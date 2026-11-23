"""Full serial evidence is independent of the bounded diagnostic report."""
import importlib.util
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest

from courier_emu.machine import CourierMachine, MAX_SERIAL_BYTES


def capture_machine():
    m = CourierMachine.__new__(CourierMachine)
    m.serial = bytearray()
    m.serial_bytes_total = 0
    m._serial_tail = bytearray()
    m.serial_trace = []
    m.online_mode = False
    m._serial_input_after_connect = []
    m.console = None
    m.serial_output = BytesIO()
    m.serial_truncated = False
    return m


def test_full_stream_preserves_raw_bytes_beyond_report_limit():
    m = capture_machine()
    payload = bytes(range(256)) * 400
    for value in payload:
        m._capture_serial(value)
    assert m.serial_output.getvalue() == payload
    assert bytes(m.serial) == payload[:MAX_SERIAL_BYTES]
    assert m.serial_truncated
    assert m.serial_bytes_total == len(payload)


def test_mode_detection_continues_after_report_fills():
    m = capture_machine()
    m.serial = bytearray(b'x' * MAX_SERIAL_BYTES)
    for value in b'\r\nCONNECT 53333/ARQ/x2\r\n':
        m._capture_serial(value)
    assert m.online_mode
    for value in b'payload\r\nNO CARRIER\r\n':
        m._capture_serial(value)
    assert not m.online_mode
    assert m.serial_trace == ['entered-data-mode', 'left-data-mode']


def test_capture_write_failure_is_not_silently_ignored():
    m = capture_machine()
    def fail(data):
        raise OSError('disk full')
    m.serial_output = SimpleNamespace(write=fail)
    with pytest.raises(OSError, match='disk full'):
        m._capture_serial(65)


def test_cli_forwards_full_stream_path(monkeypatch, tmp_path):
    from courier_emu.cli import build_parser, _worker_command
    monkeypatch.setattr('courier_emu.cli.load_image',
                        lambda *a, **kw: SimpleNamespace(path='firmware.rom'))
    path = tmp_path / 'serial.bin'
    args = build_parser().parse_args(['run', 'firmware.rom', '--serial-output', str(path)])
    cmd = _worker_command(args)
    assert cmd[cmd.index('--serial-output') + 1] == str(path)


@pytest.fixture
def validator():
    path = Path(__file__).resolve().parents[2] / 'v90modem/tools/probe_x2_host_courier.py'
    if not path.exists():
        pytest.skip('sibling x2 test driver not installed')
    spec = importlib.util.spec_from_file_location('x2_capture_validator', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.read_serial_capture


def test_validator_accepts_full_stream_despite_truncated_report(validator, tmp_path):
    path = tmp_path / 'serial.bin'
    payload = b'a' * 100000
    path.write_bytes(payload)
    assert validator({'serial_truncated': True, 'serial_bytes_total': len(payload)}, path) == payload


def test_validator_rejects_missing_or_incomplete_capture(validator, tmp_path):
    path = tmp_path / 'serial.bin'
    with pytest.raises(ValueError, match='truncated'):
        validator({'serial_truncated': True}, path)
    path.write_bytes(b'abc')
    with pytest.raises(ValueError, match='reported total'):
        validator({'serial_bytes_total': 4}, path)
