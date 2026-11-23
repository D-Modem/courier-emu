"""Codec-direct transport uses native DSP polling, never the 8 kHz socket FIR."""
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from courier_emu.bridge import CourierDspBridge
from courier_emu.cli import build_parser, _worker_command

ROOT = Path(__file__).resolve().parents[1]
IMAGE = ROOT / 'dumps/courier-board-21210-capture-403/courier-board.rom'


def physical_bridge():
    bridge = CourierDspBridge.__new__(CourierDspBridge)
    bridge.core = SimpleNamespace(codec_sample_rate=7200,
        service_step=lambda *args: None, set_hybrid_return=lambda *args: None,
        line_tx_writes=lambda: 143, call_tdm_active=lambda: False)
    bridge.line = SimpleNamespace(codec_direct=True)
    bridge.daa = SimpleNamespace(off_hook=True)
    bridge.exchange = bridge.sip = None
    bridge._audio_only = True
    bridge._line_digital = True
    bridge.error = None
    bridge.active = bridge.launched = bridge.boot_rom_enabled = True
    bridge._runtime_mode = False
    bridge._call_resume_pending = bridge.rx_acquisition_assist = False
    bridge._hybrid_return_applied = 0
    bridge._x86_ticks = bridge._instructions = bridge._line_codec_last = 0
    bridge._line_service_skipped = bridge._codec_instructions = 0
    bridge._dsp_cycle_debt = -1e6
    bridge.dsp_cycles_per_x86 = 5
    bridge.batch = 256
    bridge.codec = None
    bridge._port_writes = lambda *args: 0
    bridge.finish_fast_clock = lambda *args: None
    return bridge


def test_physical_native_poll_yields_at_codec_deadline_and_retune():
    bridge = physical_bridge()
    assert bridge.fast_clock_static()
    assert bridge.line_service_limits() == (144, 64)
    assert bridge.clock_x86_fast(256)
    bridge.core.line_tx_writes = lambda: 144
    assert not bridge.clock_x86_fast(256)
    bridge.core.codec_sample_rate = 9600
    assert bridge.line_service_limits() == (192, 64)
    assert bridge.clock_x86_fast(256)
    bridge.core.line_tx_writes = lambda: 192
    assert not bridge.clock_x86_fast(256)


def test_physical_retune_cannot_extend_the_batch_before_refilling_adc():
    bridge = physical_bridge()
    bridge._physical_codec_rate = 7200
    bridge.core.codec_sample_rate = 9600
    assert bridge.line_service_limits() == (1, 64)
    assert not bridge.clock_x86_fast(256)


def test_low_latency_physical_service_uses_requested_interval():
    bridge = physical_bridge()
    bridge.line.codec_service_seconds = .005
    assert bridge.line_service_limits() == (36, 64)


def test_fresh_generation_does_not_inherit_retune_deadline():
    bridge = physical_bridge()
    bridge._physical_codec_rate = 9600
    bridge._exchange_tx_index = 0
    assert bridge.line_service_limits() == (144, 64)


@pytest.mark.parametrize('state', ['legacy_audio', 'hybrid_changed', 'not_launched', 'error'])
def test_physical_native_poll_keeps_existing_safety_guards(state):
    bridge = physical_bridge()
    if state == 'legacy_audio':
        bridge.line.codec_direct = False
    elif state == 'hybrid_changed':
        bridge._hybrid_return_applied = 26
    elif state == 'not_launched':
        bridge.launched = False
    else:
        bridge.error = 'stopped'
    assert not bridge.fast_clock_static()


@pytest.fixture
def pcm_peer(tmp_path):
    # No hardware: a lossless, unpaced peer records real firmware output.
    helper = tmp_path / 'pcm-peer'
    helper.write_text(f'#!{sys.executable}\n' + '''
import hashlib, json, os, socket, struct, sys
s = socket.socket(fileno=int(sys.argv[1]))
def read(n):
    out = bytearray()
    while len(out) < n:
        b = s.recv(n-len(out))
        if not b: return None
        out.extend(b)
    return bytes(out)
hash = hashlib.sha256()
samples = frames = 0
had_offhook = False
hooks = []
controls = []
while True:
    header = read(8)
    if header is None: break
    n, flags = struct.unpack('<II', header)
    hook = flags & 1
    pcm = read(2*n)
    hash.update(pcm)
    samples += n
    frames += bool(n)
    if not n: controls.append(flags)
    if not hooks or hooks[-1] != hook: hooks.append(hook)
    had_offhook = had_offhook or bool(hook)
    gaps = int(os.environ.get('APPLE_TEST_FINISH_GAPS') == '1' and had_offhook and not n and flags == 2)
    s.sendall(struct.pack('<IIII',n,0,gaps,0)+bytes(2*n))
with open(os.environ['APPLE_TEST_TRACE'],'w') as f:
    json.dump(dict(samples=samples,frames=frames,hooks=hooks,controls=controls,sha256=hash.hexdigest()),f)
''')
    helper.chmod(0o755)
    return helper


@pytest.mark.skipif(not IMAGE.exists(), reason='captured 403 image unavailable')
def test_403_physical_poll_native_and_python_are_equivalent(tmp_path, pcm_peer):
    # Native poll on/off must not change audio, hook transitions, instruction
    # boundaries, AT results, codec state or explicit reset controls.
    helper = pcm_peer
    reports, traces = [], []
    for enabled in ('0', '1'):
        trace = tmp_path / f'trace-{enabled}.json'
        args = build_parser().parse_args([
            'run', str(IMAGE), '--apple-modem', str(helper),
            '--nvram-fixture', 'idsdl403', '--board-id', '7',
            '--tick-ms', '5', '--at', 'ATH1', '--serial-input-after', '5000000',
            '--instructions', '60000000', '--line-frames', '500'])
        env = dict(os.environ, COURIER_WORKER_POLL=enabled,
                   COURIER_FAST_SERVICE='1', APPLE_TEST_TRACE=str(trace))
        completed = subprocess.run(_worker_command(args), env=env,
                                   text=True, capture_output=True, timeout=60)
        assert completed.returncode == 0, completed.stderr
        report = json.loads(completed.stdout)
        assert report['error'] is None
        assert report['dsp_bridge']['error'] is None
        assert report['serial_text'] == '\r\nOK\r\n'
        assert report['dsp_bridge']['line']['native_lane_io']
        polls = report['dsp_bridge']['line']['native_worker_polls']
        assert (polls > 0) is (enabled == '1')
        reports.append(report)
        traces.append(json.loads(trace.read_text()))
    assert traces[0] == traces[1]
    # A stopped CPU explicitly releases physical PCM before slow reporting.
    assert traces[0]['hooks'] == [0, 1, 0]
    assert not reports[0]['dsp_bridge']['line']['off_hook']
    for key in ('instructions', 'registers', 'serial_hex', 'supervisor_call_cells'):
        assert reports[0][key] == reports[1][key]
    assert reports[0]['dsp_bridge']['serial_port'] == reports[1]['dsp_bridge']['serial_port']


@pytest.mark.skipif(not IMAGE.exists(), reason='captured 403 image unavailable')
def test_403_dial_timeout_releases_hook_and_returns_result_after_reset(tmp_path, pcm_peer):
    trace = tmp_path / 'dial-timeout.json'
    args = build_parser().parse_args([
        'run', str(IMAGE), '--apple-modem', str(pcm_peer),
        '--nvram-fixture', 'idsdl403', '--board-id', '7', '--tick-ms', '5',
        '--at', 'ATX1S7=1DT6311', '--serial-input-after', '5000000',
        '--instructions', '80000000', '--line-frames', '1100'])
    command = _worker_command(args)
    gain_option = command.index('--apple-tx-gain')
    del command[gain_option:gain_option + 2]  # verify the worker's own default too
    completed = subprocess.run(command,
        env=dict(os.environ, APPLE_TEST_TRACE=str(trace), COURIER_WORKER_POLL='1'),
        text=True, capture_output=True, timeout=60)
    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report['error'] is None and report['dsp_bridge']['error'] is None
    assert report['serial_text'] == '\r\nNO CARRIER\r\n'
    line = report['dsp_bridge']['line']
    assert line['native_worker_polls'] > 0
    assert line['tx_gain'] == 1.0
    assert not line['off_hook']
    assert not line['output_gap_samples'] and not line['input_overflow_samples']
    wire = json.loads(trace.read_text())
    assert wire['hooks'] == [0, 1, 0]
    assert 3 in wire['controls']  # explicit reset silence while still off-hook
    assert wire['controls'][-1] & 1 == 0  # control-only release, no PCM needed


@pytest.mark.skipif(not IMAGE.exists(), reason='captured 403 image unavailable')
@pytest.mark.parametrize('combined', [False, True])
def test_403_binary_setup_must_not_overflow_real_at_command_buffer(tmp_path, pcm_peer, combined):
    # Real CPU/ROM AT parser, but the PCM peer is explicitly offline silence:
    # no physical modem/line, fabricated carrier, or decoded data is involved.
    from tools.apple_sip_profiles import settings
    at = ('ATX1S27=1' + settings('v32-lapm') + 'S2=255&I0S7=45DT2903'
          if combined else 'ATS2=43&I0')
    trace = tmp_path / 'binary-setup.json'
    args = build_parser().parse_args([
        'run', str(IMAGE), '--apple-modem', str(pcm_peer),
        '--nvram-fixture', 'idsdl403', '--board-id', '7', '--tick-ms', '5',
        '--at', at, '--serial-input-after', '5000000',
        '--instructions', '60000000', '--line-frames', '500'])
    completed = subprocess.run(_worker_command(args),
        env=dict(os.environ, APPLE_TEST_TRACE=str(trace)),
        text=True, capture_output=True, timeout=60)
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result['error'] is None and result['dsp_bridge']['error'] is None
    assert result['serial_text'] == ('\r\nERROR\r\n' if combined else '\r\nOK\r\n')
    assert json.loads(trace.read_text())['hooks'] == [0]


@pytest.mark.skipif(not IMAGE.exists(), reason='captured 403 image unavailable')
def test_physical_finish_preserves_reported_active_failure(tmp_path, pcm_peer):
    trace = tmp_path / 'finish-failure.json'
    args = build_parser().parse_args([
        'run', str(IMAGE), '--apple-modem', str(pcm_peer),
        '--nvram-fixture', 'idsdl403', '--board-id', '7', '--tick-ms', '5',
        '--at', 'ATH1', '--serial-input-after', '5000000',
        '--instructions', '60000000', '--line-frames', '500'])
    completed = subprocess.run(_worker_command(args),
        env=dict(os.environ, APPLE_TEST_TRACE=str(trace), APPLE_TEST_FINISH_GAPS='1'),
        text=True, capture_output=True, timeout=60)
    result = json.loads(completed.stdout)
    assert completed.returncode != 0
    assert 'output underrun' in result['error']
    assert result['dsp_bridge']['line']['output_gap_samples'] == 1
    assert json.loads(trace.read_text())['hooks'] == [0, 1, 0]


@pytest.mark.skipif(not IMAGE.exists(), reason='captured 403 image unavailable')
def test_trace_worker_archives_actual_mailbox_events_offline(tmp_path, pcm_peer):
    prefix = tmp_path / 'codec'
    args = build_parser().parse_args([
        'run', str(IMAGE), '--apple-modem', str(pcm_peer),
        '--nvram-fixture', 'idsdl403', '--board-id', '7', '--tick-ms', '5',
        '--at', 'ATX1S7=1DT7910', '--serial-input-after', '5000000',
        '--instructions', '600000000', '--line-frames', '1000'])
    command = _worker_command(args)
    completed = subprocess.run([
        command[0], str(ROOT/'artifacts/apple-dial-extensions/trace_worker.py'), *command[3:]],
        env=dict(os.environ, APPLE_CALL_TRACE=str(prefix), APPLE_CALL_DIAGNOSTICS='1',
                 APPLE_TEST_TRACE=str(tmp_path/'peer-trace.json')),
        text=True, capture_output=True, timeout=60)
    assert completed.returncode == 0, completed.stderr
    saved = [json.loads(line) for line in (tmp_path/'codec-mailbox.jsonl').read_text().splitlines()]
    assert any(row['kind']=='io' and row['port']==0x5e for row in saved)
    assert any(row['kind']=='host' for row in saved)
    assert not [row for row in saved if row['kind'] in ('loss', 'error')]
