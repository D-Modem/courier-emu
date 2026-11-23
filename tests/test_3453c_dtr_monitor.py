"""Original DTR-lost predicate; not a synthetic hangup in real peers."""
from pathlib import Path

import pytest

from courier_emu import x86_interpreter as x86


@pytest.mark.parametrize('native', [False, True])
@pytest.mark.parametrize('p1_lost', [False, True])
@pytest.mark.parametrize('asic_lost', [False, True])
def test_original_bc_kind_zero_dtr_monitor_checks_both_active_low_inputs(
        native, p1_lost, asic_lost):
    path = Path(__file__).resolve().parents[1] / 'dumps/3453bc-firmware-read-2.2.09/firmware.bin'
    cpu = x86.Uc(0, 0)
    cpu.native_enabled = native
    cpu.mem_map(0, len(cpu.memory))
    cpu.mem_write(0x40000, path.read_bytes())
    # Unit caller for original 57BB:30CF (5AC7F). No replacement monitor.
    cpu.mem_write(0x57bb0, bytes.fromhex('e8cc30f4'))
    cpu.mem_write(0x979, b'\x02')  # &D2
    cpu.mem_write(0x965, b'\x00')  # kind zero uses EB P1.6 as well as ASIC 14.0
    cpu.mem_write(0x91b, b'\x00')  # zero S25 for this isolated predicate control
    cpu.mem_write(0xff5a, bytes([0x40 if p1_lost else 0]))
    cpu.reg_write(x86.UC_X86_REG_CS, 0x57bb)
    cpu.reg_write(x86.UC_X86_REG_SS, 0x3000)
    cpu.reg_write(x86.UC_X86_REG_SP, 0xfffe)
    cpu.reg_write(x86.UC_X86_REG_AX, 0)
    reached = []

    def read(_cpu, port, _size, _user):
        assert port == 0x14  # original selector 0104 via table at 5A90F
        return int(asic_lost)

    def action(_cpu, address, _size, _user):
        # Stop before the command-state event, rather than invent its callback
        # or an NO CARRIER response. The real peer probe exercises the rest.
        reached.append(address)
        _cpu.emu_stop()

    cpu.hook_add(x86.UC_HOOK_INSN, read, instruction=x86.UC_X86_INS_IN)
    cpu.hook_add(x86.UC_HOOK_CODE, action, begin=0x5ad38, end=0x5ad38)
    cpu.emu_start(0x57bb0, 0, count=200)
    assert bool(reached) is (p1_lost and asic_lost)
