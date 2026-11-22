#!/usr/bin/env python3
"""Independent, offline Bell-103/8N1 WAV diagnostic; never used by the emulator."""
import argparse
from array import array
import json
import math
from pathlib import Path
import sys
import wave


def uart_runs(bits):
    frames = {
        i: sum(bits[i + 1 + k] << k for k in range(8))
        for i in range(1, len(bits) - 9)
        if bits[i - 1] and not bits[i] and bits[i + 9]
    }
    for start in frames:
        if start - 10 in frames:
            continue
        data = bytearray()
        i = start
        while i in frames:
            data.append(frames[i])
            i += 10
        if len(data) >= 4:
            yield start, bytes(data)


def decode(samples, rate, mark, space):
    # Nearest-sample conversion to 24 samples/bit. This is a diagnostic, not
    # a replacement for the guest receiver or a calibrated BER measurement.
    samples = [samples[i * rate // 7200] for i in range(len(samples) * 7200 // rate)]
    weights = [[complex(math.cos(2 * math.pi * f * i / 7200),
                        math.sin(2 * math.pi * f * i / 7200)) for i in range(24)]
               for f in (mark, space)]
    runs = []
    for phase in range(24):
        bits = []
        for start in range(phase, len(samples) - 23, 24):
            block = samples[start:start + 24]
            energies = [abs(sum(x * w for x, w in zip(block, row))) for row in weights]
            bits.append(int(energies[0] > energies[1]))
        for start, data in uart_runs(bits):
            runs.append({'phase': phase, 'start_seconds': (phase + start * 24) / 7200,
                         'bytes': len(data), 'hex': data.hex()})
    return sorted(runs, key=lambda row: (-row['bytes'], row['phase'], row['start_seconds']))


def analyze(path, mark, space, expected=None):
    with wave.open(str(path)) as wav:
        if wav.getnchannels() != 1 or wav.getsampwidth() != 2:
            raise ValueError('expected mono signed 16-bit PCM')
        rate = wav.getframerate()
        samples = array('h', wav.readframes(wav.getnframes()))
    if sys.byteorder != 'little':
        samples.byteswap()
    runs = decode(samples, rate, mark, space)
    result = {'mark_hz': mark, 'space_hz': space, 'baud': 300, 'framing': '8N1',
              'method': '24 timing phases; non-coherent energy; contiguous valid frames',
              'runs': runs}
    if expected is not None:
        result['expected_hex'] = expected.hex()
        result['exact_payload_found'] = any(expected in bytes.fromhex(r['hex']) for r in runs)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--a-payload-hex')
    parser.add_argument('--b-payload-hex')
    args = parser.parse_args()
    result = {}
    for side, mark, space in [('a', 2225, 2025), ('b', 1270, 1070)]:
        expected = getattr(args, side + '_payload_hex')
        result[side + '-tx'] = analyze(args.directory / (side + '-tx.wav'), mark, space,
                                      bytes.fromhex(expected) if expected is not None else None)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
