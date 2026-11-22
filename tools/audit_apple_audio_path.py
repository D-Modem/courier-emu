#!/usr/bin/env python3
"""Offline audit of Apple PCM captures; no hardware access or invented audio.

Replays codec-to-hardware conversion exactly (including reset generations),
measures hardware-bound PCM, and summarizes real payload verdicts. Helper-bound
TX is NOT a post-DAC recording; physical clipping/delay needs an analog probe.
Requires NumPy.
"""
import argparse
import bisect
import json
import re
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from courier_emu.resample import BandLimitedResampler
from tools.analyze_apple_bell103 import decode


def events(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def pcm_metrics(samples):
    x = np.asarray(samples, dtype=float)
    if not len(x):
        return {'samples': 0}
    mean = float(np.mean(x))
    return {'samples': len(x), 'mean': round(mean, 3),
            'rms': round(float(np.sqrt(np.mean(x * x))), 3),
            'ac_rms': round(float(np.sqrt(np.mean((x - mean)**2))), 3),
            'peak': int(np.max(np.abs(x))),
            'near_rail_samples': int(np.count_nonzero(np.abs(x) >= 32760))}


def replay_tx(recording):
    codec = np.frombuffer((recording / 'codec-tx.s16').read_bytes(), dtype='<i2')
    hardware = np.frombuffer((recording / 'codec-hardware-tx.s16').read_bytes(), dtype='<i2')
    ce = events(recording / 'codec-frames.jsonl')
    he = events(recording / 'codec-hardware-frames.jsonl')
    controls = [e for e in he if not e['tx_count']]
    converter = BandLimitedResampler()
    cursor = 0
    resetting = False
    resets = 0
    rendered = []
    for event in ce:
        while cursor < len(controls) and controls[cursor]['time'] < event['time']:
            reset = controls[cursor].get('resetting', False)
            if reset and not resetting:
                converter = BandLimitedResampler()
                resets += 1
            resetting = reset
            cursor += 1
        start, count = event['tx_start'], event['tx_count']
        chunk = codec[start:start + count]
        if len(chunk) != count:
            raise ValueError('truncated codec TX trace')
        output = converter.convert(chunk.tolist(), event['rate'], he[0]['rate'])
        gain = event.get('tx_gain', 1.0)
        rendered.extend(round(x * gain) if event['off_hook'] else 0 for x in output)
        # The first PCM exchange clears reset silence. Retain that edge so a
        # later explicit reset builds a new converter even without controls.
        if output:
            resetting = False
    expected = np.asarray(rendered, dtype=np.int16)
    n = min(len(expected), len(hardware))
    mismatch = np.flatnonzero(expected[:n] != hardware[:n])
    return {'expected_samples': len(expected), 'recorded_samples': len(hardware),
            'reset_generations': resets,
            'exact_match': len(expected) == len(hardware) and not len(mismatch),
            'different_samples_in_common_prefix': len(mismatch),
            'first_different_sample': int(mismatch[0]) if len(mismatch) else None,
            'boundary': 'helper-bound attempted TX, not proof of physical DAC playback'}


def audit(capture):
    recording = capture / 'caller/2903'
    he = events(recording / 'codec-hardware-frames.jsonl')
    tx = np.frombuffer((recording / 'codec-hardware-tx.s16').read_bytes(), dtype='<i2')
    rx = np.frombuffer((recording / 'codec-hardware-rx.s16').read_bytes(), dtype='<i2')
    offhook = [e for e in he if e['off_hook'] and e['tx_count'] and not e.get('failed')]
    result = {'capture': str(capture), 'tx_converter_replay': replay_tx(recording)}
    verification = capture / 'payload-verification.json'
    v = json.loads(verification.read_text()) if verification.exists() else {}
    rate = he[0]['rate']
    for channel, data in [('tx', tx), ('rx', rx)]:
        blocks = [data[e[f'{channel}_start']:e[f'{channel}_start'] + e.get(f'{channel}_count', 0)]
                  for e in offhook]
        samples = np.concatenate(blocks) if blocks else np.array([], dtype='<i2')
        metrics = result['hardware_' + channel] = pcm_metrics(samples)
        expected = v.get('expected_apple_to_sip' if channel == 'tx' else 'expected_sip_to_apple',
                         'APPLE-TO-SIP-123' if channel == 'tx' else 'SIP-TO-APPLE-456').encode('ascii')
        decoded = decode(samples, rate, *( (1270, 1070) if channel == 'tx' else (2225, 2025)), expected)
        start = decoded['payload_start_seconds']
        metrics['exact_expected_payload_decoded'] = decoded['exact_payload_found']
        if start is not None:
            first = round(start * rate)
            last = first + round(len(expected) * 10 / 300 * rate)
            metrics['payload_window'] = {'start_seconds': round(start, 6),
                                         **pcm_metrics(samples[first:last])}
    intervals = [(b['time'] - a['time']) * 1000 for a, b in zip(offhook, offhook[1:])]
    result['exchange_start_intervals_ms'] = (
        {'p50': round(float(np.percentile(intervals, 50)), 3),
         'p99': round(float(np.percentile(intervals, 99)), 3),
         'maximum': round(max(intervals), 3)} if intervals else {})
    result['exchange_timing_warning'] = 'HAL callback bursts and explicit reset pauses are included; not a DAC clock.'
    if v:
        result['payload'] = {k: v[k] for k in ('caller_connect', 'receiver_connect',
                                              'apple_to_sip_payload', 'sip_to_apple_payload')}
    summary = recording / 'summary.json'
    if summary.exists():
        s = json.loads(summary.read_text())
        result['transport'] = {k: s['line'].get(k) for k in ('output_gap_samples',
            'input_overflow_samples', 'live_filter_misses', 'native_receive', 'off_hook_pcm_seconds')}
        result['hook_released'] = (not bool(s['final_line_status']['hook'] & 1)
                                   if s.get('final_line_status') else None)
        result['error'] = s.get('bridge_error') or s.get('error')
    log = recording / 'hardware.log'
    if log.exists():
        match = re.search(r'active output gaps=(\d+).*?input overflow=(\d+)', log.read_text())
        if match:
            result['helper_final_counts'] = {'output_gap_samples': int(match[1]),
                                              'input_overflow_samples': int(match[2])}
    snapshots = recording / 'codec-state.jsonl'
    if snapshots.exists():
        times = [e['time'] for e in he]
        active_counts = []
        for snapshot in events(snapshots):
            index = bisect.bisect_right(times, snapshot['time']) - 1
            if index >= 0 and he[index]['off_hook'] and not he[index].get('resetting'):
                active_counts.append(snapshot['codec']['rx_empty_frames'])
        result['active_adc_empty_counter'] = {'snapshots': len(active_counts),
            'minimum': min(active_counts) if active_counts else None,
            'maximum': max(active_counts) if active_counts else None,
            'warning': 'Counters reset with the DSP; initial empty frames are not active losses.'}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('captures', nargs='+', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = []
    for capture in args.captures:
        try:
            row = audit(capture)
        except (OSError, ValueError, KeyError) as exc:
            row = {'capture': str(capture), 'audit_error': str(exc)}
        result.append(row)
        print(capture.name, row.get('tx_converter_replay', {}).get('exact_match'), row.get('payload', {}))
    args.output.write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
