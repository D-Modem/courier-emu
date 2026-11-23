#!/usr/bin/env python3
"""Offline Bell 103 boundary audit; never feeds bytes/carrier into the emulator.

Uses NumPy and the independent UART frame scanner. Compares known marker bytes
against FSK at Apple hardware TX/RX and the I-modem SIP TX/RX boundaries. Sample
clocks are independent; capture start times are not assumed aligned.
"""
import argparse
import json
from pathlib import Path
import sys
import wave

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.decode_3453_peer_uart import uart_runs
from courier_emu.sip import ulaw_to_linear


def decode(samples, rate, mark, space, expected, baud=300):
    # 24 samples per candidate bit; nearest-sample conversion for diagnostics.
    target_rate = baud * 24
    indices = np.arange(int(len(samples) * target_rate / rate)) * rate / target_rate
    x = np.asarray(samples, dtype=float)[indices.astype(int)]
    weights = np.exp(2j * np.pi * np.array([mark, space])[:, None]
                     * np.arange(24) / target_rate)
    runs = []
    for phase in range(24):
        n = (len(x) - phase) // 24
        if n <= 0:
            continue
        blocks = x[phase:phase + n * 24].reshape(n, 24)
        energies = np.abs(blocks @ weights.T)
        bits = (energies[:, 0] > energies[:, 1]).astype(int).tolist()
        for start, data in uart_runs(bits):
            runs.append({'phase': phase, 'start_seconds': (phase + start * 24) / target_rate,
                         'bytes': len(data), 'hex': data.hex(),
                         'ascii7': bytes(b & 127 for b in data).decode('ascii', 'backslashreplace')})
    runs.sort(key=lambda row: (-row['bytes'], row['phase'], row['start_seconds']))
    prefix = expected[:16]
    starts = [r['start_seconds'] + bytes.fromhex(r['hex']).index(prefix) * 10 / baud
              for r in runs if prefix and prefix in bytes.fromhex(r['hex'])]
    return {'baud': baud, 'mark_hz': mark, 'space_hz': space,
            'payload_start_seconds': min(starts) if starts else None,
            'exact_payload_found': any(expected in bytes.fromhex(r['hex']) for r in runs),
            'ascii7_payload_found': any(expected.decode('ascii') in r['ascii7'] for r in runs),
            'runs': runs[:30]}


def first_codeword_splice(source, heard, start, end, *, anchor=256, search=512):
    """Locate a first insertion in two *identical-codec* digital captures.

    Exact byte matching only: never correlate the analog Apple capture against
    G.711 or fit a waveform to hide changes. A failed match is inconclusive.
    """
    if not 0 <= start < end <= len(source) or end - start < anchor:
        raise ValueError('invalid source comparison interval')
    at = heard.find(source[start:start + anchor])
    if at < 0:
        return {'anchor_found': False}
    offset = at - start
    pos = start
    while pos < end and pos + offset < len(heard) and source[pos] == heard[pos + offset]:
        pos += 1
    result = {'anchor_found': True, 'source_start': start, 'heard_start': at,
              'identical_prefix_samples': pos - start, 'interval_identical': pos == end}
    if pos < end:
        dest = pos + offset
        result.update(source_divergence=pos, heard_divergence=dest)
        block = source[pos:pos + 128]
        for count in range(1, search + 1):
            if len(block) == 128 and heard[dest + count:dest + count + 128] == block:
                result.update(inserted_samples=count, inserted_hex=heard[dest:dest + count].hex(),
                              resync_verified_samples=128)
                break
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--baud', type=float, default=300)
    args = parser.parse_args()
    p = args.capture
    verification = p / 'payload-verification.json'
    expected = json.loads(verification.read_text()) if verification.exists() else {}
    caller_payload = expected.get('expected_apple_to_sip', 'APPLE-TO-SIP-123').encode('ascii')
    receiver_payload = expected.get('expected_sip_to_apple', 'SIP-TO-APPLE-456').encode('ascii')
    with wave.open(str(p / 'caller/2903/apple-stereo.wav')) as wav:
        rate = wav.getframerate()
        apple = np.frombuffer(wav.readframes(wav.getnframes()), dtype='<i2').reshape(-1, 2)
    table = np.array([ulaw_to_linear(i) for i in range(256)], dtype=float)
    def sip(name):
        return table[np.frombuffer((p / 'receiver' / name).read_bytes(), dtype=np.uint8)]
    boundaries = [
        ('apple_hardware_tx', apple[:, 0], rate, 1270, 1070, caller_payload),
        ('sip_rx_from_apple', sip('apple-to-imodem.g711'), 8000, 1270, 1070, caller_payload),
        ('imodem_dsp_heard', sip('imodem-heard.g711'), 8000, 1270, 1070, caller_payload),
        ('sip_tx_to_apple', sip('imodem-to-apple.g711'), 8000, 2225, 2025, receiver_payload),
        ('apple_hardware_rx', apple[:, 1], rate, 2225, 2025, receiver_payload),
    ]
    result = {name: decode(x, r, mark, space, expected, args.baud)
              for name, x, r, mark, space, expected in boundaries}
    incoming = result['sip_rx_from_apple']
    matching = [run for run in incoming['runs']
                if b'APPLE-TO-SIP-123' in bytes.fromhex(run['hex'])]
    if matching:
        run = matching[0]
        data = bytes.fromhex(run['hex'])
        seconds = run['start_seconds'] + data.index(b'APPLE-TO-SIP-123') * 10 / args.baud
        start = round(seconds * 8000)
        end = start + round(len(caller_payload) * 10 / args.baud * 8000)
        incoming['codeword_comparison_to_dsp_heard'] = first_codeword_splice(
            (p / 'receiver/apple-to-imodem.g711').read_bytes(),
            (p / 'receiver/imodem-heard.g711').read_bytes(), start, end)
    output = args.output or p / 'bell103-boundary-audit.json'
    output.write_text(json.dumps(result, indent=2) + '\n')
    for name, row in result.items():
        print(name, 'exact=', row['exact_payload_found'], 'ascii7=', row['ascii7_payload_found'])
        for run in row['runs'][:3]:
            print(' ', round(run['start_seconds'], 3), run['hex'], repr(run['ascii7']))


if __name__ == '__main__':
    main()
