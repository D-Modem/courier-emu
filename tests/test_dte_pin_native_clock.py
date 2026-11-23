"""Real Machine FF5A hooks must see data-bit edges without service at them."""
from pathlib import Path
import pytest
from courier_emu.images import load_image
from courier_emu.machine import CourierMachine
from courier_emu.x86_interpreter import Uc, UC_X86_REG_CS, UC_X86_REG_IP, UC_X86_REG_DS, UC_X86_REG_ES


@pytest.mark.parametrize('byte', [0x00, 0xff, 0xa5])
def test_raw_pin_read_hook_synchronizes_between_scheduler_services(byte, monkeypatch):
    path = (Path(__file__).resolve().parents[1]
            / 'dumps/courier-board-21210-capture-403/courier-board.rom')
    if not path.exists():
        pytest.skip('optional supervisor ROM unavailable')
    m = CourierMachine(load_image(path), interrupt_poll_instructions=4096)
    # 150 reads in a 3-instruction loop, all before the first 1024-instruction
    # service. The 50-instruction bits cross many read accesses in that span.
    program = bytes.fromhex('bf0020 b99600 a05aff aa e2fa f4')
    original_start = Uc.emu_start
    first = [True]
    def start(uc, begin, until, **kwargs):
        if first[0]:
            first[0] = False
            uc.mem_write(0x1000, program)
            for reg, value in [(UC_X86_REG_CS, 0), (UC_X86_REG_IP, 0x1000),
                               (UC_X86_REG_DS, 0), (UC_X86_REG_ES, 0)]:
                uc.reg_write(reg, value)
            begin = 0x1000
        return original_start(uc, begin, until, **kwargs)
    monkeypatch.setattr(Uc, 'emu_start', start)
    m.dte_line.bit_instructions = 50
    m.dte_line.begin(byte, 0)
    observations = []
    level = m.dte_line.level
    def observed(now):
        value = level(now)
        observations.append((now, value))
        return value
    m.dte_line.level = observed
    m.run(500)
    assert len(observations) == 150
    assert len({at for at, _ in observations}) == 150
    assert observations[-1][0] < 1024
    assert {at // 50 for at, _ in observations} >= set(range(9))
    for at, value in observations:
        bit = at // 50
        expected = 0 if bit == 0 else (1 if bit >= 9 else (byte >> (bit - 1)) & 1)
        assert value == expected
    assert [bool(v & 0x20) for v in m.uc.mem_read(0x2000, 150)] == [bool(v) for _, v in observations]
    assert m.uc._native.retired > 0
