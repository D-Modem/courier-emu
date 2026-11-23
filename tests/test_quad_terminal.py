from collections import deque
from types import SimpleNamespace

import pytest

from courier_emu.quad_terminal import QuadTerminal


class Memory:
    def __init__(self, state, carrier):
        self.bytes = {0x81f8: state & 255, 0x81f9: state >> 8, 0x8311: carrier}
        self.writes = []

    def mem_read(self, address, count):
        return bytes(self.bytes.get(address + offset, 0) for offset in range(count))

    def mem_write(self, address, value):
        self.writes.append((address, value))
        self.bytes.update({address + offset: byte for offset, byte in enumerate(value)})


def machine(state=0x91a1, carrier=4):
    delivered = []
    return SimpleNamespace(uc=Memory(state, carrier), instructions=50_000_000,
                           serial_rx=deque(b'DATA'), serial=bytearray(),
                           uart=SimpleNamespace(pending=False, receive_unread=False, receive_enabled=True,
                                                deliver=delivered.append),
                           delivered=delivered)


@pytest.mark.parametrize('kwargs', [{'interval': 0}, {'interval': -1}, {'online_interval': 0}])
def test_terminal_byte_intervals_must_be_positive(kwargs):
    with pytest.raises(ValueError, match='positive'):
        QuadTerminal(**kwargs)


def test_online_interval_defaults_to_the_existing_general_interval():
    terminal = QuadTerminal(interval=10_000)
    current = machine()
    terminal.service(current, True)
    assert terminal.next_byte == current.instructions + 10_000


def test_online_bytes_use_guest_uart_handler_without_callback_patches():
    terminal = QuadTerminal()
    current = machine()
    terminal.service(current, True)
    assert current.delivered == [ord('D')]
    assert current.uc.writes == []
    assert terminal.opened == 0
    assert terminal.command_start  # Data must not change command-boundary bookkeeping.
    terminal.service(current, True)
    assert current.delivered == [ord('D')]  # Respect the DTE character deadline.
    current.instructions = terminal.next_byte
    terminal.service(current, True)
    assert current.delivered == [ord('D'), ord('A')]


@pytest.mark.parametrize('carrier,interrupts,pending', [(0, True, False),
                                                        (4, False, False),
                                                        (4, True, True)])
def test_online_delivery_requires_carrier_interrupts_and_free_uart(carrier, interrupts, pending):
    current = machine(carrier=carrier)
    current.uart.pending = pending
    QuadTerminal().service(current, interrupts)
    assert not current.delivered
    assert not current.uc.writes


def test_online_pacing_is_configurable_without_speeding_up_command_autobaud():
    terminal = QuadTerminal(interval=100_000, online_interval=10_000)
    current = machine()
    terminal.service(current, True)
    assert terminal.next_byte == current.instructions + 10_000
    current = machine(state=0x91e6, carrier=0)
    current.timers = SimpleNamespace(write=lambda *args: None)
    terminal = QuadTerminal(interval=100_000, online_interval=10_000)
    terminal.service(current, True)
    assert terminal.next_byte == current.instructions + 100_000


def test_online_delivery_waits_for_firmware_to_enable_receiver():
    current = machine()
    current.uart.receive_enabled = False
    QuadTerminal().service(current, True)
    assert not current.delivered
    assert len(current.serial_rx) == 4


@pytest.mark.parametrize('state,carrier', [(0x91a1, 4), (0x91e6, 0)])
def test_unread_byte_blocks_delivery_even_after_interrupt_dispatch(state, carrier):
    from courier_emu.uart import EbSerial, S0RBUF

    terminal = QuadTerminal()
    current = machine(state=state, carrier=carrier)
    current.timers = SimpleNamespace(write=lambda *args: None)
    current.uart = EbSerial(control=0x21)
    current.uart.deliver(0x80)
    current.uart.pending.clear()  # ISR entered, but has not read the buffer.
    queued = bytes(current.serial_rx)
    terminal.service(current, True)
    assert bytes(current.serial_rx) == queued
    assert terminal.received == terminal.opened == 0
    assert not current.uc.writes
    assert current.uart.overruns == 0
    assert current.uart.read(S0RBUF, 2) == 0x80

    terminal.service(current, True)
    assert terminal.received == 1
    assert current.uart.read(S0RBUF, 2) == queued[0]
    assert current.uart.overruns == 0


def test_online_stream_preserves_all_octets_under_slow_firmware_reads():
    from courier_emu.uart import EbSerial, S0RBUF

    terminal = QuadTerminal(interval=1)
    current = machine()
    current.uart = EbSerial(control=0x21)
    payload = bytes(range(256)) * 4
    current.serial_rx = deque(payload)
    received = bytearray()
    while current.serial_rx:
        terminal.service(current, True)
        current.uart.pending.clear()
        current.instructions += 100_000
        terminal.service(current, True)  # Deliberately late buffer read.
        received.append(current.uart.read(S0RBUF, 2))
    assert received == payload
    assert terminal.received == len(payload)
    assert current.uart.overruns == 0
    assert terminal.opened == 0
    assert not current.uc.writes


def test_command_autobaud_adapter_still_opens_at_attention_boundary():
    terminal = QuadTerminal()
    current = machine(state=0x91e6, carrier=0)
    current.timers = SimpleNamespace(write=lambda *args: None)
    terminal.service(current, True)
    assert terminal.opened == 1
    assert current.delivered == [ord('D')]
    assert (0x81f4, (0xf85d).to_bytes(2, 'little')) in current.uc.writes
