#!/usr/bin/env python3
"""Measure cold vs preflighted Apple training retunes without opening hardware."""
from pathlib import Path
import json
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from courier_emu import resample as rs
from courier_emu.apple_line import AppleLine

HARDWARE_RATE = 10286.
SEQUENCE = ((7200., 43), (8641.23446206601, 1), (9600., 151), (9600., 193))


def run():
    tx, rx = rs.BandLimitedResampler(), rs.BandLimitedResampler()
    for _ in range(10):
        samples = tx.convert([0]*144, 7200., HARDWARE_RATE)
        rx.convert([0]*len(samples), HARDWARE_RATE, 7200.)
    stages = []
    for rate, count in SEQUENCE:
        start = time.perf_counter()
        hardware = tx.convert([0]*count, rate, HARDWARE_RATE)
        tx_ms = (time.perf_counter()-start)*1000
        start = time.perf_counter()
        rx.convert([0]*len(hardware), HARDWARE_RATE, rate)
        stages.append({'codec_rate': rate, 'codec_samples': count,
                       'tx_ms': tx_ms, 'rx_ms': (time.perf_counter()-start)*1000})
    return {'stages': stages, 'conversion_ms': sum(x['tx_ms']+x['rx_ms'] for x in stages)}


def main():
    # Warm only boot/dial clocks and native plumbing, as in the failing call.
    tx, rx = rs.BandLimitedResampler(), rs.BandLimitedResampler()
    for rate in (7200., 8000., 7200.):
        samples = tx.convert([0]*200, rate, HARDWARE_RATE)
        rx.convert([0]*len(samples), HARDWARE_RATE, rate)
    original = rs._kernel
    builds = []

    def measured(cutoff):
        start = time.perf_counter()
        out = original(cutoff)
        builds.append({'cutoff': cutoff, 'milliseconds': (time.perf_counter()-start)*1000})
        return out

    rs._kernel = measured
    cold = run()
    cold['kernel_builds'] = builds[:]
    # Remove only the training receive tables to measure true startup prep,
    # rather than inheriting them from the cold comparison above.
    for rate, _ in SEQUENCE:
        if rate != 7200:
            rs._KERNELS.pop(round(rs.CUTOFF*rate/2/HARDWARE_RATE, 9), None)
    builds.clear()
    line = AppleLine('never-started', int(HARDWARE_RATE))
    preparation_builds = builds[:]
    builds.clear()
    ready = run()
    ready['kernel_builds'] = builds[:]
    print(json.dumps({'hardware_opened': line.connected,
                      'cold': cold, 'preflighted': ready,
                      'preparation_ms': line.preparation_ms,
                      'prepared_rate_count': len(line.prepared_codec_rates),
                      'preparation_kernel_builds': len(preparation_builds)}, indent=2))
    assert not line.connected and not ready['kernel_builds']


if __name__ == '__main__':
    main()
