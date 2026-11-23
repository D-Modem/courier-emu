"""80C186EB status latches are distinct from data and interrupt latches."""
from courier_emu.uart import (
    EbSerial, S0STS, S0RBUF, S0TBUF, RECEIVE_VECTOR, TRANSMIT_VECTOR,
    CLEAR_TO_SEND, TRANSMIT_READY, RECEIVE_READY, TRANSMIT_COMPLETE,
    OVERRUN_ERROR,
)


def test_status_acknowledges_completion_without_consuming_data_or_irq():
    uart = EbSerial()
    uart.deliver(0x81)
    assert uart.write(S0TBUF, 2, 0x142) == 0x42
    assert uart.read(S0STS, 2) == (
        TRANSMIT_READY | CLEAR_TO_SEND | RECEIVE_READY | TRANSMIT_COMPLETE)
    assert uart.read(S0STS, 2) == TRANSMIT_READY | CLEAR_TO_SEND
    assert list(uart.pending) == [RECEIVE_VECTOR, TRANSMIT_VECTOR]
    assert uart.read(S0RBUF, 2) == 0x81


def test_buffer_read_consumes_data_but_preserves_receive_completion():
    uart = EbSerial()
    uart.deliver(0x41)
    assert uart.read(S0RBUF, 2) == 0x41
    uart.deliver(0x54)
    assert not uart.overrun
    assert uart.read(S0STS, 2) & RECEIVE_READY
    assert uart.read(S0RBUF, 2) == 0x54


def test_status_read_does_not_prevent_unread_buffer_overrun():
    uart = EbSerial()
    uart.deliver(0x41)
    uart.read(S0STS, 2)
    uart.deliver(0x54)
    assert uart.overruns == 1
    assert uart.read(S0STS, 2) & OVERRUN_ERROR
    assert not uart.read(S0STS, 2) & OVERRUN_ERROR
    assert uart.read(S0RBUF, 2) == 0x54


def test_pending_transmit_completion_does_not_block_receive_capacity():
    uart = EbSerial()
    uart.write(S0TBUF, 2, 0x42)
    assert list(uart.pending) == [TRANSMIT_VECTOR]
    assert uart.receive_available
    uart.deliver(0x41)
    assert not uart.receive_available
    assert list(uart.pending) == [TRANSMIT_VECTOR, RECEIVE_VECTOR]
    uart.pending.remove(RECEIVE_VECTOR)
    assert not uart.receive_available  # The unread holding byte still matters.
    assert uart.read(S0RBUF, 2) == 0x41
    assert uart.receive_available
    assert list(uart.pending) == [TRANSMIT_VECTOR]
    assert uart.overruns == 0


def test_receive_interrupt_has_priority_over_an_earlier_transmit_request():
    uart = EbSerial()
    uart.write(S0TBUF, 2, 0x42)
    uart.deliver(0x41)
    assert uart.take_interrupt() == RECEIVE_VECTOR
    assert uart.take_interrupt() == TRANSMIT_VECTOR


def timed_uart():
    uart = EbSerial(control=0x21, baud_compare=0x8015, timed_transmit=True)
    uart.advance(100, 5.93)
    return uart


def test_timed_transmit_raises_ti_at_stop_bit_not_at_buffer_write():
    uart = timed_uart()
    uart.write(S0TBUF, 2, 0x41)
    # 22 CPU cycles per baud tick, eight ticks per bit, nine bits to stop.
    from math import ceil
    stop = 100 + ceil(9 * 22 * 8 / 5.93)
    end = 100 + ceil(10 * 22 * 8 / 5.93)
    assert not uart.pending
    assert not uart.read(S0STS, 2) & (TRANSMIT_COMPLETE | TRANSMIT_READY)
    uart.advance(stop - 1, 5.93)
    assert not uart.pending
    uart.advance(stop, 5.93)
    assert list(uart.pending) == [TRANSMIT_VECTOR]
    assert uart.read(S0STS, 2) & TRANSMIT_COMPLETE
    assert uart.transmit_busy
    uart.advance(end, 5.93)
    assert not uart.transmit_busy
    assert uart.read(S0STS, 2) & TRANSMIT_READY


def test_timed_transmit_has_two_slots_and_coalesces_completion_requests():
    uart = timed_uart()
    uart.write(S0TBUF, 2, 0x41)
    uart.write(S0TBUF, 2, 0x42)
    assert uart.transmit_overruns == 0
    assert not uart.pending
    uart.advance(1000, 5.93)
    assert not uart.transmit_busy
    assert list(uart.pending) == [TRANSMIT_VECTOR]
    assert uart.transmitted == 2
    assert uart.read(S0STS, 2) & TRANSMIT_COMPLETE
    assert not uart.read(S0STS, 2) & TRANSMIT_COMPLETE


def test_third_write_to_busy_transmitter_reports_a_holding_register_overrun():
    uart = timed_uart()
    for byte in b'ABC':
        uart.write(S0TBUF, 2, byte)
    assert uart.transmit_overruns == 1


def test_receive_runs_while_timed_transmitter_is_busy():
    uart = timed_uart()
    uart.write(S0TBUF, 2, 0x42)
    assert uart.receive_available
    uart.deliver(0x41)
    assert uart.take_interrupt() == RECEIVE_VECTOR
    assert uart.read(S0RBUF, 2) == 0x41
    assert uart.transmit_busy
    assert uart.receive_available
    uart.advance(1000, 5.93)
    assert uart.take_interrupt() == TRANSMIT_VECTOR
    assert uart.overruns == 0


def test_cts_is_a_persistent_input_level():
    uart = EbSerial(clear_to_send=True)
    assert uart.read(S0STS, 2) & CLEAR_TO_SEND
    assert uart.read(S0STS, 2) & CLEAR_TO_SEND
    uart.clear_to_send = False
    assert not uart.read(S0STS, 2) & CLEAR_TO_SEND
