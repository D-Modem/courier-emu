#!/usr/bin/env python3
"""Test Apple PCM/rate changes with silence. On-hook unless --off-hook is given.

No number is ever dialed. Off-hook briefly seizes the connected powered line.
This tests hardware transport, NOT modem negotiation or firmware throughput.
"""
from pathlib import Path
import argparse
import json
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from courier_emu.apple_line import AppleLine, APPLE_RATES, hardware_rate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--helper', type=Path, default=ROOT / '.build/apple_line')
    parser.add_argument('--hardware-rate', type=int, choices=APPLE_RATES)
    parser.add_argument('--codec-rate', type=float, action='append', dest='rates',
                        help='repeat for a retune test; defaults to the known Courier rate ladder')
    parser.add_argument('--seconds', type=float, default=1, help='seconds at each codec rate')
    parser.add_argument('--off-hook', action='store_true', help='seize the line; no dialing')
    args = parser.parse_args()
    rates = args.rates or [7200, 40320000 / 5320, 8000, 9600, 10266.666667]
    if not 0 < args.seconds <= 30 or not all(0 < r <= 10286 for r in rates):
        parser.error('require 0 < seconds <= 30 and 0 < codec rates <= 10286')
    rate = args.hardware_rate or hardware_rate(max(rates))
    if max(rates) > rate + .01:
        parser.error('hardware rate must cover every codec rate')
    line = AppleLine(str(args.helper), rate)
    stages = []
    started = time.monotonic()
    error = None
    try:
        line.open()
        # Establish the monitor stream before a possible hook transition.
        for _ in range(10):
            line.service_codec([0] * round(rates[0] * .02), rates[0], False)
        for codec in rates:
            start = time.monotonic()
            rx = []
            for _ in range(max(1, round(args.seconds / .02))):
                rx.extend(line.service_codec([0] * round(codec * .02), codec, args.off_hook))
            stages.append({'codec_rate': codec, 'wall_seconds': time.monotonic()-start,
                           'rx_samples': len(rx), 'rx_peak': max(map(abs, rx), default=0)})
    except (OSError, RuntimeError) as exc:
        error = str(exc)
    finally:
        line.close()  # EOF releases hook, even if transport or resampling failed
    print(json.dumps({'off_hook_test': args.off_hook, 'dialed': False,
                      'elapsed_seconds': time.monotonic()-started,
                      'stages': stages, 'line': line.status(), 'error': error}, indent=2))
    return 1 if error or line.error else 0


if __name__ == '__main__':
    raise SystemExit(main())
