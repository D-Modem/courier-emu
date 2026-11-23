"""Original-firmware evidence for ATI6 accounting and the IRQ13 watchdog."""
from pathlib import Path

import pytest

from tools.probe_imodem_firmware_accounting import probe


@pytest.fixture(scope='module')
def accounting():
    image = Path(__file__).resolve().parents[1] / 'Ie030002.nac'
    if not image.exists():
        pytest.skip('Ie030002 firmware not available')
    return probe(image)


def test_call_time_seconds_advance_every_200_system_ticks(accounting):
    assert accounting['call_time'] == [
        {'system_ticks': 100, 'displayed_seconds': 1},
        {'system_ticks': 200, 'displayed_seconds': 1},
        {'system_ticks': 300, 'displayed_seconds': 2},
        {'system_ticks': 400, 'displayed_seconds': 2},
        {'system_ticks': 500, 'displayed_seconds': 3},
    ]


def test_irq_watchdog_aborts_on_entry_50_and_system_tick_resets_count(accounting):
    assert accounting['irq_watchdog'] == [
        {'entries': 49, 'abort_flag': 0},
        {'entries': 50, 'abort_flag': 128},
    ]
    assert accounting['irq_count_after_system_tick'] == 0
    assert accounting['abort_after_reset_and_one_irq'] == 0
