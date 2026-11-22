"""Exact, bounded, independently paced duplex DTE records for live Apple tests.

No byte normalization, resynchronization, carrier/ACK injection or CRC repair.
The parent observes each real remote DTE before issuing the next record in that
same direction. This deliberately measures bounded record traffic, not maximum
modem throughput.
"""
import hashlib
import math
import struct
import zlib

HEADER = struct.Struct('<4scIH')


def record(role, sequence, *, binary=True, size=256):
    if role not in ('A', 'I') or not 0 <= sequence < 2**32 or not 1 <= size <= 4096:
        raise ValueError('invalid traffic record')
    if binary:
        # Every 256-byte body contains all octets, including NUL, LF, Ctrl-],
        # XON/XOFF and 0xff. The permutation changes by role and sequence.
        body = bytes((73 * i + 17 * sequence + ord(role)) & 255 for i in range(size))
    else:
        seed = f'{role}:{sequence}'.encode('ascii')
        body = b''.join(hashlib.sha256(seed + i.to_bytes(4, 'little')).hexdigest().encode()
                        for i in range((size + 63) // 64))[:size]
        return f'~CEMU:{role}:{sequence:08x}:'.encode() + body + b'\r\n'
    header = HEADER.pack(b'CEMU', role.encode('ascii'), sequence, size)
    return header + body + struct.pack('<I', zlib.crc32(header + body))


class ReceiveStream:
    def __init__(self, source, *, binary=True, size=256):
        self.source, self.binary, self.size = source, binary, size
        self.pending = bytearray()
        self.records = self.bytes = 0
        self.error = None
        self.last_complete = self.started = None
        self.max_gap = 0.0
        self.hash = hashlib.sha256()

    def start(self, now):
        self.started = self.last_complete = now

    def feed(self, data, now):
        if self.error:
            return
        self.pending.extend(data)
        while self.pending:
            expected = record(self.source, self.records, binary=self.binary, size=self.size)
            n = min(len(expected), len(self.pending))
            if self.pending[:n] != expected[:n]:
                at = next(i for i in range(n) if self.pending[i] != expected[i])
                self.error = dict(sequence=self.records, offset=at,
                                  expected=expected[at], actual=self.pending[at], time=now)
                return
            if n < len(expected):
                return
            del self.pending[:n]
            self.records += 1
            self.bytes += n
            self.hash.update(expected)
            if self.last_complete is not None:
                self.max_gap = max(self.max_gap, now - self.last_complete)
            self.last_complete = now

    def status(self, now):
        return dict(records=self.records, bytes=self.bytes, pending_bytes=len(self.pending),
                    sha256=self.hash.hexdigest(), error=self.error,
                    max_gap_seconds=self.max_gap,
                    open_gap_seconds=now - self.last_complete if self.last_complete is not None else None)


def check_window(window, seconds, max_gap=5):
    if not math.isfinite(seconds) or seconds <= 0:
        raise AssertionError('invalid traffic duration')
    if not isinstance(window, dict):
        raise AssertionError('no completed traffic window')
    if not math.isfinite(window['elapsed_seconds']) or window['elapsed_seconds'] < seconds:
        raise AssertionError('insufficient connected observation time')
    for side in ('apple', 'imodem'):
        stream = window[side]
        if any(not isinstance(stream[key], (int, float)) or not math.isfinite(stream[key])
               or stream[key] < 0 for key in ('max_gap_seconds', 'open_gap_seconds')):
            raise AssertionError(f'{side}: invalid gap statistics')
        if stream['error']:
            raise AssertionError(f'{side}: corrupt traffic: {stream["error"]}')
        if stream['records'] < 10:
            raise AssertionError(f'{side}: insufficient complete records ({stream["records"]} < 10)')
        if stream['max_gap_seconds'] > max_gap or stream['open_gap_seconds'] > max_gap:
            raise AssertionError(f'{side}: traffic stalled')


def verify_events(directory, metadata):
    """Recompute gaps, counts and one-outstanding pacing from saved DTE events."""
    import json
    start, end = metadata['start'], metadata['end']
    if not all(math.isfinite(value) for value in (start, end)) or abs(end-start-metadata['seconds']) > 1e-6:
        raise AssertionError('invalid scheduled traffic window')
    observed_end = start + metadata['window']['elapsed_seconds']
    sent = dict(apple=0, imodem=0)
    received = dict(apple=0, imodem=0)
    times = dict(apple=[], imodem=[])
    last = -math.inf
    for line in (directory / 'events.jsonl').read_text().splitlines():
        event = json.loads(line)
        now = event['time']
        if not math.isfinite(now) or now < last:
            raise AssertionError('nonmonotonic event log')
        last = now
        if event['event'] not in ('sent', 'received'):
            continue
        side = event['side']
        other = 'apple' if side == 'imodem' else 'imodem'
        count = event['records']
        if event['event'] == 'sent':
            if not start <= now < end or count != sent[side] + 1 or received[other] != count - 1:
                raise AssertionError('invalid send window, sequence or outstanding-record bound')
            sent[side] = count
        else:
            if now < start or count != received[side] + 1 or count > sent[other]:
                raise AssertionError('receive sequence is not backed by a real send')
            received[side] = count
            if now <= observed_end:
                times[side].append(now)
    if sent != metadata['sent_records']:
        raise AssertionError('event send counts differ from saved metadata')
    for side in ('apple', 'imodem'):
        other = 'apple' if side == 'imodem' else 'imodem'
        if received[side] != sent[other]:
            raise AssertionError('event log has undrained records')
        status = metadata['window'][side]
        points = [start] + times[side]
        gap = max((b - a for a, b in zip(points, points[1:])), default=0)
        if (status['records'] != len(times[side])
                or abs(status['max_gap_seconds'] - gap) > 1e-6
                or abs(status['open_gap_seconds'] - (observed_end - points[-1])) > 1e-6):
            raise AssertionError('saved window statistics disagree with actual DTE events')


def verify_saved(directory, *, metadata=None):
    """Independently regenerate sent records and compare every saved byte."""
    import json
    metadata = metadata or json.loads((directory / 'traffic.json').read_text())
    if metadata.get('failure'):
        raise AssertionError(metadata['failure'])
    check_window(metadata['window'], metadata['seconds'])
    verify_events(directory, metadata)
    result = {}
    for source, role, destination in [('apple', 'A', 'imodem'), ('imodem', 'I', 'apple')]:
        count = metadata['sent_records'][source]
        if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 100000:
            raise AssertionError('invalid bounded record count')
        sent = (directory / f'{source}-sent.bin').read_bytes()
        received = (directory / f'{destination}-received.bin').read_bytes()
        expected = b''.join(record(role, n, binary=metadata['binary'], size=metadata['record_size'])
                            for n in range(count))
        if not count or sent != expected:
            raise AssertionError(f'{source}: saved source differs from deterministic records')
        if received != expected:
            raise AssertionError(f'{source}: saved receive stream differs from sent records')
        result[source] = dict(records=count, record_bytes=len(sent),
                              payload_bytes=count * metadata['record_size'],
                              sha256=hashlib.sha256(sent).hexdigest(), exact=True)
    return result


def main():
    import argparse
    import json
    from pathlib import Path
    parser = argparse.ArgumentParser(description='Independently verify saved Apple duplex payloads and timing (no hardware)')
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    try:
        result = dict(payload_and_timing_passed=True, streams=verify_saved(args.directory))
    except (AssertionError, OSError, ValueError, KeyError, TypeError) as exc:
        result = dict(payload_and_timing_passed=False, error=str(exc))
    print(json.dumps(result, indent=2))
    return 0 if result['payload_and_timing_passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
