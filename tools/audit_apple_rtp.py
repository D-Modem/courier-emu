#!/usr/bin/env python3
"""Compare extracted RTP payloads across a PBX, by SSRC/sequence/timestamp.

Input is the metadata+G.711 output of eicon_rtp_pcap_check.py. Keeps arrival
order for timing diagnostics but restores timestamp order for sample identity
checks. Differences in capture start/end are not declared packet loss.
"""
import argparse
import json
from pathlib import Path
import statistics


def load_stream(path):
    rows = json.loads(path.read_text())
    audio = path.with_suffix('.g711').read_bytes()
    packets = {}
    offset = 0
    duplicates = 0
    for row in rows:
        size = row['bytes']
        payload = audio[offset:offset + size]
        if len(payload) != size or size < 0:
            raise ValueError('truncated or invalid RTP extraction')
        offset += size
        key = row['sequence'], row['timestamp']
        if key in packets:
            duplicates += 1
            if packets[key][1] != payload:
                raise ValueError('conflicting payloads for one RTP packet identity')
        packets[key] = row['time'], payload
    if offset != len(audio) or not rows:
        raise ValueError('RTP extraction length mismatch or empty stream')
    base = rows[0]['timestamp']
    ordered = sorted(packets, key=lambda key: (key[1] - base + 2**31) % 2**32 - 2**31)
    return {'packets': packets, 'ordered_audio': b''.join(packets[k][1] for k in ordered),
            'arrival_rows': rows, 'duplicates': duplicates}


def compare_source(stream, source):
    """Match sparse packets to DSP samples without compressing timestamp gaps."""
    packets = stream['packets']
    base = stream['arrival_rows'][0]['timestamp']
    relative = lambda key: (key[1] - base + 2**31) % 2**32 - 2**31
    keys = sorted(packets, key=relative)
    groups = []
    start = previous_end = None
    block = bytearray()
    for key in keys:
        at = relative(key)
        payload = packets[key][1]
        if previous_end is not None and at != previous_end:
            groups.append((start, bytes(block)))
            start, block = None, bytearray()
        if start is None:
            start = at
        block.extend(payload)
        previous_end = at + len(payload)
    groups.append((start, bytes(block)))
    candidates = []
    for at, block in sorted(groups, key=lambda row: -len(row[1])):
        found = source.find(block)
        if found >= 0:
            offset = found - at
            mismatches = sum(source[offset + relative(key):offset + relative(key) + len(packets[key][1])]
                             != packets[key][1] for key in keys)
            candidates.append((mismatches, offset))
    mismatches, offset = min(candidates) if candidates else (None, None)
    span = relative(keys[-1]) + len(packets[keys[-1]][1]) - relative(keys[0])
    return {'captured_packets_exact_in_dsp_tx': mismatches == 0,
            'source_anchor_found': bool(candidates), 'source_sample_offset': offset,
            'mismatching_captured_packets': mismatches,
            'timestamp_span_samples': span,
            'uncaptured_timestamp_samples': max(0, span - len(stream['ordered_audio']))}


def compare(upstream, downstream):
    a, b = upstream['packets'], downstream['packets']
    shared = a.keys() & b.keys()
    delays = [(b[key][0] - a[key][0]) * 1000 for key in shared]
    return {'shared_packets': len(shared),
            'shared_samples': sum(len(a[k][1]) for k in shared),
            'altered_payload_packets': sum(a[k][1] != b[k][1] for k in shared),
            'only_upstream_packets': len(a.keys() - b.keys()),
            'only_downstream_packets': len(b.keys() - a.keys()),
            'forwarding_delay_ms': {'minimum': min(delays), 'maximum': max(delays),
                                    'median': statistics.median(delays)} if delays else None,
            'warning': 'Unshared packets may precede answer or follow hangup; not a loss estimate.'}


def audit(directory, host, dsp_tx=None):
    streams = {}
    for path in directory.glob('*.json'):
        if path.with_suffix('.g711').exists():
            streams[path.stem] = load_stream(path)
    selected_ssrc = {name.split('--')[-1] for name in streams
                     if any(endpoint.startswith(host + '_') for endpoint in name.split('--')[:2])}
    comparisons = []
    sources = []
    for ssrc in sorted(selected_ssrc):
        group = {n: s for n, s in streams.items() if n.endswith('--' + ssrc)}
        for name, stream in group.items():
            if name.startswith(host + '_') and dsp_tx is not None:
                data = stream['ordered_audio']
                at = dsp_tx.find(data)
                sources.append({'stream': name, 'ordered_samples': len(data),
                                'exact_in_dsp_tx': at >= 0,
                                'dsp_sample_offset': at if at >= 0 else None,
                                **compare_source(stream, dsp_tx)})
            src, dst, _ = name.split('--')
            for other, peer in group.items():
                src2, dst2, _ = other.split('--')
                if dst.split('_')[0] == src2.split('_')[0] and name != other:
                    comparisons.append({'upstream': name, 'downstream': other,
                                         **compare(stream, peer)})
    return {'ssrcs': sorted(selected_ssrc), 'dsp_to_network': sources,
            'pbx_forwarding': comparisons}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--host', required=True, help='SIP emulator IPv4 address in capture')
    parser.add_argument('--dsp-tx', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.directory, args.host, args.dsp_tx.read_bytes() if args.dsp_tx else None)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
