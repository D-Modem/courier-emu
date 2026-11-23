"""Compare separate/combined XF getters; synthetic FFI cost, not modem throughput.

Run from the repository root:
    .venv/bin/python -m tools.benchmark_xf_frame_state
Use COURIER_C5X_LIBRARY to select a prebuilt library on the target host.
"""
from __future__ import annotations

import argparse
import json
import platform
import statistics
import struct
import timeit

from courier_emu.dsp import NativeC5x


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--calls', type=int, default=500_000)
    parser.add_argument('--pairs', type=int, default=6)
    args = parser.parse_args()
    if args.calls < 1 or args.pairs < 1:
        parser.error('calls and pairs must be positive')
    with NativeC5x.from_program(0, struct.pack('<H', 0x5500)) as core:
        if core._xf_frame_state_function is None:
            parser.error('selected library does not implement the combined getter')

        def separate():
            return core.xf_falling_edges(), core.reset_generation()

        methods = {'separate': separate, 'combined': core.xf_frame_state}
        samples: dict[str, list[float]] = {name: [] for name in methods}
        for method in methods.values():
            assert method() == separate()
            timeit.timeit(method, number=min(args.calls, 10_000))
        for pair in range(args.pairs):
            order = ('separate', 'combined') if pair % 2 == 0 else ('combined', 'separate')
            for name in order:
                samples[name].append(timeit.timeit(methods[name], number=args.calls))
        medians = {name: statistics.median(values) for name, values in samples.items()}
        print(json.dumps({
            'platform': platform.platform(), 'python': platform.python_version(),
            'calls_per_sample': args.calls, 'seconds': samples,
            'median_seconds': medians,
            'getter_speedup': medians['separate'] / medians['combined'],
            'scope': 'Synthetic getter overhead only; no live media or modem throughput claim.',
        }, indent=2))


if __name__ == '__main__':
    main()
