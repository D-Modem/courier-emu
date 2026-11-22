"""A delayed call whose slots end RPTB must return to the repeated body.

Courier 4.03's PCM table compactor uses RORB; CCD helper,C; MAR; MAR,
with the second MAR at the block end. Returning to the linear PC after the
slots drops all remaining selected bits in that 32-bit mask word.
"""
import struct

import pytest

from courier_emu.dsp import NativeC5x


@pytest.mark.parametrize('call', ['calld', 'calad', 'ccd'])
@pytest.mark.parametrize('repeat_count', [0, 1, 3])
@pytest.mark.parametrize('two_word_slot', [False, True])
@pytest.mark.parametrize('tail_words', [0, 1])
def test_delayed_call_at_repeat_end_resumes_remaining_iterations(
        call, repeat_count, two_word_slot, tail_words):
    origin = 0x6000
    # LDP 0; BRCR=count; RPTB end; SETC C; LACC #helper.
    code = [0xbc00, 0xae09, repeat_count, 0xbec6, 0,
            0xbe4f, 0xbf80, 0]
    helper_operand = None
    if call == 'calad':
        code += [0xbe3d]
    else:
        code += [0x7e80 if call == 'calld' else 0xfb11, 0]
        helper_operand = len(code) - 1
    code += [0xae61, 0x1234] if two_word_slot else [0x8b00, 0x8b00]
    code += [0x8b00] * tail_words
    code[4] = origin + len(code) - 1
    halt = origin + len(code)
    code += [0x7980, halt]
    helper = origin + len(code)
    code[7] = helper
    if helper_operand is not None:
        code[helper_operand] = helper
    # Increment an independent counter; RET.
    code += [0x1060, 0xb801, 0x9060, 0xef00]
    with NativeC5x.from_program(origin, struct.pack(f'<{len(code)}H', *code)) as core:
        core.set_pc(origin)
        core.step(200)
        assert core.data(0x60) == repeat_count + 1
        assert core.state()['pc'] == halt
        if two_word_slot:
            assert core.data(0x61) == 0x1234


@pytest.mark.parametrize('mask', [0, 1, 0x1b6d, 0xffff])
def test_conditional_delayed_call_visits_every_selected_mask_bit(mask):
    # Firmware f302..f306, reduced to a bit-selection counter. The helper
    # clobbers ACC and C, but the original 32 bits in ACCB remain available
    # to successive RORBs. In particular, a taken CCD must not exit RPTB.
    origin = 0x6000
    code = [0xbc00, 0xbe46, 0xbf80, mask, 0xbe1e,
            0xae09, 31, 0xbec6, 0x600d,
            0xbe15, 0xfb11, 0x6010, 0x8b00, 0x8b00,
            0x7980, 0x600e,
            0x1060, 0xb801, 0x9060, 0xef00]
    with NativeC5x.from_program(origin, struct.pack(f'<{len(code)}H', *code)) as core:
        core.set_pc(origin)
        core.step(1000)
        assert core.data(0x60) == mask.bit_count()
        assert core.state()['pc'] == 0x600e
