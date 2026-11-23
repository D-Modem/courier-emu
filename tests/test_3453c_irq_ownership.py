"""The byte-UART and frame requests must share the controller's EOI stack."""
import pytest

from courier_emu.machine import CourierMachine
from courier_emu.timers import INT0_VECTOR


def controller():
    machine = object.__new__(CourierMachine)
    machine._interrupt_stack = []
    machine._int0_in_service = False
    machine._rom_link_errors = None
    return machine


@pytest.mark.parametrize('specific', [False, True])
def test_nested_uart_eoi_does_not_release_interrupted_data_irq(specific):
    machine = controller()
    machine._track_external_interrupt(INT0_VECTOR)
    machine._track_external_interrupt(0x0e)
    machine._complete_external_interrupt(0x0e if specific else 0x8000)
    assert machine._interrupt_stack == [INT0_VECTOR]
    assert machine._int0_in_service
    machine._complete_external_interrupt(INT0_VECTOR if specific else 0x8000)
    assert machine._interrupt_stack == []
    assert not machine._int0_in_service


def test_data_irq_eoi_preserves_interrupted_board_tick():
    machine = controller()
    machine._track_external_interrupt(0x0f)
    machine._track_external_interrupt(INT0_VECTOR)
    machine._complete_external_interrupt(0x8000)
    assert machine._interrupt_stack == [0x0f]
    assert not machine._int0_in_service
    machine._complete_external_interrupt(0x8000)
    machine._complete_external_interrupt(0x8000)  # no in-service request
    assert machine._interrupt_stack == []
