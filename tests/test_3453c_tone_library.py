"""Isolated genuine tone library, not proof of a supervisor-driven call."""
from pathlib import Path

from courier_emu.bridge import CourierDspBridge
from courier_emu.images import load_image
from courier_emu.exchange import DtmfDecoder

ROOT = Path(__file__).resolve().parents[1]


def test_original_bc_tone_library_generates_decodable_dtmf_when_installed():
    image = load_image(ROOT / 'dumps/3453bc-firmware-read-2.2.09/firmware.bin')
    bridge = CourierDspBridge(image)
    core = bridge.core
    try:
        segments = image.dsp_program_segments()
        origin, resident = segments[0]
        core.load_program(resident, origin)
        library_origin, library = next(pair for pair in segments if pair[0] == 0)
        core.load_program(library, library_origin)
        core.set_pc(origin)
        core.set_io(0x57, 6)
        core.step(500_000)
        assert core.program(0x413) == 0xbc07

        def command(tag, value):
            core.set_io(0x5e, tag)
            core.set_io(0x5f, value)
            core.set_io(0x57, core.io(0x57) | 1)
            core.step(60_000)

        command(0x1a, 0x3000)
        command(0x1b, 0x0c08)
        command(0x13, 5)
        assert core.data(0x39a) == 0x044a
        core.step(6_000_000)
        assert any(core.line_tx_samples())
        bridge._take_line_audio()
        decoder = DtmfDecoder(sample_rate=8000)
        assert decoder.feed(list(bridge._exchange_line_buffer)) == '5'
    finally:
        core.close()
