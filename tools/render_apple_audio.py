#!/usr/bin/env python3
"""Export fixed-hardware-grid Apple captures as stereo WAV (TX left, RX right).

Offline only; no hardware access or NumPy dependency. Preserves raw levels and
DC: no normalization, AGC or synthetic audio. Frame pairing is at the helper
exchange boundary, NOT a measurement of analog round-trip delay.
"""
import argparse
import json
from pathlib import Path
import struct
import wave


def render(recording: Path, output: Path) -> dict:
    events = [json.loads(line) for line in
              (recording / 'codec-hardware-frames.jsonl').read_text().splitlines()]
    tx = (recording / 'codec-hardware-tx.s16').read_bytes()
    rx = (recording / 'codec-hardware-rx.s16').read_bytes()
    frames = bytearray()
    rate = None
    for event in events:
        if not event['off_hook'] or event.get('resetting') or event.get('failed'):
            continue
        count = event['tx_count']
        if count == 0:
            continue  # immediate control requests have no PCM
        if count != event.get('rx_count'):
            raise ValueError('unequal TX/RX counts: cannot pair hardware frames')
        current_rate = event['rate']
        if int(current_rate) != current_rate or current_rate <= 0:
            raise ValueError('WAV requires a positive integer hardware rate')
        if rate is not None and rate != current_rate:
            raise ValueError('hardware rate changed: refusing to relabel PCM')
        rate = int(current_rate)
        start_tx, start_rx = event['tx_start'] * 2, event['rx_start'] * 2
        if min(start_tx, start_rx) < 0:
            raise ValueError('negative PCM offset')
        left = tx[start_tx:start_tx + count * 2]
        right = rx[start_rx:start_rx + count * 2]
        if len(left) != count * 2 or len(right) != count * 2:
            raise ValueError('truncated hardware PCM')
        for (a,), (b,) in zip(struct.iter_unpack('<h', left), struct.iter_unpack('<h', right)):
            frames.extend(struct.pack('<hh', a, b))
    if rate is None:
        raise ValueError('no complete off-hook hardware audio')
    with wave.open(str(output), 'wb') as wav:
        wav.setparams((2, 2, rate, 0, 'NONE', 'not compressed'))
        wav.writeframes(frames)
    return {'path': str(output), 'sample_rate': rate, 'seconds': len(frames) / 4 / rate,
            'left': 'hardware TX (post host gain)', 'right': 'raw hardware RX (before DC blocker)',
            'warning': 'Off-hook exchanges only; reset gaps omitted. Not analog-delay aligned.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('recording', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    output = args.output or args.recording / 'apple-stereo.wav'
    print(json.dumps(render(args.recording, output), indent=2))


if __name__ == '__main__':
    main()
