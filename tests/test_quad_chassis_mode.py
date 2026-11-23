from pathlib import Path

import pytest
from unicorn import Uc, UC_ARCH_X86, UC_MODE_16
from unicorn.x86_const import UC_X86_REG_AX, UC_X86_REG_CS, UC_X86_REG_DS, UC_X86_REG_IP

from tools.probe_quad_call import chassis_frame

ROOT = Path(__file__).resolve().parents[1]


def test_original_dispatcher_selects_feature_provisioning_parameter_01f2():
    flash = (ROOT / 'artifacts/quad-identify-20260910/flash.bin').read_bytes()
    uc = Uc(UC_ARCH_X86, UC_MODE_16)
    uc.mem_map(0, 0x100000)
    uc.mem_write(0xc0000, flash)
    uc.reg_write(UC_X86_REG_CS, 0xf3b2)
    uc.reg_write(UC_X86_REG_IP, 0xf4889 - 0xf3b20)
    uc.reg_write(UC_X86_REG_DS, 0)
    uc.reg_write(UC_X86_REG_AX, 0x01f2)
    uc.emu_start(0xf4889, 0xf4894, count=10)
    assert int.from_bytes(uc.mem_read(0x9c2e, 2), 'little') == 0x4dbb


def test_original_feature_setter_enables_x2_gate_not_receive_callbacks():
    flash = (ROOT / 'artifacts/quad-identify-20260910/flash.bin').read_bytes()
    uc = Uc(UC_ARCH_X86, UC_MODE_16)
    uc.mem_map(0, 0x100000)
    uc.mem_write(0xc0000, flash)
    uc.mem_write(0x1000, chassis_frame(0x01f2, 0x20, 0))
    uc.mem_write(0x9c2c, (0x100a).to_bytes(2, 'little'))
    uc.mem_write(0x8838, b'\xcf')
    uc.mem_write(0x839d, (0x3210).to_bytes(2, 'little'))
    uc.reg_write(UC_X86_REG_CS, 0xf3b2)
    uc.reg_write(UC_X86_REG_IP, 0x4dbb)
    uc.reg_write(UC_X86_REG_DS, 0)
    uc.emu_start(0xf88db, 0xf89ae, count=120)
    assert uc.mem_read(0x8838, 1) == b'\xef'
    assert int.from_bytes(uc.mem_read(0x839d, 2), 'little') == 0x3210


@pytest.mark.parametrize('wire,mode', [(0, 0), (1, 1), (2, 4), (3, 5), (4, 6), (5, 7)])
def test_original_chassis_mode_setter_maps_wire_enum_not_at_mode_number(wire, mode):
    flash = (ROOT / 'artifacts/quad-identify-20260910/flash.bin').read_bytes()
    assert flash[0x37c74:0x37c79] == bytes.fromhex('fc8b362c9c')
    frame = chassis_frame(0x003f, wire, 0)
    uc = Uc(UC_ARCH_X86, UC_MODE_16)
    uc.mem_map(0, 0x100000)
    uc.mem_write(0xc0000, flash)
    uc.mem_write(0x1000, frame)
    # The real dispatcher has already consumed header and parameter ID.
    uc.mem_write(0x9c2c, (0x100a).to_bytes(2, 'little'))
    uc.reg_write(UC_X86_REG_CS, 0xf000)
    uc.reg_write(UC_X86_REG_IP, 0x7c74)
    uc.reg_write(UC_X86_REG_DS, 0)
    # Execute the original setter; stop before its common post-update handler.
    uc.emu_start(0xf7c74, 0xf7c96, count=20)
    assert uc.mem_read(0xa895, 1)[0] == mode
    assert int.from_bytes(uc.mem_read(0x9c2c, 2), 'little') == 0x100c
