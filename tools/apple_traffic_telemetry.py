"""Read-only, request/response media snapshots on a separate harness socket.

No telemetry command or response is sent through a modem DTE, SIP or RTP.
Snapshots run on the receiver's existing console-pump thread. They do not poll,
advance clocks, read consume-on-read peripherals, or modify firmware state.
"""
import json
import math
import select
import socket
import time

LIMIT = 65536
PLAYOUT_COUNTERS = ('missing_samples', 'late_packets', 'out_of_window_packets',
                    'overlap_packets', 'rejected_sources', 'rejected_ssrc', 'played_samples')


def collect(machine):
    bri = machine.bri
    session = bri.media_peer.session
    with session._rtp_lock:
        playout = session._rtp_playout.status()
        receive = session._rtp_rx_stats.status()
        sent = session.rtp_octets_sent
        received = session.rtp_octets_received
    native = machine._native_io
    return dict(time=time.monotonic(), instructions=machine.instructions,
                call_state=bri.call_state, sip_state=session.state,
                dte_framing=machine.dte_framing(), playout=playout,
                rtp_receive=receive, rtp_octets_sent=sent, rtp_octets_received=received,
                native_clock=native.clock_stats() if native is not None else {})


class Server:
    def __init__(self, channel, snapshot=collect):
        self.channel = channel
        self.channel.setblocking(False)
        self.snapshot = snapshot
        self.incoming = bytearray()
        self.outgoing = bytearray()
        self.closed = False

    def poll(self, machine):
        if self.closed:
            return
        try:
            chunk = self.channel.recv(4096)
        except BlockingIOError:
            chunk = None
        if chunk == b'':
            self.closed = True
            return
        if chunk:
            self.incoming.extend(chunk)
        if len(self.incoming) > LIMIT:
            raise RuntimeError('telemetry request exceeds bound')
        while b'\n' in self.incoming:
            line, _, remainder = self.incoming.partition(b'\n')
            self.incoming[:] = remainder
            request = json.loads(line)
            try:
                response = dict(id=request['id'], phase=request['phase'], **self.snapshot(machine))
            except Exception as exc:
                response = dict(id=request['id'], phase=request['phase'], error=str(exc))
            self.outgoing.extend(json.dumps(response).encode('ascii') + b'\n')
            if len(self.outgoing) > LIMIT:
                raise RuntimeError('telemetry response backlog exceeds bound')
        if self.outgoing:
            try:
                count = self.channel.send(self.outgoing)
            except BlockingIOError:
                return
            del self.outgoing[:count]


class Client:
    def __init__(self, channel):
        self.channel = channel
        self.channel.setblocking(False)
        self.incoming = bytearray()
        self.snapshots = []
        self.errors = []
        self.sequence = 0

    def snapshot(self, phase, timeout=2):
        identity = self.sequence
        self.sequence += 1
        begin = time.monotonic()
        deadline = begin + timeout
        pending = memoryview(json.dumps(dict(id=identity, phase=phase)).encode('ascii') + b'\n')
        while pending:
            if time.monotonic() >= deadline:
                raise TimeoutError(f'telemetry {phase}: request timed out')
            if not select.select([], [self.channel], [], max(0, deadline-time.monotonic()))[1]:
                raise TimeoutError(f'telemetry {phase}: request timed out')
            try:
                count = self.channel.send(pending)
            except BlockingIOError:
                continue
            if not count:
                raise RuntimeError('telemetry channel closed')
            pending = pending[count:]
        while b'\n' not in self.incoming:
            if time.monotonic() >= deadline:
                raise TimeoutError(f'telemetry {phase}: response timed out')
            if not select.select([self.channel], [], [], max(0, deadline-time.monotonic()))[0]:
                raise TimeoutError(f'telemetry {phase}: response timed out')
            try:
                chunk = self.channel.recv(4096)
            except BlockingIOError:
                continue
            if not chunk:
                raise RuntimeError('telemetry channel closed')
            self.incoming.extend(chunk)
            if len(self.incoming) > LIMIT:
                raise RuntimeError('telemetry response exceeds bound')
        line, _, remainder = self.incoming.partition(b'\n')
        self.incoming[:] = remainder
        response = json.loads(line)
        if response.get('id') != identity or response.get('phase') != phase:
            raise RuntimeError('telemetry response does not match request')
        if 'error' in response:
            raise RuntimeError(f'telemetry {phase}: {response["error"]}')
        finish = time.monotonic()
        if not begin <= response['time'] <= finish:
            raise RuntimeError('telemetry snapshot time outside request interval')
        response.update(request_started=begin, response_received=finish,
                        roundtrip_ms=(finish-begin)*1000)
        self.snapshots.append(response)
        return response

    def capture(self, phase):
        """Record errors without preventing independent hardware cleanup."""
        try:
            return self.snapshot(phase)
        except Exception as exc:
            self.errors.append(dict(phase=phase, error=str(exc), time=time.monotonic()))
            return None


def summarize(snapshots):
    """Attribute cumulative playout changes, refusing counter resets/time reversal."""
    result = []
    for before, after in zip(snapshots, snapshots[1:]):
        elapsed = after['time'] - before['time']
        if not math.isfinite(elapsed) or elapsed < 0:
            raise ValueError('nonmonotonic telemetry snapshots')
        delta = {}
        for key in PLAYOUT_COUNTERS:
            a, b = before['playout'][key], after['playout'][key]
            if (type(a) is not int or type(b) is not int or a < 0 or b < a):
                raise ValueError(f'invalid/reset telemetry counter: {key}')
            delta[key] = b-a
        result.append(dict(start_phase=before['phase'], end_phase=after['phase'],
                           elapsed_seconds=elapsed, playout_delta=delta))
    return result


def run_receiver():
    import os
    import runpy
    from courier_emu import isdn_console
    channel = socket.socket(fileno=int(os.environ['APPLE_TRAFFIC_TELEMETRY_FD']))
    server = Server(channel)
    original = isdn_console.interactive_pump

    def instrumented(*args, **kwargs):
        pump = original(*args, **kwargs)
        def observed(machine):
            pump(machine)
            server.poll(machine)
        return observed

    isdn_console.interactive_pump = instrumented
    try:
        runpy.run_module('courier_emu', run_name='__main__')
    finally:
        isdn_console.interactive_pump = original
        channel.close()


if __name__ == '__main__':
    # Executed as a module from the project root, preserving normal CLI args.
    run_receiver()
