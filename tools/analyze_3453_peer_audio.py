#!/usr/bin/env python3
"""Analyze explicitly selected offline peer WAV diagnostics (stdlib only)."""
import argparse
from array import array
import cmath
import hashlib
import json
import math
from pathlib import Path
import sys
import wave


def spectrum(samples):
    n = len(samples)
    if n < 2 or n & (n - 1):
        raise ValueError('FFT length must be a power of two')
    values = [complex(x * (0.5 - 0.5 * math.cos(2 * math.pi * i / (n - 1))))
              for i, x in enumerate(samples)]
    j = 0
    for i in range(1, n):
        bit = n >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j ^= bit
        if i < j:
            values[i], values[j] = values[j], values[i]
    size = 2
    while size <= n:
        root = cmath.exp(-2j * math.pi / size)
        for first in range(0, n, size):
            phase = 1
            for offset in range(size // 2):
                a = first + offset
                b = a + size // 2
                even, odd = values[a], phase * values[b]
                values[a], values[b] = even + odd, even - odd
                phase *= root
        size *= 2
    return [abs(v) for v in values[:n // 2 + 1]]


def analyze(directory):
    result = {}
    for name in ('a-tx', 'a-rx', 'b-tx', 'b-rx'):
        path = directory / (name + '.wav')
        with wave.open(str(path)) as wav:
            if wav.getnchannels() != 1 or wav.getsampwidth() != 2:
                raise ValueError(f'{path}: expected mono signed 16-bit PCM')
            rate = wav.getframerate()
            raw = wav.readframes(wav.getnframes())
        samples = array('h', raw)
        if sys.byteorder != 'little':
            samples.byteswap()
        rows = []
        for start in (1, 3, 5, 7):
            block = samples[start * rate:start * rate + 4096]
            if len(block) != 4096:
                continue
            amplitudes = spectrum(block)
            peak_bin = max(range(len(amplitudes)), key=amplitudes.__getitem__)
            rows.append({'start_seconds': start, 'peak': max(map(abs, block)),
                         'dominant_hz': round(peak_bin * rate / 4096, 2)})
        result[name] = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                        'sample_rate': rate, 'frames': len(samples),
                        'fft_size': 4096, 'window': 'Hann', 'windows': rows}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    print(json.dumps(analyze(args.directory), indent=2))


if __name__ == '__main__':
    main()
