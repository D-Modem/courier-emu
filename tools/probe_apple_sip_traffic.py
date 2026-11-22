#!/usr/bin/env python3
"""One bounded V.32/LAPM call with exact sustained duplex DTE traffic.

Uses the established Apple -> PBX extension 2903 -> native I-modem path.
No firmware state, carrier, decoded bytes or ACKs are injected. Binary mode
requires 8N1 and disables terminal control-byte translation. Private output.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from courier_emu.cli import build_parser, _worker_command
from tools.apple_sip_profiles import settings
from tools.apple_traffic import ReceiveStream, record, verify_saved
from tools.capture_apple_sip import modem_status
from tools.apple_traffic_telemetry import Client as TelemetryClient, summarize as summarize_telemetry

CONNECT = re.compile(rb'(?:^|\r\n)(CONNECT[^\r\n]*)\r\n')


class Endpoint:
    def __init__(self, name, role, reader, writer, directory, binary):
        self.name, self.role = name, role
        self.reader, self.writer = reader, writer
        os.set_blocking(reader, False)
        os.set_blocking(writer, False)
        self.raw = (directory / f'{name}-dte.bin').open('xb')
        self.received = (directory / f'{name}-received.bin').open('xb')
        self.sent = (directory / f'{name}-sent.bin').open('xb')
        self.command = bytearray()
        self.connect = None
        self.connected_at = None
        self.queued = bytearray()
        self.count = 0
        self.stream = ReceiveStream('I' if role == 'A' else 'A', binary=binary)

    def read(self, now):
        try:
            data = os.read(self.reader, 65536)
        except BlockingIOError:
            return
        if not data:
            raise RuntimeError(f'{self.name}: DTE closed before test completed')
        self.raw.write(data)
        if self.connect is None:
            self.command.extend(data)
            if len(self.command) > 65536:
                raise RuntimeError(f'{self.name}: CONNECT preamble exceeds bound')
            match = CONNECT.search(self.command)
            if match is None:
                return
            self.connect = match.group(1).decode('ascii')
            self.connected_at = now
            data = bytes(self.command[match.end():])
        if data:
            self.received.write(data)
            self.stream.feed(data, now)

    def flush(self):
        if not self.queued:
            return
        try:
            n = os.write(self.writer, self.queued)
        except BlockingIOError:
            return
        del self.queued[:n]

    def queue_record(self, binary):
        value = record(self.role, self.count, binary=binary)
        self.sent.write(value)
        self.queued.extend(value)
        self.count += 1

    def close_files(self):
        for stream in (self.raw, self.received, self.sent):
            stream.close()


def report(path):
    text = path.read_text()
    at = text.rfind('\n{')
    return json.loads(text[at + 1:] if at >= 0 else text)


def stop(process):
    if process is None:
        return
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def receiver_diagnostics(process, directory):
    """Read actual carrier loss, then query ATI6 through the ordinary DTE.

    This is after the frozen traffic/drain window and after the analog caller
    exited/released. Never send an AT command into an online data stream.
    """
    data = bytearray()
    queried = False
    deadline = time.monotonic() + 10
    with (directory / 'post-call-diagnostics.bin').open('xb') as log:
        while process.poll() is None and time.monotonic() < deadline:
            try:
                chunk = os.read(process.stdout.fileno(), 65536)
            except BlockingIOError:
                chunk = None
            if chunk == b'': break
            if chunk:
                data.extend(chunk)
                log.write(chunk)
            if not queried and b'\r\nNO CARRIER\r\n' in data:
                os.write(process.stdin.fileno(), b'ATI6\r')
                queried = True
                data.clear()
            if queried and b'\r\nOK\r\n' in data: break
            time.sleep(.01)
    return dict(queried=queried, complete=queried and b'\r\nOK\r\n' in data)


def online_diagnostics(reader, writer, path):
    """After freezing the traffic/drain verdict, use guarded +++ then ATI6.

    The diagnostic bytes/results are kept separate from measured payloads.
    An observed firmware OK is mandatory before issuing ATI6.
    """
    with path.open('xb') as log:
        time.sleep(1.2)  # Ordinary S12 guard; do not alter firmware timers.
        os.write(writer, b'+++')
        data = bytearray()
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            try:
                chunk = os.read(reader, 65536)
            except BlockingIOError:
                chunk = None
            if chunk == b'': return dict(escaped=False, reason='DTE closed')
            if chunk:
                log.write(chunk)
                data.extend(chunk)
            if b'\r\nOK\r\n' in data: break
            time.sleep(.01)
        else:
            return dict(escaped=False, reason='no firmware escape OK; ATI6 not sent')
        os.write(writer, b'ATI6\r')
        data.clear()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                chunk = os.read(reader, 65536)
            except BlockingIOError:
                chunk = None
            if chunk == b'': break
            if chunk:
                log.write(chunk)
                data.extend(chunk)
            if b'\r\nOK\r\n' in data: return dict(escaped=True, complete=True)
            time.sleep(.01)
        return dict(escaped=True, complete=False)


def command_plan():
    preset = settings('v32-lapm')
    plan = dict(receiver=['AT*V2=3', 'AT&W', 'ATS0=1' + preset + 'S2=43&I0'],
                caller_setup='ATS2=43&I0',
                caller_dial='ATX1S27=1' + preset + 'S7=45DT2903')
    if any(len(command) >= 64 for command in [*plan['receiver'], plan['caller_setup'], plan['caller_dial']]):
        raise ValueError('AT command would overflow the firmware command buffer')
    return plan


def transport_plan(environ):
    frames = int(environ.get('APPLE_MODEM_BUFFER_FRAMES', '0') or '0')
    if frames != 0 and not 4 <= frames <= 4096:
        raise ValueError('APPLE_MODEM_BUFFER_FRAMES must be 0 or 4..4096')
    async_status = environ.get('APPLE_LINE_ASYNC_STATUS', '0')
    if async_status not in ('0', '1'):
        raise ValueError('APPLE_LINE_ASYNC_STATUS must be 0 or 1')
    raw_gain = environ.get('APPLE_POST_DIAL_GAIN')
    post_dial_gain = float(raw_gain) if raw_gain is not None else None
    if post_dial_gain is not None and not 0 <= post_dial_gain <= 1:
        raise ValueError('APPLE_POST_DIAL_GAIN must be 0..1')
    service_seconds = .005 if 0 < frames <= 128 else .02
    # Keep the same 320-second transport backstop at either service cadence.
    # A fixed 16000-frame cap shrank to 80 seconds in the 5-ms mode.
    return dict(buffer_frames_requested=frames, codec_service_seconds=service_seconds,
                async_status_requested=async_status == '1', post_dial_tx_gain=post_dial_gain,
                max_line_frames=round(320 / service_seconds), backstop_seconds=320)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seconds', type=float, default=60)
    parser.add_argument('--binary', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.seconds <= 120:
        parser.error('--seconds must be 1..120')
    try:
        transport = transport_plan(os.environ)
    except ValueError as exc:
        parser.error(str(exc))
    os.umask(0o077)
    out = args.output.resolve()
    out.mkdir(parents=True, mode=0o700, exist_ok=False)
    (out / 'transport-settings.json').write_text(json.dumps(transport, indent=2) + '\n')
    helper = str(ROOT / '.build/apple_line')
    initial = modem_status(helper)
    (out / 'initial-status.log').write_text(initial['stderr'])
    (out / 'initial-status.json').write_text(initial['stdout'])
    if initial['returncode'] or json.loads(initial['stdout'])['hook'] & 1:
        raise RuntimeError('on-hook not verified; not dialing')
    auth = subprocess.check_output(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8',
        'root@asterisk.net.cryan.nz',
        "sed -n '/^\\[auth2903\\]/,/^\\[/p' /etc/asterisk/pjsip.conf"], text=True, timeout=15)
    credentials = dict(line.split('=', 1) for line in auth.splitlines() if '=' in line)
    env = dict(os.environ, COURIER_SIP_PASSWORD=credentials['password'].strip())
    shutil.copyfile(ROOT / 'artifacts/real-courier-inbound/nvram.sav', out / 'nvram.sav')
    # Ordinary volatile firmware settings: no software flow control, standard
    # guarded escape (used only after the frozen window and full drain).
    # One outstanding record bounds UART queues.
    commands = command_plan()
    (out / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')
    receiver_command = [sys.executable, '-m', 'tools.apple_traffic_telemetry', 'isdn-run', 'Ie030002.nac',
        '--with-dsp', '--flash-nvram', str(out / 'nvram.sav'), '--bri-call-to', '7349195',
        '--terminal', '--terminal-binary', '--no-local-echo', '--report',
        '--bri-network', '--bri-establish', 'terminal', '--bri-sip', 'asterisk.net.cryan.nz',
        '--bri-sip-username', '2903', '--bri-sip-register', '--bri-sip-local-port', '5062',
        '--bri-sip-buffer-ms', '200', '--bri-sip-rtp-delay-ms', '200',
        '--bri-sip-record', str(out / 'apple-to-imodem.g711'),
        '--bri-tx-g711', str(out / 'imodem-to-apple.g711'),
        '--bri-rx-heard', str(out / 'imodem-heard.g711')]
    receiver = caller = None
    telemetry = control = child_control = None
    drain_snapshot = None
    drain_end_at = None
    link = child_link = None
    endpoints = {}
    failure = None
    window = None
    start = end = None
    with (out / 'receiver-report.log').open('w') as receiver_log, \
         (out / 'caller-report.json').open('wb') as caller_report, \
         (out / 'caller-hardware.log').open('w') as caller_log, \
         (out / 'events.jsonl').open('w') as events:
        try:
            control, child_control = socket.socketpair()
            telemetry = TelemetryClient(control)
            receiver_env = dict(env, APPLE_TRAFFIC_TELEMETRY_FD=str(child_control.fileno()))
            receiver = subprocess.Popen(receiver_command, cwd=ROOT, env=receiver_env,
                pass_fds=(child_control.fileno(),),
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=receiver_log)
            child_control.close()
            child_control = None

            def snapshot(phase):
                value = telemetry.capture(phase)
                if value is None:
                    raise RuntimeError(f'receiver media telemetry failed at {phase}')
                return value

            imodem = Endpoint('imodem', 'I', receiver.stdout.fileno(), receiver.stdin.fileno(), out, args.binary)
            endpoints['imodem'] = imodem

            def pump():
                now = time.monotonic()
                for endpoint in endpoints.values():
                    endpoint.flush()
                    before = endpoint.stream.records
                    endpoint.read(now)
                    if endpoint.stream.records != before:
                        events.write(json.dumps(dict(event='received', side=endpoint.name,
                            time=now, records=endpoint.stream.records)) + '\n')
                    if endpoint.connect is None and any(code in endpoint.command for code in
                            (b'\r\nERROR\r\n', b'\r\nNO CARRIER\r\n', b'\r\nNO DIAL TONE\r\n', b'\r\nBUSY\r\n')):
                        raise RuntimeError(f'{endpoint.name}: firmware rejected command or call: {bytes(endpoint.command)!r}')
                    if endpoint.stream.error:
                        raise RuntimeError(f'{endpoint.name}: corrupt traffic {endpoint.stream.error}')
                if any(p is not None and p.poll() is not None for p in (receiver, caller)):
                    raise RuntimeError('modem process exited during observation')
                return now

            def wait(predicate, seconds, label):
                deadline = time.monotonic() + seconds
                while time.monotonic() < deadline:
                    pump()
                    if predicate(): return
                    time.sleep(.005)
                raise TimeoutError(label)

            wait(lambda: '[command port ready]' in (out / 'receiver-report.log').read_text(), 30, 'receiver readiness')
            snapshot('ready')
            for index, at in enumerate(commands['receiver'], 1):
                imodem.queued.extend((at + '\r').encode('ascii'))
                wait(lambda: bytes(imodem.command).count(b'\r\nOK\r\n') >= index, 25, f'receiver {at}')
            deadline = time.monotonic() + 45
            while True:
                contact = subprocess.check_output(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8',
                    'root@asterisk.net.cryan.nz', 'asterisk -rx "pjsip show contacts"'], text=True, timeout=15)
                (out / 'contacts-before.log').write_text(contact)
                if any('2903/sip:2903@' in line and 'Avail' in line.split() for line in contact.splitlines()): break
                if time.monotonic() >= deadline: raise RuntimeError('receiver not reachable; not dialing')
                pump()
                time.sleep(1)
            snapshot('pre_dial')
            link, child_link = socket.socketpair()
            cli = build_parser().parse_args(['run',
                str(ROOT / 'dumps/courier-board-21210-capture-403/courier-board.rom'),
                '--apple-modem', '--nvram-fixture', 'idsdl403', '--board-id', '7', '--tick-ms', '5',
                '--at', commands['caller_setup'], '--serial-input-after', '5000000',
                '--instructions', '2000000000', '--line-frames', str(transport['max_line_frames']), '--summary'])
            command = _worker_command(cli)
            caller_env = dict(os.environ, APPLE_CALL_TRACE=str(out / 'codec'),
                              APPLE_CALL_DIAGNOSTICS='1', APPLE_STOP_AFTER_CONNECT_SECONDS='0')
            caller = subprocess.Popen([command[0], str(ROOT / 'artifacts/apple-dial-extensions/trace_worker.py'),
                *command[3:], '--serial-fd', str(child_link.fileno())], cwd=ROOT, env=caller_env,
                pass_fds=(child_link.fileno(),), stdout=caller_report, stderr=caller_log)
            child_link.close()
            child_link = None
            apple = Endpoint('apple', 'A', link.fileno(), link.fileno(), out, args.binary)
            endpoints['apple'] = apple
            # Keep the normal firmware's command line below its bounded AT
            # buffer. Setup plus dial in one line was 66 bytes and got ERROR.
            wait(lambda: b'\r\nOK\r\n' in apple.command, 25, 'caller setup OK')
            # Keep the already-validated modulation preset and dial in the
            # same firmware transaction; the short first command sets only
            # binary transport controls, avoiding the 66-byte combined line.
            apple.queued.extend((commands['caller_dial'] + '\r').encode('ascii'))
            events.write(json.dumps(dict(event='dial_requested', time=time.monotonic(), extension='2903')) + '\n')
            wait(lambda: all(ep.connect for ep in endpoints.values()), 65, 'both CONNECT results')
            if 'LAPM' not in apple.connect or 'ARQ' not in imodem.connect:
                raise RuntimeError('required error correction was not established')
            snapshot('pre_traffic')
            start = time.monotonic() + .5
            end = start + args.seconds
            for ep in endpoints.values(): ep.stream.start(start)
            last_progress = start
            while True:
                now = pump()
                if now >= end and window is None:
                    window = dict(elapsed_seconds=now-start,
                                  **{name: ep.stream.status(now) for name, ep in endpoints.items()})
                    snapshot('traffic_end')
                if window is None and now >= start:
                    for name, ep in endpoints.items():
                        remote = endpoints['imodem' if name == 'apple' else 'apple']
                        if not ep.queued and ep.count == remote.stream.records:
                            ep.queue_record(args.binary)
                            events.write(json.dumps(dict(event='sent', side=name, time=now,
                                                        records=ep.count)) + '\n')
                if now >= last_progress + 1:
                    events.write(json.dumps(dict(event='progress', time=now,
                        receive={name: ep.stream.status(now) for name, ep in endpoints.items()})) + '\n')
                    events.flush()
                    last_progress = now
                if window is not None:
                    drained = all(ep.count == endpoints['imodem' if name == 'apple' else 'apple'].stream.records
                                  and not ep.queued and not ep.stream.pending for name, ep in endpoints.items())
                    if drained: break
                    if now >= end + 5: raise RuntimeError('final records failed to drain within five seconds')
                time.sleep(.005)
        except Exception as exc:
            failure = str(exc)
        finally:
            # Freeze the drain evidence BEFORE diagnostics/teardown. Previously
            # its open-gap timestamps accidentally included cleanup time.
            drain_end_at = time.monotonic()
            drain_snapshot = {name: ep.stream.status(drain_end_at) for name, ep in endpoints.items()}
            if telemetry is not None and window is not None:
                telemetry.capture('pre_diagnostics')
            # The drain deadline/failure is already frozen: even when a tail
            # stalled, read real counters before hanging up. Late payload and
            # diagnostics go ONLY to separate files and cannot repair a failed
            # window, missing tail, hash or event count.
            if window is not None and len(endpoints) == 2:
                diagnostics = {}
                for name, ep in endpoints.items():
                    try:
                        diagnostics[name] = online_diagnostics(ep.reader, ep.writer,
                            out / f'{name}-online-diagnostics.bin')
                    except Exception as exc:
                        diagnostics[name] = dict(error=str(exc))
                    if telemetry is not None:
                        telemetry.capture(name + '_diagnostics_done')
                (out / 'online-diagnostics.json').write_text(json.dumps(diagnostics, indent=2) + '\n')
            # EOF is the documented binary-console stop; the analog console
            # also observes EOF. No embedded payload byte acts as a detach.
            if link is not None:
                try: link.shutdown(socket.SHUT_WR)
                except OSError: pass
            stop(caller)
            if receiver is not None and receiver.stdin is not None:
                try:
                    diagnostic = (receiver_diagnostics(receiver, out)
                                  if endpoints.get('imodem') and endpoints['imodem'].connect
                                  else dict(queried=False, reason='no established carrier'))
                except Exception as exc:
                    diagnostic = dict(error=str(exc))
                (out / 'post-call-diagnostics.json').write_text(json.dumps(diagnostic, indent=2) + '\n')
                if telemetry is not None:
                    telemetry.capture('post_hangup')
                receiver.stdin.close()
            stop(receiver)
            if child_control is not None: child_control.close()
            if control is not None: control.close()
            if child_link is not None: child_link.close()
            if link is not None: link.close()
            for ep in endpoints.values(): ep.close_files()
    metadata = dict(seconds=args.seconds, binary=args.binary, record_size=256,
                    clock='parent monotonic seconds after both CONNECT results, plus 0.5s warmup',
                    start=start, end=end, window=window,
                    sent_records={name: ep.count for name, ep in endpoints.items()},
                    drain=drain_snapshot, drain_end_at=drain_end_at,
                    connect={name: ep.connect for name, ep in endpoints.items()},
                    exit_codes=dict(caller=caller.returncode if caller else None,
                                    receiver=receiver.returncode if receiver else None), failure=failure)
    (out / 'traffic.json').write_text(json.dumps(metadata, indent=2) + '\n')
    final = modem_status(helper)
    (out / 'final-status.json').write_text(final['stdout'])
    (out / 'final-status.log').write_text(final['stderr'])
    media = dict(snapshots=telemetry.snapshots if telemetry else [],
                 errors=telemetry.errors if telemetry else [dict(error='receiver telemetry not started')])
    try:
        media['intervals'] = summarize_telemetry(media['snapshots'])
    except (KeyError, TypeError, ValueError) as exc:
        media['errors'].append(dict(error=str(exc)))
    (out / 'media-telemetry.json').write_text(json.dumps(media, indent=2) + '\n')
    verification = dict(passed=False, error=failure, media_intervals=media.get('intervals'),
                        media_telemetry_errors=media['errors'])
    try:
        if failure: raise AssertionError(failure)
        if media['errors']: raise AssertionError('receiver media telemetry incomplete/invalid')
        if any(code != 0 for code in metadata['exit_codes'].values()): raise AssertionError('process exit failure')
        verification['streams'] = verify_saved(out, metadata=metadata)
        analog = json.loads((out / 'caller-report.json').read_text())
        digital = report(out / 'receiver-report.log')
        if analog['error'] or analog['dsp_bridge']['error'] or digital['error']:
            raise AssertionError('CPU/DSP/line error')
        if digital['dte_framing'] != '8N1': raise AssertionError('I-modem DTE is not 8N1')
        line = analog['dsp_bridge']['line']
        if line['output_gap_samples'] or line['input_overflow_samples']: raise AssertionError('active USB sample loss')
        if analog['console']['dropped']: raise AssertionError('analog terminal output dropped')
        if any(s['overruns'] or s['output_dropped'] for s in digital['serial'].values()):
            raise AssertionError('I-modem UART overrun/output drop')
        playout = digital['bri']['media_peer']['sip']['rtp_receive']['playout']
        if any(playout[k] for k in ('missing_samples', 'late_packets', 'out_of_window_packets',
                                    'overlap_packets', 'rejected_sources', 'rejected_ssrc')):
            raise AssertionError('RTP playout discontinuity or rejected media')
        if final['returncode'] or json.loads(final['stdout'])['hook'] & 1 or not json.loads(final['stdout'])['protection_register'] & 8:
            raise AssertionError('final hook/protection not verified')
        verification.update(passed=True, error=None, rtp_playout=playout,
            payload_bytes_per_second={side: window[side]['records'] * 256 / args.seconds for side in window if side != 'elapsed_seconds'})
    except Exception as exc:
        verification['error'] = str(exc)
    (out / 'traffic-verification.json').write_text(json.dumps(verification, indent=2) + '\n')
    print(json.dumps(verification, indent=2))
    return 0 if verification['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
