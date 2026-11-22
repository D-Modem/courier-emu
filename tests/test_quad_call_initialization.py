from collections import deque
from types import SimpleNamespace

import pytest

from tools.probe_quad_call import terminal_initialization_ready


class ReadOnlyMemory:
    def __init__(self, state=0x91e6):
        self.state = state
        self.reads = []

    def mem_read(self, address, size):
        self.reads.append((address, size))
        assert (address, size) == (0x81f8, 2)
        return self.state.to_bytes(2, 'little')


def machine(output=b'\r\nOK\r\n', state=0x91e6):
    return SimpleNamespace(
        uc=ReadOnlyMemory(state), serial=list(output), serial_rx=deque(),
        quad_terminal=SimpleNamespace(output_start=0),
        uart=SimpleNamespace(pending=deque(), receive_unread=False))


def test_original_ok_and_idle_receiver_allow_chassis_configuration():
    guest = machine()
    assert terminal_initialization_ready(guest)
    assert guest.uc.reads == [(0x81f8, 2)]


@pytest.mark.parametrize('pending', ['host', 'uart', 'unread', 'command'])
def test_ok_does_not_allow_chassis_to_interrupt_remaining_setup(pending):
    guest = machine()
    if pending == 'host':
        guest.serial_rx.append(13)
    elif pending == 'uart':
        guest.uart.pending.append(13)
    elif pending == 'unread':
        guest.uart.receive_unread = True
    else:
        guest.uc.state = 0x92af
    assert not terminal_initialization_ready(guest)


def test_missing_or_partial_response_is_not_completion():
    assert not terminal_initialization_ready(machine(b'\r\nOK'))
    assert not terminal_initialization_ready(machine(b''))


def test_preexisting_output_does_not_acknowledge_this_setup():
    guest = machine()
    guest.quad_terminal.output_start = len(guest.serial)
    assert not terminal_initialization_ready(guest)


def test_multiple_setup_lines_require_all_original_results():
    assert not terminal_initialization_ready(machine(), expected_results=2)
    assert terminal_initialization_ready(machine(b'\r\nOK\r\n\r\nOK\r\n'), expected_results=2)


def test_rejected_settings_are_not_silently_used_as_a_control():
    with pytest.raises(RuntimeError, match='initialization returned ERROR'):
        terminal_initialization_ready(machine(b'\r\nERROR\r\n'))
