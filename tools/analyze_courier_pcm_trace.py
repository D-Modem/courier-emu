#!/usr/bin/env python3
"""Summarize passive Courier 4.03 PCM pre-descrambler captures.

The capture must be taken at 0x8ce8, before that routine overwrites @0320.
DP=6 and mode @006f=0843 select the observed V.90 receive path. This is a
firmware-state diagnostic, not a waveform decoder or proof of lossless capture.
Accepts the isolated live probe's ``pcm-raw`` records and offline ``retrain``
records (the latter must have been captured at the same PC).
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import statistics
from typing import Iterable


def repeating_period(values: list[int], limit: int = 64) -> list[int] | None:
    """Return a strictly repeating prefix, requiring at least two periods."""
    for width in range(1, min(limit, len(values) // 2) + 1):
        if all(value == values[i % width] for i, value in enumerate(values)):
            return values[:width]
    return None


def signed16(value: int) -> int:
    return (value & 0x7fff) - (value & 0x8000)


def summarize(records: Iterable[dict]) -> dict:
    rows = [r for r in records
            if r.get('kind') in ('pcm-raw', 'retrain') and r.get('dp') == 6
            and r.get('ram', {}).get('006f') == 0x843]
    values = []
    widths: Counter = Counter()
    for row in rows:
        ram = row['ram']
        width = ram['0322']
        if not 1 <= width <= 16:
            raise ValueError(f'invalid receive chunk width: {width}')
        widths[width] += 1
        values.append(ram['0320'] & ((1 << width) - 1))
    result = {
        'capture_pc': '0x8ce8',
        'mode': '0x0843',
        'records': len(rows),
        'chunk_width_counts': dict(sorted(widths.items())),
        'chunk_value_counts': dict(sorted(Counter(values).items())),
        # A pattern of chunk *values* is meaningful only with fixed widths.
        'repeating_chunks': repeating_period(values) if len(widths) == 1 else None,
        'samples': {},
        'capture_completeness': 'not established by these records',
    }
    for address in ('0300', '0338'):
        samples = [signed16(r['ram'][address]) for r in rows if address in r['ram']]
        if samples:
            result['samples'][address] = {
                'count': len(samples), 'min': min(samples), 'max': max(samples),
                'mean': statistics.mean(samples),
                'standard_deviation': statistics.pstdev(samples),
            }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trace', type=Path)
    args = parser.parse_args()
    with args.trace.open() as stream:
        result = summarize(json.loads(line) for line in stream if line.strip())
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
