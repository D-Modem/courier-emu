import struct

import pytest

from courier_emu.dsp import NativeC5x
from courier_emu.quad_c50 import QuadC50Endpoint
from courier_emu.bridge import DSP_CYCLES_PER_X86
from courier_emu.quad_audio import resident_from_ram
from pathlib import Path


def program(*words):
    return struct.pack(f"<{len(words)}H", *words)


@pytest.mark.parametrize("cycles", [0, -1])
def test_service_slice_must_be_positive(cycles):
    with pytest.raises(ValueError, match="positive"):
        QuadC50Endpoint(service_slice_cycles=cycles)


def test_configured_data_lane_trace_remains_bounded_without_losing_totals():
    endpoint = QuadC50Endpoint(trace_data_lanes=True, data_lane_limit=2)
    endpoint._record_data_lane("cpu-to-dsp", 0, 0x40ff)
    endpoint._record_data_lane("dsp-to-cpu", 0, 0x0011)
    endpoint._record_data_lane("dsp-to-cpu", 1, 0x0091)
    assert len(endpoint.data_lane_events) == 2
    assert [event["word"] for event in endpoint.data_lane_events] == [0x40ff, 0x0011]
    assert endpoint.data_words_sent == 1
    assert endpoint.data_words_received == 2


def test_handshake_drain_survives_debug_ring_rollover():
    # A synthetic idle loop produces irrelevant output writes. Then execute
    # tag, argument and PA7 reply strobes after more than 8192 such events.
    with NativeC5x.from_program(0x8000, program(0x0c40, 0x21, 0x7980, 0x8000)) as core:
        core.configure_host_mailbox()
        endpoint = QuadC50Endpoint(core=core, _in_reset=False)
        core.set_pc(0x8000)
        core.set_data(0x40, 0)
        for _ in range(300):
            core.step(64)
            endpoint._drain_pulls()
        assert core.io_event_total() > 8192
        assert core.state()["io_events"] == 8192
        core.load_program(program(0x0c40, 0x5e, 0x0c41, 0x5f,
                                  0x0c42, 0x57), 0x9000)
        core.set_pc(0x9000)
        core.set_data(0x40, 0x55)
        core.set_data(0x41, 0xabcd)
        core.set_data(0x42, 2)
        core.step(3)
        endpoint._drain_pulls()
        assert endpoint.replies_posted == 1
        assert endpoint.read(0xd8, 1) == 0x55
        assert endpoint.read(0xdc, 1) == 0xcd
        assert endpoint.read(0xde, 1) == 0xab
        assert endpoint.read(0x9c, 1) & 2
        endpoint._drain_pulls()
        assert endpoint.replies_posted == 1


def test_native_mailbox_reset_releases_reply_slot_without_inventing_overlay():
    # QF resets PA7 during a command-1 reinitialization, after boot handoff.
    # A reset must leave the reply holding register free, or 86db never
    # presents even the reset-complete 55 and the V.8 menu queue fills.
    with NativeC5x.from_program(0x8000, program(0xae57, 0xffff)) as core:
        core.configure_host_mailbox()
        core.set_io(0x57, 0x0203)
        core.set_pc(0x8000)
        core.step(1)
        assert core.io(0x57) == 2
        # Ordinary acknowledgements are still write-one-clear, not reset.
        core.load_program(program(0xae57, 0x0200), 0x8000)
        core.set_io(0x57, 0x0203)
        core.set_pc(0x8000)
        core.step(1)
        assert core.io(0x57) == 3


def test_only_overlay_acknowledgement_consumes_overlay_window():
    with NativeC5x.from_program(0x8000, program(0x0c40, 0x57)) as core:
        core.configure_host_mailbox()
        endpoint = QuadC50Endpoint(core=core, _in_reset=False,
                                   window=(1, 2, 3, 4), _runtime_waiting=True)
        core.set_pc(0x8000)
        core.set_data(0x40, 1)
        core.step(1)
        endpoint._drain_pulls()
        assert endpoint.window == (1, 2, 3, 4)
        assert endpoint.commands_acked == 1
        core.set_data(0x40, 0x200)
        core.set_pc(0x8000)
        core.step(1)
        endpoint._drain_pulls()
        assert endpoint.window == (1, 2, 3, 4)  # preflight, not consumed
        core.load_program(program(0xaf41, 0x58, 0xaf42, 0x59,
                                  0xaf43, 0x5a, 0xaf44, 0x5b,
                                  0x0c40, 0x57), 0x8000)
        core.set_pc(0x8000)
        core.step(5)
        endpoint._drain_pulls()
        assert endpoint.window is None
        assert endpoint.program == [1, 2, 3, 4]
        assert endpoint.runtime_acks == 1


def test_overlay_start_waits_for_dsp_arm_and_reset_cannot_consume_data():
    with NativeC5x.from_program(0x8000, program(0xae57, 0x700)) as core:
        core.configure_host_mailbox()
        endpoint = QuadC50Endpoint(core=core, _in_reset=False,
                                   _overlay_ready=True)
        endpoint._runtime_strobe(4)
        assert endpoint.read(0x9e, 1) == 0
        core.set_pc(0x8000)
        core.step(1)
        endpoint._drain_pulls()
        assert endpoint.read(0x9e, 1) == 6
        endpoint._runtime_strobe(2)
        assert endpoint.window is not None
        core.load_program(program(0xae57, 0xffff), 0x8000)
        core.set_pc(0x8000)
        core.step(1)
        endpoint._drain_pulls()
        assert endpoint.runtime_acks == 0
        assert endpoint.window is not None


def test_live_six_bank_data_lanes_and_independent_receive_acknowledgements():
    with NativeC5x.from_program(0x8000, program(0xae56, 0x0025)) as core:
        core.configure_host_mailbox()
        core.set_io(0x56, 0x3f00)
        endpoint = QuadC50Endpoint(core=core, _in_reset=False,
                                   _boot_pending=False, _completion=True)
        assert endpoint.read(0x98, 1) == 0xff
        assert endpoint.read(0x9a, 1) == 0xc0
        endpoint.write(0xc0, 1, 0xab)
        endpoint.write(0xc2, 1, 0xcd)
        endpoint.write(0xd4, 1, 0x12)
        endpoint.write(0xd6, 1, 0x34)
        endpoint.write(0x98, 1, 0x25)
        assert core.io(0x58) == 0xcdab
        assert core.io(0x5d) == 0x3412
        assert core.io(0x56) == 0x3f25
        assert endpoint.window is None  # a data write is not a boot burst
        assert endpoint.read(0x98, 1) == 0xda
        core.set_pc(0x8000)
        core.step(1)
        assert endpoint.read(0x98, 1) == 0xff
        core.load_program(program(0x0c40, 0x5b, 0x0c41, 0x56), 0x8000)
        core.set_data(0x40, 0x1234)
        core.set_data(0x41, 0x0800)
        core.set_pc(0x8000)
        core.step(2)
        assert endpoint.read(0x9a, 1) == 0xc8
        assert endpoint.read(0xcc, 1) == 0x34
        assert endpoint.read(0xce, 1) == 0x12
        endpoint.write(0x9a, 1, 8)
        assert endpoint.read(0x9a, 1) == 0xc0
        endpoint.write(0x98, 1, 0xff)
        assert endpoint.core is None
        assert not endpoint._completion


def test_quad_idle2_enters_power_down_without_aborting():
    # 0xbe23 is the C5x IDLE2 opcode used by the Quad resident at 0x8329.
    # It is a real low-power wait, not an invalid instruction or ordinary IDLE.
    with NativeC5x.from_program(0x8000, program(0xbe23)) as core:
        core.set_pc(0x8000)
        core.step_cycles(8)
        assert core.state()["idle"]
        core.interrupt(4)
        assert not core.state()["idle"]


def test_service_charges_cycles_not_instruction_count():
    # Two-cycle branch loop must not run twice as fast as a one-cycle loop.
    with NativeC5x.from_program(0x8000, program(0x7980, 0x8000)) as core:
        endpoint = QuadC50Endpoint(core=core)
        core.set_pc(0x8000)
        initial = core.state()
        for _ in range(10):
            endpoint.service(1)
        state = core.state()
        assert state["cycles"] - initial["cycles"] == endpoint.cycles
        assert state["instructions"] - initial["instructions"] == endpoint.steps
        assert endpoint.cycles >= int(10 * DSP_CYCLES_PER_X86)
        assert endpoint.cycles <= int(10 * DSP_CYCLES_PER_X86) + 3
        assert endpoint.steps < endpoint.cycles


def test_byte_receiver_preserves_low_byte_and_shifter_history():
    with NativeC5x.from_program(0x8000, program(0xbe22)) as core:
        core.host_write(0x22, 0x40cc)
        core.host_write(0x20, 0)
        core.configure_digital_pcm(clock_hz=40_320_000)
        core.configure_line_frame_interrupt(5, 0xffff)
        core.queue_g711_rx(bytes((0x7a, 0xb5)))
        core.set_pc(0x8000)
        core.step_cycles(5040)
        assert core.register(0x20) & 255 == 0x7a
        core.step_cycles(5040)
        assert core.register(0x20) == 0x7ab5
        # Unlike byte mode, sixteen-bit mode supplies the complete new word.
        core.host_write(0x22, 0x40c8)
        core.queue_g711_rx(bytes((0x12, 0x34)))
        core.step_cycles(5040)
        assert core.register(0x20) == 0x1234


def test_original_quad_byte_isr_consumes_delayed_received_octet():
    root = Path(__file__).resolve().parents[1]
    resident = resident_from_ram((root / "artifacts/quad-identify-20260910/ram.bin").read_bytes())
    with NativeC5x.from_program(0x8000, resident) as core:
        core.host_write(0x22, 0x40cc)
        core.host_write(0x20, 0)
        core.configure_digital_pcm(clock_hz=40_320_000)
        core.configure_line_frame_interrupt(5, 0xffff)
        core.queue_g711_rx(bytes((0x7a, 0xb5)))
        core.load_program(program(0xbe22), 0x7000)
        core.set_pc(0x7000)
        core.step_cycles(10080)
        core.set_data(0x390, 0xbd0)
        core.set_pc(0x8406)
        core.step(7)
        assert core.data(0xbd0) == 0x7a


@pytest.mark.parametrize("slice_cycles", [64, 512])
@pytest.mark.parametrize("frame_octets", [160, 800])
def test_media_peer_refills_each_frame_without_reactivating_or_underrunning(frame_octets, slice_cycles):
    class Peer:
        def __init__(self):
            self.starts = 0
            self.frames = 0

        def start(self):
            self.starts += 1

        def exchange(self, octets):
            assert len(octets) == 1
            self.frames += 1
            return b"\x7a"

        def status(self):
            return {"frames": self.frames}

    peer = Peer()
    peer.frame_octets = frame_octets
    with NativeC5x.from_program(0x8000, program(0xbe22)) as core:
        core.host_write(0x22, 0x40cc)
        core.set_pc(0x8000)
        dsp = QuadC50Endpoint(core=core, _in_reset=False,
                              _boot_pending=False, service_slice_cycles=slice_cycles)
        dsp.media_peer = peer
        dsp.connect_digital_call()
        dsp._activate_pcm()
        assert peer.starts == 1
        assert core.g711_rx_pending() == frame_octets
        dsp.service(400_000)
        assert peer.frames > 800
        assert core.g711_rx_pending() == frame_octets
        assert core.g711_rx_underruns() == 0
        assert dsp.status()["media_peer"]["frames"] == peer.frames


def test_drain_detects_unobserved_history_loss():
    with NativeC5x.from_program(0x8000, program(0x0c40, 0x21, 0x7980, 0x8000)) as core:
        endpoint = QuadC50Endpoint(core=core)
        core.set_pc(0x8000)
        core.step(20000)
        with pytest.raises(RuntimeError, match="history lost"):
            endpoint._drain_pulls()
