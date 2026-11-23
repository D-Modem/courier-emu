#!/usr/bin/env python3
"""Preflight, or explicitly run one Apple/V.32-LAPM call with dual RTP captures.

No PBX configuration changes. Requires the original Apple 05ac:1401 device,
verified on-hook, local BPF access, SSH and tcpdump. Default is preflight only.
Captures may contain SIP credentials/audio: output is private (0700 directory).
"""
import argparse
import json
import os
from pathlib import Path
import re
import shlex
import signal
import socket
import subprocess
import sys
import time
import uuid
import ipaddress

ROOT = Path(__file__).resolve().parents[1]


def run(command, *, timeout=15):
    try:
        p = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {'command': command, 'returncode': -1, 'stdout': '', 'stderr': str(exc)}
    return {'command': command, 'returncode': p.returncode,
            'stdout': p.stdout, 'stderr': p.stderr}


def ssh(host, command):
    return ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', host, command]


def modem_status(helper):
    # Do not even open USB while a known sibling hardware experiment is
    # running. This advisory check is not a lock; libusb's exclusive interface
    # claim remains the race-safe gate. Never detach/kill the other owner.
    processes = run(['ps', '-axo', 'pid=,comm='])
    owners = []
    for line in processes['stdout'].splitlines():
        fields = line.strip().split(None, 1)
        if len(fields) == 2:
            name = Path(fields[1]).name
            if name == 'apple_line' or name.startswith('apple_usb_modem_'):
                owners.append(line.strip())
    if processes['returncode'] or owners:
        return dict(command=[helper, '--status'], returncode=1, stdout='',
                    stderr='USB owner check failed or another modem test is running', owners=owners)
    return run([helper, '--status'])


def on_hook(result):
    if result['returncode']:
        return False
    try:
        return not (json.loads(result['stdout'])['hook'] & 1)
    except (KeyError, TypeError, ValueError):
        return False


def remote_capture_filter(local, peers=()):
    addresses = list(dict.fromkeys(str(ipaddress.IPv4Address(ip)) for ip in [local, *peers]))
    hosts = ' or '.join('host ' + ip for ip in addresses)
    return 'udp and ' + (hosts if len(addresses) == 1 else '(' + hosts + ')')


def capture_stats(text):
    fields = {label: int(value) for value, label in re.findall(
        r'^(\d+) packets (captured|received by filter|dropped by kernel)\s*$', text, re.M)}
    return {'counters': fields, 'verified_no_kernel_drops':
            fields.get('captured', 0) > 0 and fields.get('dropped by kernel') == 0}


def save(path, value):
    with path.open('x') as stream:
        stream.write(json.dumps(value, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='new, private evidence directory')
    parser.add_argument('--pbx', default='asterisk.net.cryan.nz')
    parser.add_argument('--ssh-host', default='root@asterisk.net.cryan.nz')
    parser.add_argument('--remote-interface', default='eth0')
    parser.add_argument('--remote-peer', action='append', default=[],
                        type=lambda value: str(ipaddress.IPv4Address(value)),
                        help='also capture this ATA/gateway IPv4 leg at PBX (repeatable); local capture unchanged')
    parser.add_argument('--run-call', action='store_true', help='explicitly dial extension 2903 once')
    parser.add_argument('--traffic-seconds', type=float, default=0,
                        help='bounded sustained traffic instead of the 180-byte control (1..120 seconds)')
    parser.add_argument('--traffic-binary', action='store_true', help='use all-octet exact traffic records')
    args = parser.parse_args()
    if args.traffic_seconds != 0 and not 1 <= args.traffic_seconds <= 120:
        parser.error('--traffic-seconds must be 1..120')
    if args.traffic_binary and not args.traffic_seconds:
        parser.error('--traffic-binary requires --traffic-seconds')
    # The historical call launcher has a fixed PBX/extension. Do not pretend
    # custom capture targets also change the live call target.
    if args.run_call and (args.pbx != 'asterisk.net.cryan.nz'
                          or args.ssh_host != 'root@asterisk.net.cryan.nz'):
        parser.error('live launcher supports only the established test PBX')
    os.umask(0o077)
    out = args.output.resolve()
    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    helper = str(ROOT / '.build/apple_line')
    preflight = {'modem': modem_status(helper)}
    address = socket.gethostbyname(args.pbx)
    route = run(['route', '-n', 'get', address])
    preflight['route'] = route
    match = re.search(r'^\s*interface:\s*(\S+)', route['stdout'], re.M)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.connect((address, 5060))
        local = probe.getsockname()[0]
    preflight.update(pbx_address=address, local_address=local, remote_peers=args.remote_peer,
                     interface=match.group(1) if match else None)
    preflight['pbx'] = run(ssh(args.ssh_host,
        'command -v tcpdump && command -v timeout && ip -s link && cat /proc/net/snmp'))
    preflight['udp'] = run(['netstat', '-s', '-p', 'udp'])
    save(out / 'preflight.json', preflight)
    if not on_hook(preflight['modem']):
        print('BLOCKED: original Apple modem missing or on-hook not verified; no call made.', file=sys.stderr)
        return 2
    if not match or route['returncode'] or preflight['pbx']['returncode']:
        print('BLOCKED: route/PBX capture preflight failed; no call made.', file=sys.stderr)
        return 2
    if not args.run_call:
        print(f'Preflight passed; no call made. Evidence: {out}')
        return 0
    token = uuid.uuid4().hex
    pidfile = f'/tmp/courier-rtp-{token}.pid'
    remote_filter = shlex.quote(remote_capture_filter(local, args.remote_peer))
    # Timeout is a backstop if SSH/control cleanup fails. PID is only for this
    # capture; never kill unrelated tcpdump processes. The shell reaps it.
    remote_command = (
        f'timeout -s INT 420 tcpdump -U -n -i {shlex.quote(args.remote_interface)} '
        f'-s 0 -w - {remote_filter} & p=$!; echo "$p" > {pidfile}; '
        f'wait "$p"; rc=$?; rm -f {pidfile}; exit "$rc"')
    local_command = ['tcpdump', '-U', '-n', '-i', match.group(1), '-s', '0',
                     '-w', str(out / 'local.pcap'), f'udp and host {address}']
    processes = []
    outcome = {'call_started': False, 'call_returncode': None}
    try:
        with (out / 'local-tcpdump.log').open('w') as local_log, \
             (out / 'pbx-tcpdump.log').open('w') as remote_log, \
             (out / 'pbx.pcap').open('wb') as capture:
            try:
                processes.append(subprocess.Popen(local_command, stderr=local_log))
                processes.append(subprocess.Popen(ssh(args.ssh_host, remote_command),
                                                   stdout=capture, stderr=remote_log))
                deadline = time.monotonic() + 12
                while True:
                    if any(p.poll() is not None for p in processes):
                        raise RuntimeError('capture exited before call; see tcpdump logs')
                    if all('listening on ' in (out / name).read_text()
                           for name in ('local-tcpdump.log', 'pbx-tcpdump.log')):
                        break
                    if time.monotonic() >= deadline:
                        raise TimeoutError('capture readiness timeout; not dialing')
                    time.sleep(.1)
                # Recheck immediately before allowing the fixed extension call.
                status = modem_status(helper)
                save(out / 'before-dial.json', status)
                if not on_hook(status):
                    raise RuntimeError('on-hook verification failed; not dialing')
                outcome['call_started'] = True
                command = [sys.executable, str(ROOT / 'artifacts/apple-courier-sip/run.py'),
                           '--protocol', 'v32-lapm', '--payload-test', '--payload-size', '180',
                           '--rtp-delay-ms', '200',
                           '--carrier-wait', '45', '--frames', '4500',
                           '--instructions', '550000000', '--timeout', '115',
                           '--output', str(out / 'call')]
                if args.traffic_seconds:
                    command = [sys.executable, str(ROOT / 'tools/probe_apple_sip_traffic.py'),
                               '--seconds', str(args.traffic_seconds), '--output', str(out / 'call')]
                    if args.traffic_binary:
                        command.append('--binary')
                # The existing launcher bounds and releases its own children.
                # Do not add an outer kill timeout that could orphan a hook owner.
                with (out / 'call.log').open('w') as log:
                    outcome['call_returncode'] = subprocess.call(command, cwd=ROOT,
                                                                 stdout=log, stderr=log)
                outcome['capture_alive_after_call'] = all(p.poll() is None for p in processes)
            finally:
                outcome['remote_stop'] = run(ssh(args.ssh_host,
                    f'if test -f {pidfile}; then kill -INT "$(cat {pidfile})"; fi'))
                if processes and processes[0].poll() is None:
                    processes[0].send_signal(signal.SIGINT)
                for p in processes:
                    try:
                        p.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        p.terminate()
                        try:
                            p.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            p.kill()
                            p.wait()
                outcome['capture_returncodes'] = [p.returncode for p in processes]
        outcome['capture_stats'] = {
            name: capture_stats((out / name).read_text())
            for name in ('local-tcpdump.log', 'pbx-tcpdump.log')}

    except Exception as exc:
        outcome['error'] = str(exc)
    finally:
        outcome['final_modem'] = modem_status(helper)
        outcome['final_udp'] = run(['netstat', '-s', '-p', 'udp'])
        outcome['final_pbx'] = run(ssh(args.ssh_host, 'ip -s link; cat /proc/net/snmp'))
        save(out / 'outcome.json', outcome)
    good = (outcome.get('call_returncode') == 0 and on_hook(outcome['final_modem'])
            and outcome.get('capture_alive_after_call') and not outcome.get('error')
            and all(row['verified_no_kernel_drops']
                    for row in outcome.get('capture_stats', {}).values())
            and len(outcome.get('capture_stats', {})) == 2)
    print(f'{"PASS" if good else "FAIL"}: {out}')
    return 0 if good else 2


if __name__ == '__main__':
    raise SystemExit(main())
