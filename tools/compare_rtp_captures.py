#!/usr/bin/env python3
"""Compare two simultaneous, extracted RTP captures without trusting clock sync.

Both directories use eicon_rtp_pcap_check.py JSON/.g711 output. Select a stream
by its complete endpoint--endpoint--SSRC name; identities include sequence and
RTP timestamp. This reports interior absence separately from capture boundaries.
Packet absence is not attributed to network loss unless both capture drop
counters and capture coverage have been independently verified.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.audit_apple_rtp import load_stream


def compare_streams(upstream, downstream):
    a, b = upstream['packets'], downstream['packets']
    shared = a.keys() & b.keys()
    base = upstream['arrival_rows'][0]['timestamp']
    relative = lambda key: (key[1] - base + 2**31) % 2**32 - 2**31
    ordered = lambda keys: sorted(keys, key=lambda key: (relative(key), key[0]))
    if shared:
        low, high = min(map(relative, shared)), max(map(relative, shared))
        interior = {key for key in a.keys() - b.keys() if low < relative(key) < high}
    else:
        interior = set()
    return {
        'upstream_packets': len(a), 'downstream_packets': len(b),
        'shared_packets': len(shared),
        'shared_payload_mismatches': sum(a[key][1] != b[key][1] for key in shared),
        'upstream_only_interior': [dict(sequence=seq, timestamp=ts, samples=len(a[seq, ts][1]))
                                   for seq, ts in ordered(interior)],
        'upstream_only_boundary_packets': len(a.keys() - b.keys() - interior),
        'downstream_only_packets': len(b.keys() - a.keys()),
        'warning': ('Interior absence requires zero-drop captures and verified coverage before '
                    'attributing loss. Boundary differences are not a loss estimate. '
                    'No one-way timing claim is made without synchronized clocks.'),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('upstream', type=Path)
    parser.add_argument('downstream', type=Path)
    parser.add_argument('--stream', required=True, help='complete extraction stream name, without .json')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if Path(args.stream).name != args.stream:
        parser.error('--stream must be a plain stream name')
    result = compare_streams(load_stream(args.upstream / (args.stream + '.json')),
                             load_stream(args.downstream / (args.stream + '.json')))
    with args.output.open('x') as out:
        out.write(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    return 0 if (result['shared_packets'] and not result['shared_payload_mismatches']
                 and not result['upstream_only_interior']
                 and not result['downstream_only_packets']) else 2


if __name__ == '__main__':
    raise SystemExit(main())
