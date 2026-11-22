"""SPRU056D 4.4.3: XF and INTM are not context-shadowed."""
import struct

import pytest

from courier_emu.dsp import NativeC5x


def image(words):
    return struct.pack(f'<{len(words)}H', *words)


@pytest.mark.parametrize('return_opcode', [0xbe38, 0xbe3a])  # RETI, RETE
@pytest.mark.parametrize('initial_xf', [False, True])
def test_interrupt_return_preserves_xf_changed_by_handler(return_opcode, initial_xf):
    with NativeC5x.from_program(0x22, image([0x7980, 0x40])) as core:
        core.load_program(image([0xbe4c if initial_xf else 0xbe4d, return_opcode]), 0x40)
        core.load_program(image([0xbe4d if initial_xf else 0xbe4c, 0xbe71]), 0x6000)
        core.set_pc(0x6000)
        core.step(5)
        state = core.state()
        assert state['pc'] == 0x6002
        assert bool(state['flags'] & 2) is not initial_xf
        assert bool(state['flags'] & 0x80) is (return_opcode == 0xbe38)


def test_reti_does_not_remask_interrupts_unmasked_by_handler():
    with NativeC5x.from_program(0x22, image([0x7980, 0x40])) as core:
        core.load_program(image([0xbe40, 0xbe38]), 0x40)  # CLRC INTM; RETI
        core.load_program(image([0xbe71]), 0x6000)
        core.set_pc(0x6000)
        core.step(4)
        assert core.state()['pc'] == 0x6001
        assert not core.state()['flags'] & 0x80
