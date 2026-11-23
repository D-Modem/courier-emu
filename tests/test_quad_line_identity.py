from pathlib import Path

import pytest

from courier_emu.machine import CourierMachine
from courier_emu.quad_image import QuadImage

ROOT = Path(__file__).resolve().parents[1]


def image():
    source = ROOT / "artifacts/quad-identify-20260910"
    return QuadImage.modem((source / "flash.bin").read_bytes(),
                           (source / "ram.bin").read_bytes())


@pytest.mark.parametrize("kind,personality", [(1, 0), (2, 1), (None, 0)])
def test_stock_startup_classifies_persistent_chassis_line_identity(kind, personality):
    machine = CourierMachine(image(), quad_line_kind=kind, tick_ms=5,
                             max_io_events=10)
    observed = []

    def observe(pc):
        if pc == 0xf3691:
            observed.append(machine.instructions)
            if kind is not None:
                # Exercise non-identity bits after the normal startup clear.
                machine.uc.mem_write(0xb4b5, b"\xa0")

    machine._code_observer = observe
    result = machine.run(2_000_000)
    assert result.error is None
    assert observed
    assert machine.uc.mem_read(0x878a, 1)[0] == personality
    if kind is not None:
        assert machine.uc.mem_read(0xb4b5, 1)[0] == 0xa0 | kind


def test_invalid_quad_line_kind_is_rejected():
    with pytest.raises(ValueError, match="Quad line kind"):
        CourierMachine(image(), quad_line_kind=3)
