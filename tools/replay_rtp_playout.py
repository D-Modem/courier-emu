#!/usr/bin/env python3
"""Replay extracted RTP arrival times through the real receive playout buffer.

Input: one eicon_rtp_pcap_check.py stream's JSON and adjacent .g711 file.
This tests recorded capture timing, NOT USB hardware, modem BER or local kernel
arrival timing. --poll-ms models additional receive-poll batching explicitly.
"""
import argparse
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from courier_emu.rtp import RtpPacket, RtpPlayout


def replay(path, *, delay_ms=60, poll_ms=5):
    if not 0 <= delay_ms < 2000 or not 0 < poll_ms <= 1000:
        raise ValueError('require 0 <= delay_ms < 2000 and 0 < poll_ms <= 1000')
    rows = json.loads(path.read_text())
    audio = path.with_suffix('.g711').read_bytes()
    if not rows:
        raise ValueError('empty RTP stream')
    packets = []
    offset = 0
    previous = rows[0]['time']
    first_time = previous
    timestamp = rows[0]['timestamp']
    positions = []
    for row in rows:
        size = row['bytes']
        if size <= 0 or size != int(size) or offset + size > len(audio):
            raise ValueError('invalid or truncated RTP extraction')
        if not math.isfinite(row['time']) or row['time'] < previous:
            raise ValueError('capture arrival times must be finite and ordered')
        previous = row['time']
        payload = audio[offset:offset + size]
        offset += size
        position = (row['timestamp'] - timestamp + 2**31) % 2**32 - 2**31
        positions.append(position)
        packets.append((row['time'] - first_time,
                        RtpPacket(row['sequence'], row['timestamp'], 7, 0, payload)))
    if offset != len(audio):
        raise ValueError('RTP extraction length mismatch')
    base = min(positions)
    span = max(at + len(packet.payload) for at, (_, packet) in zip(positions, packets)) - base
    # Bound offline allocations too: a corrupt timestamp must not allocate GBs.
    if span > 8000 * 600:
        raise ValueError('replay timestamp span exceeds ten-minute limit')
    expected = {}
    for at, (_, packet) in zip(positions, packets):
        for i, value in enumerate(packet.payload, at - base):
            if i in expected and expected[i] != value:
                raise ValueError('conflicting overlapping RTP payloads')
            expected[i] = value
    peer = ('capture', 1)
    buffer = RtpPlayout(delay_samples=round(delay_ms * 8))
    result = bytearray()
    index = 0
    step = poll_ms / 1000
    # Model session.poll: read queued datagrams, then drain elapsed deadlines.
    finish = max(packets[-1][0], delay_ms / 1000 + span / 8000)
    for tick in range(math.ceil(finish / step) + 2):
        now = tick * step
        while index < len(packets) and packets[index][0] <= now:
            _, packet = packets[index]
            buffer.push(packet, peer, peer, now)
            index += 1
        result.extend(buffer.drain(now))
    tail = max(0, len(result) - span)
    missing = buffer.missing_samples - tail
    mismatches = sum(i >= len(result) or result[i] != value for i, value in expected.items())
    return {
        'stream': str(path), 'capture_timing_only': True,
        'delay_ms': delay_ms, 'poll_ms': poll_ms,
        'input_packets': len(packets), 'timestamp_span_samples': span,
        'capture_missing_samples': span - len(expected),
        'playout_missing_samples_in_span': missing,
        'captured_sample_mismatches': mismatches,
        'captured_samples_preserved': mismatches == 0 and missing == span - len(expected),
        'playout': buffer.status(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('streams', type=Path, nargs='+')
    parser.add_argument('--delay-ms', type=float, default=60)
    parser.add_argument('--poll-ms', type=float, default=5)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = [replay(path, delay_ms=args.delay_ms, poll_ms=args.poll_ms) for path in args.streams]
    with args.output.open('x') as out:
        out.write(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    return 0 if all(row['captured_samples_preserved'] for row in result) else 2


if __name__ == '__main__':
    raise SystemExit(main())
