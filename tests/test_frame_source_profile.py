import pytest

from courier_emu import machine as machine_module
from courier_emu.machine import CourierMachine
from tests.test_native_machine import firmware


@pytest.mark.parametrize('options,expected', [
    ({}, None),
    ({'frame_source': 'dsp-xf'}, 64),
    ({'frame_source': 'dsp-xf', 'interrupt_poll_instructions': 1024}, 1024),
    ({'frame_source': 'periodic', 'interrupt_poll_instructions': 64}, 64),
    ({'frame_source': 'dsp-xf', 'frame_hz': 2401}, None),
])
def test_frame_profile_selects_per_machine_latency_without_global_mutation(monkeypatch, options, expected):
    monkeypatch.delenv('COURIER_ROM_XF_INT0', raising=False)
    before = machine_module.TIMER_POLL_INSTRUCTIONS
    m = CourierMachine(firmware('IDSDL302.ROM'), **options)
    assert m._interrupt_poll_instructions == (before if expected is None else expected)
    assert m._timer_poll_owed == m._interrupt_poll_instructions
    assert machine_module.TIMER_POLL_INSTRUCTIONS == before
    # Creating an XF instance must not silently retime another board.
    legacy = CourierMachine(firmware('IDSDL302.ROM'))
    assert legacy._interrupt_poll_instructions == before


def test_invalid_source_and_poll_interval_are_rejected():
    image = firmware('IDSDL302.ROM')
    with pytest.raises(ValueError, match='frame_source'):
        CourierMachine(image, frame_source='imaginary')
    for period in (0, -1, .5):
        with pytest.raises(ValueError, match='interrupt_poll_instructions'):
            CourierMachine(image, interrupt_poll_instructions=period)
        with pytest.raises(ValueError, match='frame_irq_poll_instructions'):
            CourierMachine(image, frame_irq_poll_instructions=period)


def test_frame_recognition_interval_is_separate_from_ordinary_irq_polling():
    m = CourierMachine(firmware('IDSDL302.ROM'), frame_source='dsp-xf',
                       interrupt_poll_instructions=1024, frame_irq_poll_instructions=16)
    assert m._frame_irq_poll_instructions == 16
    assert m._interrupt_poll_instructions == 1024
    assert m._timer_poll_owed == 1024
