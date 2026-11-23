"""DTE defaults are active firmware configuration, not seven-bit text masking."""
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from courier_emu.dte_framing import locate_dte_framing
from courier_emu.images import load_image
from courier_emu.machine import CourierMachine

ROOT = Path(__file__).resolve().parents[1]


def firmware(name):
    path = ROOT / name
    if not path.is_file():
        pytest.skip(f'optional firmware {name} unavailable')
    return load_image(path)


@pytest.mark.parametrize('name,address', [
    ('main211.xmf', 0x936), ('main2205.XMF', 0x958), ('2_3_33.XMF', 0x95a),
    ('IDSDL302.ROM', 0x5e6),
    ('dumps/courier-board-21210-capture-403/courier-board.rom', 0x4de),
])
def test_locates_active_not_stored_profile_format(name, address):
    assert locate_dte_framing(firmware(name).data) == address


def test_rejects_unknown_and_ambiguous_layouts():
    data = firmware('main211.xmf').data
    assert locate_dte_framing(b'unknown firmware') is None
    assert locate_dte_framing(data + data) is None
    # ATI5's stored WORDLEN reader alone must never be used as an active field.
    assert locate_dte_framing(bytes.fromhex('b007f606240a077502fec0')) is None


@pytest.mark.parametrize('framing,parity,width', [('8N1', 'N', 8), ('7M1', 'M', 7),
                                               ('7O1', 'O', 7), ('7E1', 'E', 7),
                                               ('stored', 'E', 7)])
def test_firmware_ati4_reports_selected_dte_format(framing, parity, width):
    machine = CourierMachine(firmware('main211.xmf'), serial_input=b'ATI4\r', dte_framing=framing)
    result = machine.run(4_000_000)
    assert result.error is None
    assert f'PARITY={parity}  WORDLEN={width}' in result.serial_text
    assert result.serial_text.endswith('OK\r\n')
    assert machine._dte_attention_seen


def test_no_attention_does_not_reconfigure_profile():
    machine = CourierMachine(firmware('main211.xmf'), serial_input=b'I4\r', dte_framing='8N1')
    machine.run(4_000_000)
    assert not machine._dte_attention_seen
    assert bytes(machine.uc.mem_read(machine._dte_framing_address, 1)) == b'\x03'


@pytest.mark.parametrize('online', [False, True])
def test_8n1_console_preserves_every_byte_including_bit_seven(online):
    # Isolated DTE capture control, not evidence of a connected datapump.
    machine = CourierMachine(firmware('main211.xmf'), serial_input=b'ATI4\r', dte_framing='8N1')
    machine.run(4_000_000)
    console = MagicMock()
    machine.console = console
    machine.online_mode = online
    for value in range(256):
        machine._capture_serial(value)
    assert bytes(call.args[0] for call in console.write.call_args_list) == bytes(range(256))


@pytest.mark.parametrize('flags,expected', [(['--console'], '8N1'),
                                           (['--serial-pty'], '8N1'),
                                           ([], 'stored'),
                                           (['--console', '--dte-framing', 'stored'], 'stored')])
def test_cli_selects_and_forwards_console_defaults(flags, expected):
    from courier_emu.cli import _worker_command, build_parser
    firmware('main211.xmf')
    args = build_parser().parse_args(['run', str(ROOT / 'main211.xmf'), *flags])
    command = _worker_command(args)
    assert command[command.index('--dte-framing') + 1] == expected


def test_stored_selection_does_not_write_firmware_setting():
    machine = CourierMachine(firmware('main211.xmf'), dte_framing='stored')
    uc = MagicMock()
    machine._accept_dte_attention(uc)
    uc.mem_write.assert_not_called()
