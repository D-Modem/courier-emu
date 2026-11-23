"""Independent ASIC register controls, not a substituted call/data path."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from courier_emu.board3453 import Board3453
from courier_emu.bridge import CourierDspBridge
from courier_emu.images import load_image

ROOT = Path(__file__).resolve().parents[1]


class HoldingRegisters:
    def __init__(self):
        self.inputs = {0x56: 0x3f00}
        self.outputs = {}

    def io(self, port):
        return self.inputs.get(port, 0)

    def set_io(self, port, value):
        self.inputs[port] = value

    def io_output(self, port):
        return self.outputs.get(port, 0)

    def data_channel_status(self):
        return ~self.inputs[0x56] & 0x3f3f

    def post_data_channels(self, mask):
        self.inputs[0x56] |= mask

    def ack_data_channels(self, mask):
        self.inputs[0x56] |= mask << 8


@pytest.mark.parametrize('channel', range(6))
def test_cpu_dsp_data_channel_directions_and_handshake(channel):
    core = HoldingRegisters()
    board = Board3453.__new__(Board3453)
    board.bridge = SimpleNamespace(core=core, window=bytearray(8),
                                   _lanes={0x40 + 2 * n: (1, n) for n in range(8)})
    board.finished = True
    board.data_window = bytearray(12)
    port, mask = 0x40 + channel * 4, 1 << channel
    assert board.read(0x18, 1) == 0x3f
    assert board.read(0x1a, 1) == 0

    board.write(port, 1, 0x56)
    board.write(port + 2, 1, 0x34)
    assert core.io(0x58 + channel) == 0
    assert core.io(0x56) == 0x3f00  # Data writes alone do not post a word.
    board.write(0x18, 1, mask)
    assert core.io(0x58 + channel) == 0x3456
    assert core.io(0x56) & mask
    assert not board.read(0x18, 1) & mask
    # The DSP reads the holding word, then acknowledges it with PA6 W1C.
    assert core.io(0x58 + channel) == 0x3456
    core.set_io(0x56, core.io(0x56) & ~mask)
    assert board.read(0x18, 1) & mask

    core.outputs[0x58 + channel] = 0xabcd  # DSP OUT precedes RX W1C.
    assert not board.read(0x1a, 1) & mask
    core.set_io(0x56, core.io(0x56) & ~(mask << 8))
    assert board.read(0x1a, 1) & mask
    assert board.read(port, 1) == 0xcd
    assert board.read(port + 2, 1) == 0xab
    assert core.io(0x58 + channel) == 0x3456  # Opposite holding direction.
    board.write(0x1a, 1, mask)
    assert not board.read(0x1a, 1) & mask


def test_original_cpu_transmit_and_receive_use_same_pa6_banks():
    firmware = (ROOT / 'dumps/3453bc-firmware-read-2.2.09/firmware.bin').read_bytes()
    def code(address, size):
        return firmware[address - 0x40000:address - 0x40000 + size]
    # TX selector 2BC returns DX=40, BX=0001; RX selector 2BE returns
    # the same data address but BX=0100. Caller posts/ACKs BX at 18/1A.
    assert code(0x68154, 8) == bytes.fromhex('ba4000bb0100f9c3')
    assert code(0x68087, 8) == bytes.fromhex('ba4000bb0001f9c3')
    assert code(0x6eab2, 6) == bytes.fromhex('e61886c4e61a')


def test_native_data_status_and_original_word_operations():
    image = load_image(ROOT / 'dumps/3453bc-firmware-read-2.2.09/firmware.bin')
    core = CourierDspBridge(image).core
    try:
        _, library = next(pair for pair in image.dsp_program_segments() if pair[0] == 0)
        # Isolated register operations, not a substitute for a guest call.
        # Both directions read/write their holding word before PA6 W1C.
        code = bytes.fromhex('06bc') + b''.join(
            library[a * 2:(a + 2) * 2] for a in (0x122, 0x11d, 0x19d, 0x197))
        core.load_program(code, 0x8000)
        core.set_io(0x56, 0x3f00)
        core.set_io(0x58, 0x3456)
        core.post_data_channels(1)
        core.set_data(0x37d, 1)
        core.set_data(0x320, 0xabcd)
        core.set_pc(0x8000)
        core.step(1)  # LDP
        core.step(1)  # IN reads exactly the posted word
        assert core.data(0x350) == 0x3456
        assert not core.data_channel_status() & 1
        core.step(1)  # W1C acknowledges it
        assert core.io(0x56) == 0x3f00
        assert core.data_channel_status() & 1
        core.set_data(0x37d, 0x100)
        core.step(1)  # OUT publishes the actual received word, before W1C
        assert core.io_output(0x58) == 0xabcd
        assert not core.data_channel_status() & 0x100
        core.step(1)  # W1C now announces the already-published RX word
        assert core.io(0x56) == 0x3e00
        assert core.data_channel_status() & 0x100
        core.ack_data_channels(1)
        assert core.io(0x56) == 0x3f00
        assert not core.data_channel_status() & 0x100
        core.reset()
        assert core.data_channel_status() == 0
        # The resident's all-ones PA6 reset (1032) exposes the initial
        # holding words for CPU drain/ACK; those ACKs establish RX-free bits.
        core.load_program(library[0x197 * 2:0x199 * 2], 0x8000)
        core.set_data(0x7d, 0xffff)
        core.set_pc(0x8000)
        core.step(1)
        assert core.io(0x56) == 0
        assert core.data_channel_status() == 0x3f3f
        core.ack_data_channels(0x3f)
        assert core.io(0x56) == 0x3f00
        assert core.data_channel_status() == 0x3f
    finally:
        core.close()


def test_original_dsp_pa6_instruction_clears_consumed_channel():
    image = load_image(ROOT / 'dumps/3453bc-firmware-read-2.2.09/firmware.bin')
    bridge = CourierDspBridge(image)
    core = bridge.core
    try:
        _, library = next(pair for pair in image.dsp_program_segments() if pair[0] == 0)
        # Original 0197: OUT @7D,8056; run only that register operation.
        core.load_program(library[0x197 * 2:0x199 * 2], 0x8000)
        core.set_data(0x7d, 1)
        core.set_io(0x56, 0x3f01)
        core.set_pc(0x8000)
        core.step(1)
        assert core.io(0x56) == 0x3f00
    finally:
        core.close()
