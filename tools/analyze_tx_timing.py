#!/usr/bin/env python3
"""Analyze low-frequency AnalogClockAudit JSONL snapshots without live profiling.

Intervals must remain online, SIP-connected and within one DSP/codec epoch.
CPU deficits include sleeping and scheduling: they are not proof of GIL stalls.
Production and send deficits are sample-time observations, not packet loss or
measured gateway playout damage. Snapshot boundaries have block quantization.
"""
import argparse
import json
import math
from pathlib import Path


def summarize(rows, *, verified_connected_window=None):
    """Only fill absent legacy SIP phase inside an externally verified window.

    An explicit non-connected phase is never overridden. The caller must obtain
    these bounds from the same call's connect/end observations, not file length.
    """
    if verified_connected_window is not None:
        start, end = verified_connected_window
        if not all(math.isfinite(t) for t in (start, end)) or start >= end:
            raise ValueError('verified connected window requires finite increasing bounds')
    intervals = []
    skipped = 0
    for a, b in zip(rows, rows[1:]):
        wall = b['monotonic_seconds'] - a['monotonic_seconds']
        if wall <= 0:
            raise ValueError('snapshot times must strictly increase')
        def connected(row):
            if row.get('sip_state') is not None:
                return row['sip_state'] == 'connected'
            return (verified_connected_window is not None and
                    start <= row['monotonic_seconds'] <= end)
        if (any(not r['online_mode'] or not connected(r)
                for r in (a, b)) or a['epoch'] != b['epoch'] or
                any(a['codec'][k] != b['codec'][k]
                    for k in ('sample_rate', 'frame_period'))):
            skipped += 1
            continue
        def delta(key):
            return b[key] - a[key]
        thread = delta('thread_cpu_seconds')
        process = delta('process_cpu_seconds')
        produced = b['rtp_tx']['produced_samples'] - a['rtp_tx']['produced_samples']
        sent = b['rtp_tx']['sent_samples'] - a['rtp_tx']['sent_samples']
        instructions = delta('cpu_instructions')
        if min(thread, process, produced, sent, instructions) < 0:
            raise ValueError('counter rewind inside a connected epoch')
        pa, pb = a.get('pacing', {}), b.get('pacing', {})
        paced = (pb['paced_seconds'] - pa['paced_seconds']
                 if pa.get('paced_seconds') is not None and
                 pb.get('paced_seconds') is not None else None)
        if paced is not None and paced < 0:
            raise ValueError('pacing counter rewind inside a connected epoch')
        intervals.append({
            'start': a['monotonic_seconds'], 'end': b['monotonic_seconds'],
            'epoch': b['epoch'], 'wall_seconds': wall,
            'sip_phase_source': ('externally_verified_window'
                                 if any(r.get('sip_state') is None for r in (a, b))
                                 else 'snapshots'),
            'thread_cpu_seconds': thread, 'process_cpu_seconds': process,
            'thread_cpu_fraction': thread / wall,
            'non_thread_cpu_seconds': max(0, wall - thread),
            # paced_seconds is requested sleep, not measured sleep duration.
            'requested_pacing_sleep_seconds': paced,
            'cpu_instructions': instructions,
            'produced_samples': produced, 'sent_samples': sent,
            'production_deficit_ms': (wall - produced / 8000) * 1000,
            'send_deficit_ms': (wall - sent / 8000) * 1000,
            'sample_clock_late_change_ms': (
                b['rtp_tx']['sample_clock_late_ms'] -
                a['rtp_tx']['sample_clock_late_ms']),
            'queue_start_samples': a.get('rtp_tx_queue_samples'),
            'queue_end_samples': b.get('rtp_tx_queue_samples'),
        })
    return {'intervals': intervals, 'skipped_boundary_intervals': skipped}


def aggregate(intervals):
    """Weighted CPU utilization, not an average of interval percentages."""
    wall = sum(r['wall_seconds'] for r in intervals)
    cpu = sum(r['thread_cpu_seconds'] for r in intervals)
    return {
        'analyzed_wall_seconds': wall, 'thread_cpu_seconds': cpu,
        'thread_cpu_fraction': cpu / wall if wall else None,
        'produced_samples': sum(r['produced_samples'] for r in intervals),
        'sent_samples': sum(r['sent_samples'] for r in intervals),
        'externally_verified_intervals': sum(
            r['sip_phase_source'] == 'externally_verified_window' for r in intervals),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshots', type=Path, help='one audit snapshot per JSONL line')
    parser.add_argument('--start', type=float, default=float('-inf'),
                        help='inclusive monotonic start; exclude diagnostic tails')
    parser.add_argument('--end', type=float, default=float('inf'))
    parser.add_argument('--verified-legacy-connected-window', action='store_true',
                        help='explicitly attest start/end are a verified connected data window; '
                             'fill missing legacy SIP phase only, never override observed phase')
    args = parser.parse_args()
    if math.isnan(args.start) or math.isnan(args.end) or args.start > args.end:
        parser.error('--start must not exceed --end and neither may be NaN')
    if args.verified_legacy_connected_window and (
            not all(math.isfinite(t) for t in (args.start, args.end)) or args.start >= args.end):
        parser.error('legacy phase attestation requires finite increasing --start and --end')
    rows = [json.loads(line) for line in args.snapshots.read_text().splitlines() if line.strip()]
    rows = [r for r in rows if args.start <= r['monotonic_seconds'] <= args.end]
    result = summarize(rows, verified_connected_window=(args.start, args.end)
                       if args.verified_legacy_connected_window else None)
    result['aggregate'] = aggregate(result['intervals'])
    result['largest_production_deficits'] = sorted(
        result['intervals'], key=lambda r: r['production_deficit_ms'], reverse=True)[:10]
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
