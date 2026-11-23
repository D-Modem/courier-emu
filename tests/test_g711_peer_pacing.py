"""Packet media must be serviced within a multi-frame DSP catch-up pass."""
import struct
from types import SimpleNamespace

import pytest

from courier_emu.am79c30 import Am79C30
from courier_emu.dsp import NativeC5x
from courier_emu.imodem_dsp import ImodemDsp
from courier_emu.isdn import IsdnMachine, DSP_CYCLES_PER_CPU_INSTRUCTION
from tools.probe_imodem_pair import G711Peer, HEADER


@pytest.mark.parametrize('native_bearer', [False, True])
@pytest.mark.parametrize('frame_service', [False, True])
@pytest.mark.parametrize('frame_octets', [4, 160, 800])
def test_offline_packet_boundary_requires_frame_service(native_bearer, frame_service,
                                                       frame_octets):
    dsc = Am79C30()
    dsc.activate()
    dsc.blocks[0x41] = bytes((0x16,))  # B1 <-> Bd
    dsp = ImodemDsp(dsc)
    peer = G711Peer('unused', listen=False)
    # Exercise the production default in the positive control. Only the
    # negative control opts back into the old poll-only scheduling.
    if not frame_service:
        peer.requires_frame_service = False
    peer.frame_octets = frame_octets
    peer.handle = SimpleNamespace(sendall=lambda data: None)
    next_source = frame_octets

    def source(start, size):
        # Exclude ff so an inserted MUX idle cannot match a source sample.
        return bytes(index % 251 for index in range(start, start + size))

    def read(size):
        nonlocal next_source
        if size == HEADER.size:
            return HEADER.pack(peer.frame_octets)
        result = source(next_source, size)
        next_source += size
        return result

    peer._read = read
    cursor = 0

    def service(dsc):
        nonlocal cursor
        stream = dsc.bearer_tx[1]
        fresh = bytes(stream[cursor:])
        cursor = len(stream)
        reply = peer.exchange(fresh)
        if reply:
            dsc.queue_bearer(1, reply)

    with NativeC5x.from_program(0x8000, struct.pack('<H', 0xbe22)) as core:
        dsp.core = core
        if native_bearer:
            assert dsp.attach_native_bearer()
        dsc.queue_bearer(1, source(0, frame_octets))
        dsp.lookahead_channels = (1,)
        dsp.enable_pcm_batch()
        core.set_pc(0x8000)
        core.configure_digital_pcm(clock_hz=40_320_000)
        core.configure_line_frame_interrupt(5, 0xffff)
        core.queue_g711_rx(b'\xff\xff')
        dsp.prefeed()
        machine = SimpleNamespace(
            with_dsp=True, _ledger=SimpleNamespace(needs_service=False),
            _live_bearer=lambda: False, _native_io=None, mailbox=dsp,
            bri=SimpleNamespace(media_peer=peer), _service_pcm_frame=lambda: service(dsc),
            instructions=int(3 * frame_octets * 5040 / DSP_CYCLES_PER_CPU_INSTRUCTION) + 1,
            _dsp_instructions=0,
        )
        IsdnMachine._advance_dsp(machine)
        heard = bytes(dsc.bearer_rx_heard[1])
        assert len(heard) >= 3 * frame_octets
        # A MUX insertion is invisible to the C5x FIFO-underrun counter.
        assert not core.g711_rx_underruns()
        if frame_service:
            assert dsp.pcm_frame_service is machine._service_pcm_frame
            assert peer.frames >= 3
            assert heard == source(0, len(heard))
            assert not dsc.bearer_underruns[1]
        else:
            # Negative control: the old timer-poll-only service inserts idle
            # at the packet boundary despite a continuous far-end source.
            assert dsp.pcm_frame_service is None
            assert heard[:frame_octets] == source(0, frame_octets)
            assert 0xff in heard[frame_octets:]
            assert dsc.bearer_underruns[1] > 0
