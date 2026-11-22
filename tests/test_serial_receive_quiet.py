"""Elide only event-free online DTE spans; raw-pin reads remain time-exact."""
from collections import deque
from types import SimpleNamespace

import pytest

from courier_emu.machine import CourierMachine
from courier_emu.uart import DteTransmitLine, EbSerial


def receiving():
    machine = CourierMachine.__new__(CourierMachine)
    machine.console = None
    machine._rom_serial = object()
    machine._rom_dte_opened = machine.online_mode = True
    machine.serial_rx = deque([0xa5, 0x00])
    machine.timers = SimpleNamespace(controller=SimpleNamespace(enabled=lambda name: True))
    machine.uart = EbSerial(holding=True)
    machine.dte_line = DteTransmitLine(1500)
    machine.dte_line.begin(0xa5, 100)
    machine.dte_line.take_edge()
    return machine


@pytest.mark.parametrize('bit', range(10))
def test_online_receive_can_wait_to_byte_completion(bit):
    machine = receiving()
    now = 100 + bit * 1500
    assert machine._serial_receive_quiet_until(now) == 15100
    assert machine._serial_receive_quiet_until(now + 1499) == 15100


@pytest.mark.parametrize('change', [
    lambda m: setattr(m, 'console', object()),
    lambda m: setattr(m, '_rom_serial', None),
    lambda m: setattr(m, '_rom_dte_opened', False),
    lambda m: setattr(m, 'online_mode', False),
    lambda m: m.serial_rx.clear(),
    lambda m: setattr(m, 'uart', None),
    lambda m: setattr(m.uart, 'holding', False),
    lambda m: m.uart.pending.append(0x14),
    lambda m: setattr(m.uart, '_tx_end', 100),
    lambda m: m.dte_line.idle(),
    lambda m: setattr(m.dte_line, '_edge', True),
])
def test_nonquiet_serial_states_remain_cooperative(change):
    machine = receiving()
    change(machine)
    assert machine._serial_receive_quiet_until(101) is None


def test_full_duplex_quiet_deadline_includes_earlier_tx_event():
    machine = receiving()
    machine.uart._tx_stop = 200
    machine.uart._tx_end = 220
    assert machine._serial_receive_quiet_until(101) == 200
    assert machine._serial_receive_quiet_until(200) is None
    machine.uart.advance(200, 5.93)
    assert machine._serial_receive_quiet_until(201) is None  # pending TI
    machine.uart.take_interrupt()
    assert machine._serial_receive_quiet_until(201) == 220


def test_masked_start_edge_stays_latched_without_forcing_python_polls():
    machine = receiving()
    machine.dte_line._edge = True
    enabled = [False]
    machine.timers.controller.enabled = lambda name: enabled[0]
    assert machine._serial_receive_quiet_until(101) == 15100
    assert machine.dte_line._edge
    enabled[0] = True
    assert machine._serial_receive_quiet_until(102) is None
    assert machine.dte_line._edge


def test_byte_completion_and_prestart_are_not_quiet():
    machine = receiving()
    assert machine._serial_receive_quiet_until(99) is None
    assert machine._serial_receive_quiet_until(15100) is None
    assert machine._serial_receive_quiet_until(15101) is None


@pytest.mark.parametrize('byte', [0x00, 0xff, 0xa5])
def test_deadlines_preserve_every_64_instruction_pin_observation(byte):
    machine = receiving()
    machine.dte_line.byte = byte
    until = machine._serial_receive_quiet_until(100)
    for now in range(128, 15200, 64):
        if now >= until:
            assert machine._serial_receive_quiet_until(now) is None
            assert machine.dte_line.complete(now)
            break
        bit = (now - 100) // 1500
        expected = 0 if bit == 0 else (1 if bit >= 9 else (byte >> (bit - 1)) & 1)
        # As with the real FF5A hook, observations compute the wire level at
        # the access time; there is no cached level to refresh at bit edges.
        assert machine.dte_line.level(now) == expected
    else:
        pytest.fail('did not reach the byte completion service')
