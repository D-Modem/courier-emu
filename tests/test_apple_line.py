import math
import socket
import struct
import subprocess
import sys
from pathlib import Path
from threading import Thread
from types import SimpleNamespace

import pytest

from courier_emu.apple_line import AppleLine, hardware_rate
from courier_emu.bridge import CourierDspBridge
from courier_emu.cli import build_parser, _worker_command


def read_exact(sock, n):
    data = bytearray()
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            return None
        data.extend(chunk)
    return bytes(data)


class HardwarePeer:
    def __init__(self, *, bad_count=False, overflow=False, gaps=False, rx_rail=False,
                 terminal_error=False):
        self.sock, client = socket.socketpair()
        self.client = client
        self.requests = []
        self.errors = []
        self.bad_count = bad_count
        self.terminal_error = terminal_error
        self.rx_rail = rx_rail
        self.overflow = overflow
        self.gaps = gaps
        self.thread = Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        try:
            index = 0
            while True:
                raw = read_exact(self.sock, 8)
                if raw is None:
                    break
                n, hook = struct.unpack('<II', raw)
                pcm = read_exact(self.sock, n * 2)
                self.requests.append((hook, struct.unpack(f'<{n}h', pcm)))
                # Hardware-grid input, not an emulated datapump.
                rx = ([-32768]*n if self.rx_rail else
                      [round(1000 * math.sin(2 * math.pi * 1200 * (index+i) / 10286)) for i in range(n)])
                index += n
                count = 0 if self.terminal_error else n + int(self.bad_count)
                self.sock.sendall(struct.pack('<IIII', count, 1, int(self.gaps), int(self.overflow)))
                if self.bad_count or self.terminal_error:
                    break
                self.sock.sendall(struct.pack(f'<{n}h', *rx))
        except (OSError, TypeError) as exc:
            self.errors.append(exc)
        finally:
            self.sock.close()

    def close(self):
        self.client.close()
        self.thread.join(timeout=2)
        assert not self.thread.is_alive()


@pytest.mark.parametrize('codec,expected', [(7200,7200), (7578.947368,8000),
    (8000,8000), (9600,9600), (10266.6667,10286)])
def test_rate_selection(codec, expected):
    assert hardware_rate(codec) == expected


def test_finish_stream_releases_before_reporting_without_pcm_or_adc_wait():
    peer = HardwarePeer()
    line = AppleLine('unused', transport=peer.client)
    try:
        line.set_control(True)
        line.finish_stream()
        line.finish_stream()  # Idempotent; reporting cannot seize again.
        assert peer.requests == [(1, ()), (2, ())]
        assert not line.status()['off_hook'] and line.resetting
        assert not line.sent_samples and not line.received_samples
    finally:
        line.close()
        peer.close()
    line.finish_stream()  # Already closed is harmless.


def test_finish_stream_does_not_forgive_an_existing_active_underrun():
    peer = HardwarePeer()
    line = AppleLine('unused', transport=peer.client)
    try:
        line.set_control(True)
        peer.gaps = True
        with pytest.raises(RuntimeError, match='output underrun'):
            line.finish_stream()
        assert line.output_gap_samples == 1
        assert line.error and line.closed
        assert peer.requests[-1] == (2, ())  # Real release was still requested.
    finally:
        line.close()
        peer.close()


def test_hardware_cannot_cover_rate():
    with pytest.raises(ValueError):
        hardware_rate(12000)


def test_direct_rate_transport_survives_retunes_and_has_bounded_counts():
    peer = HardwarePeer()
    line = AppleLine('unused', tx_gain=0.25, transport=peer.client)
    total_seconds = 0
    received = []
    try:
        for rate in (7200, 7578.947368, 8000, 9600, 7200):
            n = round(rate * .02)
            for _ in range(15):
                samples = [round(2000 * math.sin(2*math.pi*1000*i/rate)) for i in range(n)]
                received.extend(line.service_codec(samples, rate, True))
                total_seconds += n / rate
        assert line.rate_history == [7200, 7578.947368, 8000, 9600, 7200]
        assert abs(line.sent_samples - total_seconds * 10286) < 200
        assert line.input_overflow_samples == 0
        assert line.output_gap_samples == 0
        assert max(map(abs, received)) > 900
        assert len(received) > 10000
        assert all(hook == 1 for hook, _ in peer.requests)
        assert max(abs(s) for _, samples in peer.requests for s in samples) < 550
    finally:
        line.close()
        peer.close()


def test_default_gain_preserves_firmware_levels():
    peer = HardwarePeer()
    line = AppleLine('unused', rate=10286, transport=peer.client)
    samples = [-20000, -10000, 0, 10000, 20000] * 100
    try:
        line.service_codec(samples, 10286, True)
        pcm = [value for _, block in peer.requests for value in block]
        assert pcm == samples
        assert line.status()['tx_gain'] == 1.0
    finally:
        line.close()
        peer.close()


def test_on_hook_never_transmits_guest_audio():
    peer = HardwarePeer()
    line = AppleLine('unused', rate=10286, transport=peer.client)
    try:
        line.service_codec([2000]*500, 10286, False)
        pcm = [samples for _, samples in peer.requests if samples]
        assert pcm and all(not any(samples) for samples in pcm)
        assert line.peer_ringing
    finally:
        line.close()
        peer.close()


@pytest.mark.parametrize('kwargs', [{'bad_count': True}, {'overflow': True}, {'gaps': True}])
def test_bad_transport_fails_closed(kwargs):
    peer = HardwarePeer(**kwargs)
    line = AppleLine('unused', transport=peer.client)
    stopped = []
    line.on_error = lambda: stopped.append(True)
    try:
        with pytest.raises(RuntimeError):
            line.service_codec([0]*500, 10286, False)
        assert line.closed and line.error
        assert stopped == [True]
    finally:
        line.close()
        peer.close()


@pytest.mark.parametrize('kind', ['gaps', 'overflow'])
def test_terminal_callback_failure_preserves_counts_without_waiting_for_pcm(kind):
    peer = HardwarePeer(terminal_error=True, **{kind: True})
    line = AppleLine('unused', transport=peer.client)
    try:
        with pytest.raises(RuntimeError, match='underrun|overflow'):
            line.service_codec([0] * 500, 10286, False)
        assert line.closed
        status = line.status()
        assert status['output_gap_samples' if kind == 'gaps' else 'input_overflow_samples'] == 1
        assert line.received_samples == 0
    finally:
        line.close()
        peer.close()


def test_reset_control_and_hangup_do_not_need_pcm_or_a_codec_clock():
    peer = HardwarePeer()
    line = AppleLine('unused', transport=peer.client)
    try:
        tx, rx = line._tx, line._rx
        line.set_control(True, resetting=True)
        assert line.resetting and line._off_hook
        assert line._tx is not tx and line._rx is not rx
        assert line.frames == line.sent_samples == 0
        line.set_control(True, resetting=True)  # no duplicate control transaction
        assert len(peer.requests) == 1
        line._tx.convert = lambda *args: []
        assert line.service_codec([1], 7200, False) == []
        assert peer.requests == [(3, ()), (2, ())]
        assert not line._off_hook and line.resetting
        assert line.control_updates == 2 and line.frames == 0
    finally:
        line.close()
        peer.close()


def test_first_pcm_resumes_strict_mode_after_reset():
    peer = HardwarePeer()
    line = AppleLine('unused', transport=peer.client)
    try:
        line.set_control(True, resetting=True)
        line.service_codec([0]*500, 10286, True)
        assert peer.requests[0] == (3, ())
        assert peer.requests[1][0] == 1 and len(peer.requests[1][1]) == 500
        assert not line.resetting
        assert line.frames == 1 and line.control_updates == 1
        assert line.status()['off_hook_pcm_seconds'] == 500 / 10286
    finally:
        line.close()
        peer.close()


def test_bridge_control_runs_when_dsp_is_inactive_and_rate_is_zero():
    calls = []
    bridge = CourierDspBridge.__new__(CourierDspBridge)
    bridge.line = SimpleNamespace(codec_direct=True, connected=True, resetting=False,
        set_control=lambda hook, **kw: calls.append((hook, kw['resetting'])))
    bridge.daa = SimpleNamespace(off_hook=True)
    bridge.error = None
    bridge.active = bridge.launched = False
    bridge.boot_rom_enabled = True
    bridge.core = SimpleNamespace(codec_sample_rate=0)
    bridge.exchange = bridge.codec = None
    bridge._instructions = 0
    bridge.clock_x86(256)  # must service control before the inactive-DSP return
    bridge.daa.off_hook = False
    bridge.clock_x86(256)
    assert calls == [(True, True), (False, True)]


@pytest.mark.skipif(sys.platform != 'darwin', reason='CoreAudio helper needs macOS')
def test_hal_reset_silence_preserves_strict_underrun_and_watchdog(tmp_path):
    # This entry point only invokes callbacks and fake register IO. It must
    # neither enumerate USB nor start HAL, request mic permission or seize a line.
    root = Path(__file__).resolve().parents[1]
    v90 = root.parent / 'v90modem'
    if not (v90 / 'tools/apple_usb_modem_audio.m').exists():
        pytest.skip('v90modem audio utilities unavailable')
    import shutil
    if not shutil.which('pkg-config') or subprocess.run(
            ['pkg-config', '--exists', 'libusb-1.0']).returncode:
        pytest.skip('libusb build dependencies unavailable')
    from tools.build_apple_line import build
    helper = build(v90, tmp_path / 'apple-line')
    result = subprocess.run([str(helper), '--selftest'], text=True,
                            capture_output=True, check=True)
    import json
    report = json.loads(result.stdout)
    assert report == {'reset_silence_frames': 16, 'strict_underrun_detected': True,
                      'reset_watchdog_detected': True, 'generation_flush': True,
                      'hook_abort_release_verified': True,
                      'control_only_trial_verified': True,
                      'firmware_hook_protocol_verified': True,
                      'async_status_monitor_verified': True,
                      'explicit_shutdown_silence_verified': True}
    # Disarm failure, a write which took despite an error, readback mismatch,
    # OPD and cancellation release before diagnostic reads. A control-only
    # trial also exercises success, OPD, and refusal with OPE disabled.
    # The async monitor selftest blocks a mocked USB read while exercising
    # the actual producer status-dispatch path and HAL callback. A subsequent
    # OPD sample must release the firmware hook, retain protection, and mute.
    # Firmware-hook mocks check the exact USB setup packet and prohibit raw
    # hook assertion or host OPE disarm, including after a command error.
    assert result.stderr.count('release_verified=1 protection_restored=1') == 13
    assert 'stage=firmware-hook-command' in result.stderr
    assert 'stage=firmware-protection-readback' in result.stderr
    assert 'stage=prearm-current' in result.stderr
    assert 'stage=prearm-auxiliary' in result.stderr
    assert 'stage=protection-disarm' in result.stderr
    assert 'stage=hook-write-readback' in result.stderr
    assert 'stage=settling' in result.stderr
    # Invalid diagnostic requests must exit before USB/HAL enumeration.
    for options in (['invalid'], ['initialized', 'nan'], ['running', 'bad'],
                    ['stopped', '12000'], ['initialized', '7500'],
                    ['none', '10286', 'extra']):
        bad = subprocess.run([str(helper), '--seizure-test', *options],
                             text=True, capture_output=True)
        assert bad.returncode == 2
        assert 'usage:' in bad.stderr
        assert 'CDC' not in bad.stderr


def test_bridge_preserves_clock_events_without_8k_conversion():
    bridge = CourierDspBridge.__new__(CourierDspBridge)
    calls, queued = [], []
    bridge.core = SimpleNamespace(
        codec_sample_rate=9600,
        line_tx_writes=lambda: 400,
        line_tx_samples=lambda start: list(range(400)),
        line_tx_clock_events=lambda: [(0,7200), (200,9600)],
        queue_codec_rx=lambda samples: queued.extend(samples))
    bridge.line = SimpleNamespace(
        service_codec=lambda samples, rate, hook: calls.append((samples,rate,hook)) or samples,
        frames=2, connected=True)
    bridge.daa = SimpleNamespace(off_hook=True)
    bridge._exchange_tx_index = 0
    bridge._line_instructions = 0
    bridge._line_rx_peak = 0
    bridge.line_frame_budget = None
    bridge.batch = 4096
    bridge._service_physical_codec()
    assert [(len(s),r,h) for s,r,h in calls] == [(200,7200,True),(200,9600,True)]
    assert queued == list(range(400))
    assert bridge._exchange_tx_index == 400
    assert bridge.daa.line_state == 'quiet'


def test_dc_blocked_silence_does_not_mean_healthy_hardware_input():
    peer = HardwarePeer(rx_rail=True)
    line = AppleLine('unused', transport=peer.client)
    try:
        for _ in range(25):
            incoming = line.service_codec([0]*144, 7200, True)
        assert max(map(abs, incoming)) <= 1
        status = line.status()
        assert status['raw_rx_mean'] == -32768
        assert status['raw_rx_near_rail_samples'] == status['samples_received']
    finally:
        line.close()
        peer.close()


def test_native_receive_keeps_hardware_clock_and_does_not_resample_twice():
    peer = HardwarePeer()
    line = AppleLine('unused', transport=peer.client)
    try:
        line.enable_native_receive()
        incoming = line.service_codec([0]*144, 7200, True)
        assert len(incoming) == line.sent_samples == line.received_samples
        assert len(incoming) >= 205  # hardware samples, NOT 144 codec samples
        assert line.status()['native_receive']
    finally:
        line.close()
        peer.close()


def test_cli_routes_hardware_without_synthetic_line(monkeypatch):
    monkeypatch.setattr('courier_emu.cli.load_image', lambda *a, **kw:
                        SimpleNamespace(path='test.rom', dsp_program_segments=[]))
    args = build_parser().parse_args(['run','test.rom','--apple-modem','--apple-rate','9600'])
    command = _worker_command(args)
    assert '--apple-modem' in command
    assert command[command.index('--apple-rate')+1] == '9600'
    assert command[command.index('--daa-line')+1] == 'quiet'
    assert command[command.index('--apple-tx-gain')+1] == '1.0'
    args.apple_tx_gain = 0.25  # intentional attenuation remains available
    attenuated = _worker_command(args)
    assert attenuated[attenuated.index('--apple-tx-gain')+1] == '0.25'
    # Preserve the optimized ROM worker's scheduling defaults; don't force
    # a large batch or the different DSP tick source for physical audio.
    assert '--dsp-batch' not in command
    assert '--tick-source' not in command
    assert '--with-dsp' in command
    for option in ('--exchange', '--line-link', '--sip-server', '--force-online'):
        assert option not in command
    args.exchange = True
    with pytest.raises(ValueError):
        _worker_command(args)


def test_preflight_finishes_before_a_helper_is_started(monkeypatch):
    from courier_emu import resample as rs
    # Native dependency setup may invoke the compiler; allow it before the
    # helper-spawn guard. No USB, microphone or HAL code runs in this test.
    rs.prepare_resampling(7200, 10286, retuned=True)

    def forbidden(*args, **kwargs):
        pytest.fail('helper started during filter preparation')

    monkeypatch.setattr('courier_emu.apple_line.subprocess.Popen', forbidden)
    line = AppleLine('unused')
    assert not line.connected and line._process is None
    assert 8641.23446206601 in line.prepared_codec_rates
    assert 9600 in line.prepared_codec_rates
    for rate in line.prepared_codec_rates:
        assert rs.resampling_prepared(rate, line.rate, retuned=True)
        assert rs.resampling_prepared(line.rate, rate)
    assert line._tx.input_rate == line._rx.input_rate == 0


def test_live_training_retunes_and_reset_never_construct_filters(monkeypatch):
    from courier_emu import resample as rs
    peer = HardwarePeer()
    line = AppleLine('unused', transport=peer.client)

    def forbidden(*args, **kwargs):
        pytest.fail('cold filter/native-library work on the active audio path')

    monkeypatch.setattr(rs, '_kernel', forbidden)
    monkeypatch.setattr('courier_emu.dsp.load_library', forbidden)
    sequence = [(7200, 1440), (7200, 43), (8641.23446206601, 1),
                (9600, 151), (9600, 193), (10266.666667, 206)]
    try:
        for _ in range(2):
            for rate, count in sequence:
                line.service_codec([0]*count, rate, True)
            line.set_control(True, resetting=True)  # fresh converter instances
        assert not line.live_filter_misses
        assert line.control_updates >= 2
    finally:
        line.close()
        peer.close()


def test_unprepared_active_clock_fails_closed_without_building_filters(monkeypatch):
    from courier_emu import resample as rs
    peer = HardwarePeer()
    line = AppleLine('unused', transport=peer.client)
    unknown = 7777.0
    key = round(rs.CUTOFF * unknown / 2 / line.rate, 9)
    monkeypatch.setattr(rs, '_KERNELS', {k: v for k, v in rs._KERNELS.items() if k != key})

    def forbidden(*args, **kwargs):
        pytest.fail('unprepared active clock triggered a cold filter build')

    monkeypatch.setattr(rs, '_kernel', forbidden)
    stopped = []
    line.on_error = lambda: stopped.append(True)
    try:
        line.set_control(True)
        with pytest.raises(RuntimeError, match='unprepared Apple codec rate'):
            line.service_codec([0]*156, unknown, True)
        assert line.closed and line.live_filter_misses == [unknown]
        assert stopped == [True]
    finally:
        line.close()
        peer.close()


def test_additional_clock_can_be_prepared_before_seizure(monkeypatch):
    from courier_emu import resample as rs
    peer = HardwarePeer()
    line = AppleLine('unused', transport=peer.client, codec_rates=(7777.,))

    def forbidden(*args, **kwargs):
        pytest.fail('cold filter build after explicit rate preparation')

    monkeypatch.setattr(rs, '_kernel', forbidden)
    try:
        line.service_codec([0]*156, 7777., True)
        assert 7777. in line.prepared_codec_rates
        assert not line.live_filter_misses
        with pytest.raises(RuntimeError, match='before seizing'):
            line.prepare_codec_rates((7888.,))
    finally:
        line.close()
        peer.close()
