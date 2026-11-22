"""The ROM's DSP frame cadence must not be replaced by a fixed 2400 Hz clock."""
import pytest

from courier_emu.machine import CourierMachine, SERVICE_INSTRUCTIONS, TIMER_POLL_INSTRUCTIONS
from tests.test_native_machine import firmware


@pytest.mark.parametrize('name', [
    'IDSDL302.ROM', 'dumps/courier-board-21210-capture-403/courier-board.rom',
])
def test_rom_with_dsp_defaults_to_firmware_edges(monkeypatch, name):
    monkeypatch.delenv('COURIER_ROM_XF_INT0', raising=False)
    m = CourierMachine(firmware(name), with_dsp=True)
    assert m._use_dsp_xf_int0
    assert m._interrupt_poll_instructions == SERVICE_INSTRUCTIONS
    assert m._timer_poll_owed == SERVICE_INSTRUCTIONS
    assert m._xf_frame_source()


@pytest.mark.parametrize('options,xf,poll', [
    ({'frame_source': 'periodic'}, False, TIMER_POLL_INSTRUCTIONS),
    ({'frame_source': 'dsp-xf'}, True, SERVICE_INSTRUCTIONS),
    ({'frame_hz': 2401}, True, TIMER_POLL_INSTRUCTIONS),
    ({'interrupt_poll_instructions': 256}, True, 256),
])
def test_explicit_controls_are_preserved(monkeypatch, options, xf, poll):
    monkeypatch.delenv('COURIER_ROM_XF_INT0', raising=False)
    m = CourierMachine(firmware('IDSDL302.ROM'), with_dsp=True, **options)
    assert m._use_dsp_xf_int0 == xf
    assert m._interrupt_poll_instructions == poll
    if 'frame_hz' in options:
        assert not m._xf_frame_source()


def test_legacy_environment_override_is_preserved(monkeypatch):
    monkeypatch.setenv('COURIER_ROM_XF_INT0', '0')
    m = CourierMachine(firmware('IDSDL302.ROM'), with_dsp=True)
    assert not m._use_dsp_xf_int0
    assert m._interrupt_poll_instructions == TIMER_POLL_INSTRUCTIONS
    m = CourierMachine(firmware('IDSDL302.ROM'), with_dsp=True, frame_source='dsp-xf')
    assert m._use_dsp_xf_int0


def test_xmf_dsp_profile_retains_legacy_polling(monkeypatch):
    monkeypatch.delenv('COURIER_ROM_XF_INT0', raising=False)
    m = CourierMachine(firmware('main211.xmf'), with_dsp=True)
    assert not m._use_dsp_xf_int0
    assert m._interrupt_poll_instructions == TIMER_POLL_INSTRUCTIONS


def test_no_dsp_retains_legacy_polling(monkeypatch):
    monkeypatch.delenv('COURIER_ROM_XF_INT0', raising=False)
    m = CourierMachine(firmware('IDSDL302.ROM'))
    assert not m._use_dsp_xf_int0
    assert m._interrupt_poll_instructions == TIMER_POLL_INSTRUCTIONS
