from types import SimpleNamespace

import pytest

from courier_emu.isdn_console import scripted_pump
from courier_emu.sio import SerialChannel


def transmit(channel, value, now):
    channel.write(channel.base, value)
    channel.advance(now)
    channel.advance(now + 1)


@pytest.mark.parametrize("capture_limit", [8, 65536])
def test_live_output_continues_after_report_capture_fills(capture_limit):
    channel = SerialChannel(0x100, max_bytes=capture_limit, pace=1)
    expected = bytes(i & 255 for i in range(capture_limit + 100))
    output = bytearray()
    for i, value in enumerate(expected):
        transmit(channel, value, i * 2)
        output.extend(channel.take_output())
    assert output == expected
    assert channel.tx == expected[:capture_limit]
    assert channel.transmitted == len(expected)
    assert channel.output_dropped == channel.overruns == 0
    assert channel.output_pending == 0
    assert channel.take_output() == b""


def test_host_backlog_is_bounded_and_reports_drops_separately():
    channel = SerialChannel(0x100, max_bytes=4, pace=1)
    for i in range(6):
        transmit(channel, i, i * 2)
    assert channel.output_pending == 4
    assert channel.output_dropped == 2
    assert channel.transmitted == 6
    assert channel.take_output() == bytes(range(4))
    transmit(channel, 6, 12)
    assert channel.take_output() == b"\x06"
    assert channel.tx == bytes(range(4))
    assert channel.overruns == 0


def test_console_deadline_uses_live_output_after_capture_limit():
    channel = SerialChannel(0x100, max_bytes=1, pace=1)
    machine = SimpleNamespace(channels={channel.base: channel},
                              command_base=channel.base, instructions=0)
    pump = scripted_pump([])
    transmit(channel, 65, 0)
    assert pump.next_due(machine) == 0
    assert channel.take_output() == b"A"
    assert pump.next_due(machine) is None
    transmit(channel, 66, 2)
    assert channel.tx == b"A"  # Capture full; the new live byte is still due.
    assert pump.next_due(machine) == 0
    assert channel.take_output() == b"B"
    assert pump.next_due(machine) is None
