"""ROM modem-to-DTE CTS is distinct from the UART's RTS-driven CTS input."""
from types import SimpleNamespace

import pytest

from courier_emu.machine import CourierMachine


@pytest.mark.parametrize('online,known_rom,busy,latch,permitted', [
    (True, True, False, 0x94, True),   # CS asserted, other panel bits irrelevant
    (True, True, False, 0x96, False),  # modem asks the host to stop
    (True, True, False, 0xff, False),
    (True, True, False, 0x00, True),
    (True, True, True, 0x96, True),    # finish an in-flight character
    (False, True, False, 0x96, True),  # don't interfere with autobaud/AT entry
    (True, False, False, 0x96, True),  # no borrowed wiring for other boards
])
def test_modem_cts_gates_only_new_online_rom_characters(
        online, known_rom, busy, latch, permitted):
    machine = SimpleNamespace(online_mode=online,
                              _rom_serial=object() if known_rom else None,
                              dte_line=SimpleNamespace(busy=busy),
                              output_latches={0x14: latch})
    assert CourierMachine._dte_transmit_permitted(machine) is permitted


def test_unobserved_latch_does_not_invent_backpressure():
    machine = SimpleNamespace(online_mode=True, _rom_serial=object(),
                              dte_line=SimpleNamespace(busy=False), output_latches={})
    assert CourierMachine._dte_transmit_permitted(machine)


def test_cts_release_and_reassertion_do_not_mutate_input():
    machine = SimpleNamespace(online_mode=True, _rom_serial=object(),
                              dte_line=SimpleNamespace(busy=False),
                              output_latches={0x14: 0x94}, serial_rx=bytearray(b'abc'))
    assert CourierMachine._dte_transmit_permitted(machine)
    machine.output_latches[0x14] |= 0x02
    assert not CourierMachine._dte_transmit_permitted(machine)
    assert machine.serial_rx == b'abc'
    machine.output_latches[0x14] &= ~0x02
    assert CourierMachine._dte_transmit_permitted(machine)
    assert machine.serial_rx == b'abc'
