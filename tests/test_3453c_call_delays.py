"""Guest call setup must not outrun its original outbound DSP ring."""
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import pytest

from courier_emu.daa import CourierDaa
from courier_emu.exchange import LineExchange
from courier_emu.flash_image import assemble_flash
from courier_emu.images import load_image
from courier_emu.machine import CourierMachine
from courier_emu.panel import DIP_PRESETS

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('profile,source,finished,off_hook,frontend,expected', [
    (True, 'dsp', True, True, False, True),
    (True, 'dsp', True, False, False, False),
    (True, 'dsp', True, False, True, True),
    (True, 'dsp', False, True, True, False),
    (True, None, True, True, True, False),
    (False, 'dsp', True, True, True, False),
])
def test_preserve_running_3453_runtime_delays(profile, source, finished,
                                             off_hook, frontend, expected):
    machine = CourierMachine.__new__(CourierMachine)
    machine._profile3453 = profile
    machine.tick_source = source
    machine._serial_started = frontend
    machine.dsp_bridge = SimpleNamespace(
        board3453=SimpleNamespace(finished=finished),
        daa=SimpleNamespace(off_hook=off_hook))
    assert machine._clocked_3453_runtime() is expected


@pytest.fixture
def bc_image(tmp_path):
    boot = (ROOT / 'dumps/3453bc-4MBRYA8G1514-bootmodem-read-20261014/bootmodem.bin').read_bytes()
    normal = (ROOT / 'dumps/3453bc-firmware-read-2.2.09/firmware.bin').read_bytes()
    path = tmp_path / 'synthetic-settings-flash.bin'
    path.write_bytes(assemble_flash(boot, normal, b'\xff' * 0x4000))
    return load_image(path)


def test_real_guest_originate_command_is_not_dropped(bc_image):
    machine = CourierMachine(
        bc_image, with_dsp=True, tick_source='dsp',
        daa=CourierDaa('quiet'), exchange=LineExchange(),
        dip_closed=DIP_PRESETS['dedicated-line-originate'],
        serial_input=b'AT&N1&U1\rAT&L1\r',
        pc_watch={0x67d89: 'queue-drop', 0x67d5a: 'word-drop'})
    result = machine.run(8_000_000).to_dict()
    assert result['error'] is None
    counts = result['dsp_bridge']['runtime_message_counts']
    assert counts.get('0017:5040') == 1
    assert result['pc_watch_counts'].get('queue-drop', 0) == 0
    assert result['pc_watch_counts'].get('word-drop', 0) == 0
    for command in ('0050:00c1', '0050:0105', '0050:0210',
                    '0050:0310', '0050:040d', '0050:0500'):
        assert counts.get(command) == 1


def test_real_guest_on_hook_recovery_keeps_download_destination_zero(bc_image):
    machine = CourierMachine(
        bc_image, with_dsp=True, tick_source='dsp',
        daa=CourierDaa('quiet'),
        exchange=LineExchange(default_outcome='no-answer'),
        serial_input=b'AT&N1&U1X0S7=1D5551212\r',
        pc_watch={0x67d89: 'packet-drop', 0x67d5a: 'word-drop'})
    result = machine.run(14_000_000).to_dict()
    assert result['error'] is None
    assert 'NO CARRIER' in result['serial_text']
    assert result['dsp_bridge']['bootstraps'] >= 2
    assert result['pc_watch_counts'].get('packet-drop', 0) == 0
    assert result['pc_watch_counts'].get('word-drop', 0) == 0
    counts = result['dsp_bridge']['runtime_message_counts']
    assert counts.get('0002:0000', 0) >= 2
    assert counts.get('0002:1200', 0) == 0


def test_real_bc_pcm_peers_connect_and_transfer_exact_online_uart(bc_image):
    # No exchange-generated training/carrier: two original firmware instances.
    # Explicit DTE typing delay lets both ends settle; no modem readiness,
    # callback, carrier, decoded data or guest RAM is substituted.
    sent = {'a': 'A0a1b2c3d4e5f6g7' * 2, 'b': 'B9z8y7x6w5v4u3t2' * 2}
    command = [sys.executable, '-m', 'courier_emu', 'link', str(bc_image.path),
               '--with-dsp', '--line-audio-only', '--tick-source', 'dsp',
               '--instructions', '40000000', '--line-frames', '100',
               '--a-at', 'AT&M0&N1&U1', '--a-at', 'AT&L1',
               '--b-at', 'AT&M0&N1&U1', '--b-at', 'AT&L1',
               '--a-send-delay-ms', '1500', '--b-send-delay-ms', '1500',
               '--a-send', sent['a'], '--b-send', sent['b'], '--summary']
    # macOS UNIX-domain socket paths are limited to 104 bytes; pytest's full
    # per-test directory commonly exceeds that before the filename is added.
    with TemporaryDirectory(prefix='bc-peers-', dir='/tmp') as directory:
        command.extend(['--socket', str(Path(directory) / 'line.sock')])
        completed = subprocess.run(command, cwd=ROOT, capture_output=True,
                                   text=True, timeout=300)
    assert completed.returncode == 0, completed.stderr
    peers = json.loads(completed.stdout)
    for name in ('a', 'b'):
        peer = peers[name]
        assert peer['error'] is None
        assert '\r\nCONNECT\r\n' in peer['serial_text']
        assert 'NO CARRIER' not in peer['serial_text']
        assert peer['serial_input_remaining'] == 0
        assert peer['data_rx_bytes'] == len(sent[name])
        expected = sent['b' if name == 'a' else 'a']
        assert peer['serial_text'].split('CONNECT\r\n', 1)[1] == expected
        assert peer['dsp_bridge']['serial_port']['codec_rx_peak'] > 0
        assert peer['dsp_bridge']['line_service']['tx_peak_line'] > 0


def test_real_bc_pcm_peers_transfer_then_disconnect_on_external_dtr(bc_image):
    sent = {'a': 'A0a1b2c3d4e5f6g7' * 2, 'b': 'B9z8y7x6w5v4u3t2' * 2}
    # Only A's external DTR pin drops. B must detect real far-end carrier
    # loss; neither peer receives a fabricated disconnect or decoded byte.
    with TemporaryDirectory(prefix='bc-dtr-', dir='/tmp') as directory:
        output = Path(directory) / 'probe'
        command = [sys.executable, str(ROOT / 'tools/probe_3453_download.py'),
                   str(bc_image.path), '--instructions', '60000000', '--frames', '160',
                   '--setup', 'AT&D2&M0&N1&U1', '--respect-dtr',
                   '--drop-dtr-after-connect-ms', '5000', '--send-at-instruction', '28000000',
                   '--a-send', sent['a'], '--b-send', sent['b'], '--output', str(output)]
        completed = subprocess.run(command, cwd=ROOT, capture_output=True,
                                   text=True, timeout=300)
        assert completed.returncode == 0, completed.stderr
        drop = json.loads((output / 'a-summary.json').read_text())['dtr_deasserted_at']
        assert drop is not None
        for side in ('a', 'b'):
            result = json.loads((output / f'{side}-summary.json').read_text())
            assert result['error'] is None
            expected = sent['b' if side == 'a' else 'a']
            before = b''.join(bytes.fromhex(event['hex']) for event in result['serial_events']
                              if event['instruction'] < drop)
            assert before.split(b'CONNECT\r\n', 1)[1] == expected.encode()
            assert bytes(result['cpu_rx_bytes'][:32]) == expected.encode()
            # Raw Bell-103 may decode a NUL during carrier loss. It must be
            # generated by the original CPU framer after the drop, not hidden
            # by a UART filter or confused with steady-state payload loss.
            extra = bytes(result['cpu_rx_bytes'][32:])
            assert extra in (b'', b'\x00')
            assert all(event['instruction'] > drop for event in result['cpu_rx_events'][32:])
            assert result['serial_text'].split('CONNECT\r\n', 1)[1] == (
                expected + extra.decode('ascii') + '\r\nNO CARRIER\r\n')
            assert result['data_rx_bytes'] == 32
            assert (result['dtr_deasserted_at'] is not None) is (side == 'a')
            assert any(not event['off_hook'] and event['instruction'] > drop
                       for event in result['hook_events'])
            snapshots = json.loads((output / f'{side}-transport.json').read_text())
            if side == 'a':
                assert snapshots[-1]['cpu']['off_hook'] is False
            # The far leased-line peer may legitimately seize again to retry.
            assert snapshots[-1]['cpu']['queue_drop_counts'] == {}
