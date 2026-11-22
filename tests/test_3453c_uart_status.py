"""The payload's synchronous DTE transmitter reports empty to every caller."""

from dataclasses import replace
from pathlib import Path

import pytest

from courier_emu.machine import CourierMachine, _uart_bus_reversed_23
from courier_emu.xmf import XmfImage


@pytest.mark.parametrize('flags', [0, 1, 0x80, 0x81])
@pytest.mark.parametrize('kind', [0, 5, 6, 7])
def test_uart_wire_reversal_matches_original_isr_loops(flags, kind):
    # 59B98 skips both loops if bit zero is clear. Otherwise there is one
    # loop at 59BA2, and a second at 59BBF unless UART kind is seven.
    loops = 0 if not flags & 1 else (1 if kind == 7 else 2)
    assert _uart_bus_reversed_23(flags, kind) is bool(loops % 2)


@pytest.mark.parametrize('irq_mode', ['rx', 'tx', None])
def test_uart_data_port_write_is_tx_regardless_of_requested_irq(irq_mode):
    image = XmfImage.load(Path(__file__).resolve().parents[1] / '2_3_33.XMF')
    # Isolated UART control: guest OUT, not a fabricated modem data reply.
    code = bytes.fromhex('c606a20600 c606650900 b04b e60a f4')
    data = bytearray(image.data)
    start = image.supervisor_offset + 0x10
    data[start:start + len(code)] = code
    machine = CourierMachine(
        replace(image, data=bytes(data), entry_offset_value=0x10),
        cpu_engine='interpreter',
    )
    machine._serial_started = True
    machine._serial_irq_mode = irq_mode
    machine.online_mode = True
    result = machine.run(32)
    assert result.serial_text == 'K'
    assert machine.data_tx_bytes == 1


@pytest.mark.parametrize('size', [1, 2])
@pytest.mark.parametrize('value', [0x4b, 0xff])
@pytest.mark.parametrize('eight_bits', [False, True])
def test_original_eb_transmit_buffer_store_reaches_terminal(size, value, eight_bits):
    image = XmfImage.load(Path(__file__).resolve().parents[1] / '2_3_33.XMF')
    # Isolated register control, not a forced online transition in a call.
    code = bytes.fromhex('c6061227') + bytes([int(eight_bits)])
    code += (bytes.fromhex('c6066aff') + bytes([value]) if size == 1 else
             bytes.fromhex('c7066aff') + bytes([value, 0xa5])) + b'\xf4'
    data = bytearray(image.data)
    start = image.supervisor_offset + 0x10
    data[start:start + len(code)] = code
    machine = CourierMachine(
        replace(image, data=bytes(data), entry_offset_value=0x10),
        cpu_engine='interpreter',
    )
    machine.online_mode = True
    machine.run(32)
    assert bytes(machine.serial) == bytes([value & (0xff if eight_bits else 0x7f)])
    assert machine.data_tx_bytes == 1


@pytest.mark.parametrize('delay', [0, 250])
def test_external_first_chunk_delay_preserves_inter_chunk_guard(delay):
    from courier_emu.machine import AFTER_CONNECT_GUARD_MS, INSTRUCTIONS_PER_MS
    image = XmfImage.load(Path(__file__).resolve().parents[1] / '2_3_33.XMF')
    machine = CourierMachine(image, serial_input_after_connect=[b'A', b'B'],
                             serial_input_after_connect_delay_ms=delay)
    machine.instructions = 1234
    # Isolated stimulus scheduler control, not evidence of firmware CONNECT.
    for value in b'\r\nCONNECT\r\n':
        machine._capture_serial(value)
    assert list(machine._serial_input_schedule) == [
        (1234 + delay * INSTRUCTIONS_PER_MS, b'A'),
        (1234 + (delay + AFTER_CONNECT_GUARD_MS) * INSTRUCTIONS_PER_MS, b'B'),
    ]


def test_negative_external_terminal_delay_is_rejected():
    image = XmfImage.load(Path(__file__).resolve().parents[1] / '2_3_33.XMF')
    with pytest.raises(ValueError, match='non-negative'):
        CourierMachine(image, serial_input_after_connect_delay_ms=-1)


@pytest.mark.parametrize('dtr', [None, False, True])
def test_external_dtr_pin_does_not_detach_terminal_uart(dtr):
    image = XmfImage.load(Path(__file__).resolve().parents[1] / '2_3_33.XMF')
    code = bytes.fromhex('e412 a20020 e414 a20120 c6065affa5 a05aff a20220 f4')
    data = bytearray(image.data)
    start = image.supervisor_offset + 0x10
    data[start:start + len(code)] = code
    machine = CourierMachine(
        replace(image, data=bytes(data), entry_offset_value=0x10),
        cpu_engine='interpreter', serial_input=b'AT\r', terminal_dtr=dtr,
    )
    machine.run(32)
    assert machine._terminal_attached
    asserted = dtr is not False
    pins = bytes(machine.uc.mem_read(0x2000, 3))
    assert bool(pins[0] & 0x40) is not asserted
    assert bool(pins[1] & 1) is not asserted
    assert bool(pins[2] & 0x40) is not asserted
    assert pins[2] & ~0x40 == 0xa5


@pytest.mark.parametrize("size", [1, 2])
@pytest.mark.parametrize("status", [0, 0xA501])
def test_uart_empty_status_at_arbitrary_guest_pc(size, status):
    image = XmfImage.load(Path(__file__).resolve().parents[1] / "2_3_33.XMF")
    # Run away from the printf and dialer polling addresses. Seed the status
    # register, read it through guest MMIO, and store the observed value in RAM.
    code = bytes.fromhex("fa c70666ff") + status.to_bytes(2, "little")
    code += bytes.fromhex("a066ff a20020" if size == 1 else "a166ff a30020")
    code += b"\xf4"
    start = image.supervisor_offset + 0x10
    data = bytearray(image.data)
    data[start:start + len(code)] = code
    machine = CourierMachine(
        replace(image, data=bytes(data), entry_offset_value=0x10),
        cpu_engine="interpreter",
    )
    machine.run(32)
    observed = int.from_bytes(machine.uc.mem_read(0x2000, size), "little")
    assert observed == (status | 8) & ((1 << (8 * size)) - 1)
