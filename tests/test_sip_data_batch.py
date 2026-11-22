"""SIP streaming must not inherit the coarse training coupling quantum."""
from collections import Counter, deque
from types import SimpleNamespace
from pathlib import Path
import struct

import pytest

from courier_emu.bridge import CourierDspBridge


def bridge(batch=4096, *, rom=True, sip=True):
    b = CourierDspBridge.__new__(CourierDspBridge)
    b.batch = b._configured_batch = batch
    b._scheduling_batch_changes = []
    b.boot_rom_enabled = rom
    b._sip_line = object() if sip else None
    b._instructions = 133377920
    b.runtime_words_queued = 0
    b.runtime_messages = []
    b.runtime_message_counts = Counter()
    b.runtime_message_first_seen = {}
    b.runtime_message_first_pc = {}
    b.observed = []
    b._observe_asic_command = lambda *words: b.observed.append(words)
    b._x86_ticks = 3072
    b._exchange_instructions = 2048
    b._codec_instructions = 123
    b._dsp_cycle_debt = -1.75
    return b


def credits(b):
    return (b._instructions, b._x86_ticks, b._exchange_instructions,
            b._codec_instructions, b._dsp_cycle_debt)


@pytest.mark.parametrize('mode', [0, 1, 2, 3])
def test_receive_mode_bounds_coupling_without_discarding_clock_credits(mode):
    b = bridge()
    before = credits(b)
    b._record_runtime_message((0xA, mode), 0x81234)
    assert b.batch == 1024
    assert b._configured_batch == 4096
    assert credits(b) == before
    assert b.observed == [(0xA, mode)]
    assert b.runtime_words_queued == 2
    assert b.runtime_message_counts[f'000a:{mode:04x}'] == 1
    assert b.runtime_message_first_pc[f'000a:{mode:04x}'] == '81234'
    assert b._scheduling_batch_changes == [{
        'instructions': 133377920, 'old': 4096, 'new': 1024,
        'reason': 'sip-receive-mode',
    }]
    b._record_runtime_message((0xA, mode), None)
    assert len(b._scheduling_batch_changes) == 1


@pytest.mark.parametrize('batch', [64, 128, 256, 512, 1024])
def test_smaller_configured_quanta_are_not_increased(batch):
    b = bridge(batch)
    b._record_runtime_message((0xA, 1), None)
    assert b.batch == batch
    assert not b._scheduling_batch_changes


@pytest.mark.parametrize('rom,sip,tag', [
    (False, True, 0xA), (True, False, 0xA), (False, False, 0xA),
    (True, True, 9), (True, True, 0x57),
])
def test_other_transports_and_commands_keep_configured_batch(rom, sip, tag):
    b = bridge(rom=rom, sip=sip)
    b._record_runtime_message((tag, 1), None)
    assert b.batch == 4096
    assert not b._scheduling_batch_changes


def test_restore_training_quantum_keeps_all_elapsed_credits():
    b = bridge()
    b._record_runtime_message((0xA, 1), None)
    before = credits(b)
    b._set_scheduling_batch(b._configured_batch, 'dsp-reset')
    assert b.batch == 4096
    assert credits(b) == before
    assert b._scheduling_batch_changes[-1]['reason'] == 'dsp-reset'


def test_reset_net_restores_training_quantum_once():
    b = bridge()
    b._record_runtime_message((0xA, 1), None)
    before = credits(b)
    resets = []
    b._windows = {1: bytearray(b'\x34\x12')}
    b.transfer = SimpleNamespace(first_strobe=1)
    b._reset_asserted = False
    b._sync_physical_control = lambda **kwargs: None
    b._reset_log = []
    b.line = None
    b._exchange_tx_index = 29
    b.float_runtime_bus = lambda: None
    b.core = SimpleNamespace(reset=lambda: resets.append(True))
    b._exchange_line_buffer = deque()
    b._configure_frame_interrupt = lambda: None
    b.set_reset(True)
    assert b.batch == 4096
    assert b._download_destination == 0x1234
    assert resets == [True]
    assert credits(b) == before
    assert b._scheduling_batch_changes[-1]['reason'] == 'dsp-reset'
    b.set_reset(True)
    assert resets == [True]
    b.set_reset(False)
    assert b.batch == 4096


# A real downstream XID, including its original FCS. This is a component
# load test of the resident output routine, not an open-loop call replay.
XID = bytes.fromhex(
    '03af8280001303038a8900050204000602040007010f08010ff0000f0003563432'
    '01010302020800030120a5cd')


def forward_at_batch(batch):
    from courier_emu.dsp import NativeC5x
    from courier_emu.images import load_image
    image = Path(__file__).resolve().parents[1] / 'dumps/courier-board-21210-capture-403/courier-board.rom'
    if not image.exists():
        pytest.skip('403 resident fixture unavailable')
    origin, program = load_image(image).dsp_program_segments()[0]
    c = NativeC5x.from_program(origin, program)
    try:
        c.configure_host_mailbox()
        assert c.program(0x8320) == 0x8B8E
        # Configure the real six-cell circular output window through MMR
        # instructions (set_data deliberately does not write MMRs).
        c.load_program(struct.pack('<9H', 0xBC00, 0xAE1C, 0x58, 0xAE1D,
                                   0x5D, 0xAE1E, 0xEF, 0x7980, 0x207), 0x200)
        c.set_pc(0x200)
        c.step(64)
        # LDP 6; CALL original 8320; side-effect-free spin after return.
        c.load_program(struct.pack('<5H', 0xBC06, 0x7A80, 0x8320,
                                   0x7980, 0x213), 0x210)
        c.set_data(0x327, 0x58)
        c.set_data(0x37B, 1)
        received = bytearray()
        sent = cursor = seen_edge = 0
        # The captured board timebase is 3,399,663 instructions/s. Offer
        # decoded bytes at 52 kbit/s; the 1415-instruction XF period is the
        # existing nominal frame cadence. CPU ACKs here are instantaneous,
        # an optimistic bound: this cannot exaggerate receiver starvation.
        end = len(XID) * 8 * 3399663 // 52000 + batch + 1415
        for now in range(batch, end + batch, batch):
            due = min(len(XID), now * 52000 // (8 * 3399663))
            while sent < due:
                c.set_data(0x320, XID[sent])
                c.set_pc(0x210)
                c.step(128)
                sent += 1
            edge = now // 1415
            if edge > seen_edge:
                seen_edge = edge
                while c.data_channel_status() & (0x100 << cursor):
                    received.append(c.io_output(0x58 + cursor) & 0xFF)
                    c.ack_data_channels(1 << cursor)
                    cursor = (cursor + 1) % 6
        return bytes(received)
    finally:
        c.close()


@pytest.mark.parametrize('configured', [256, 1024, 4096])
def test_effective_streaming_batch_preserves_original_xid(configured):
    b = bridge(configured)
    b._record_runtime_message((0xA, 3), None)
    assert forward_at_batch(b.batch) == XID


def test_uncapped_training_batch_loses_bytes_even_with_instant_cpu_acks():
    received = forward_at_batch(4096)
    assert received != XID
    assert len(received) < len(XID)


def test_batch_change_history_is_bounded():
    b = bridge()
    for _ in range(40):
        b._set_scheduling_batch(1024, 'sip-receive-mode')
        b._set_scheduling_batch(4096, 'dsp-reset')
    assert len(b._scheduling_batch_changes) == 32
