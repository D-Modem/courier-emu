#!/usr/bin/env python3
"""Offline spectrum/FSK timeline from all-generation Apple codec captures.

Needs numpy (the sibling v90modem venv has it). Does not open hardware. Times
are in each channel's captured sample clock, excluding on-hook/reset gaps;
they are not exact physical DAC/ADC timestamps. RX is post DC/rate conversion.
TX applies recorded host gain; older captures without that field assume unity.
"""
import argparse
from pathlib import Path
import json
import sys
import wave

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from courier_emu.resample import BandLimitedResampler
from tools.analyze_bearer_handshake import windows, runs, fsk_bits, octets, info0, ulaw_table

RATE = 8000


def decode(recording, events, channel, prefix='codec'):
    source = np.frombuffer((recording / f'{prefix}-{channel}.s16').read_bytes(), dtype='<i2')
    converter = BandLimitedResampler()
    values = []
    for event in events:
        if not event['off_hook'] or f'{channel}_count' not in event:
            continue
        start, count = event[f'{channel}_start'], event[f'{channel}_count']
        rate = event.get(f'{channel}_rate', event['rate'])
        converted = converter.convert(source[start:start+count].tolist(), rate, RATE)
        if channel == 'tx':
            gain = event.get('tx_gain', 1.0)
            converted = [max(-32768, min(32767, round(value*gain))) for value in converted]
        values.extend(converted)
    return np.array(values, dtype=np.int16)


def crc_frames(x):
    """Search independently of the dominant peak (e.g. a strong guard tone).

    Cropping first also avoids repeatedly mixing/convolving the entire call.
    Returned times bound search windows, not exact frame boundaries.
    """
    events, last_seen = [], {}
    for carrier in (1200, 2400):
        for start in range(0, len(x)-int(.12*RATE), RATE//4):
            crop = x[start:start+RATE//2]
            for frame in info0(crop, carrier, 0, len(crop)/RATE,
                               body_lengths=(7, 17, 30, 38, 77)):
                key = carrier, frame['body_length'], frame['body_bits']
                previous = last_seen.get(key, -RATE)
                last_seen[key] = start
                if start-previous <= RATE//2:
                    continue
                event = {'from_s': start/RATE, 'to_s': (start+len(crop))/RATE,
                    'kind': 'DPSK-CRC-frame', 'carrier_hz': carrier,
                    'timing': 'search window; decision time is demodulator timing, not a DAC timestamp',
                    'decision_time_s': (start+frame['sync_decision_sample'])/RATE, **frame}
                event['sequence'] = {7: 'x2 modulation-parameter candidate',
                    17: 'V.34 INFO0 / V.90 INFO0a', 30: 'V.90 INFO0d',
                    38: 'INFO1a', 77: 'V.34 INFO1c / V.90 INFO1d'}[frame['body_length']]
                if frame['body_length'] == 38:
                    selector = sum(int(frame['body_bits'][25+i]) << i for i in range(3))
                    event['info1a_protocol_selector'] = selector
                    event['protocol_request'] = 'V.90' if selector == 6 else 'V.34' if selector < 6 else 'reserved'
                events.append(event)
    return events


def timeline(pcm):
    x = pcm.astype(float)
    win = windows(x)
    events = []
    for frequency in (400, 1100, 1200, 1650, 1800, 2100, 2250, 2400):
        for start, end in runs(win, lambda r, p, f=frequency: abs(p-f)<=40 and r>100, .25):
            events.append({'from_s': round(start, 3), 'to_s': round(end, 3),
                           'kind': 'tone-band', 'frequency_hz': frequency})
    for channel, mark, space, low, high in ((1,980,1180,940,1220),(2,1650,1850,1600,1900)):
        for start, end in runs(win, lambda r,p: low<=p<=high and r>100, .3):
            # Restrict very long candidates: tones/noise in this band are not
            # automatically V.8; repeated framed octets are separate evidence.
            end = min(end, start+8)
            bits = fsk_bits(x, mark, space, int(start*RATE), int(end*RATE))
            data = octets(bits)
            if len(data) >= 3:
                events.append({'from_s': round(start,3), 'to_s': round(end,3),
                    'kind': 'FSK-candidate', 'v21_channel': channel,
                    'octets_hex': bytes(data[:80]).hex(' '), 'framed_octets': len(data)})
    events.extend(crc_frames(x))
    energy = []
    for start in range(0,len(x)-RATE+1,RATE):
        block=x[start:start+RATE]
        weighted=block*np.hanning(len(block))
        spectrum=np.abs(np.fft.rfft(weighted))**2
        peak=int(np.argmax(spectrum[100:3601]))+100
        energy.append({'second':start//RATE,'rms':round(float(np.sqrt(np.mean(block**2))),1),
                       'peak_hz':peak,'near_rail_samples':int(np.count_nonzero(np.abs(block)>=32760))})
    return {'seconds':len(x)/RATE,'events':sorted(events,key=lambda e:e['from_s']),
            'one_second_windows':energy,
            'warning':'Spectral bands/FSK candidates are not a validated call-progress classifier.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('recording',type=Path)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--boundary', choices=['codec', 'hardware'], default='codec')
    parser.add_argument('--g711', action='store_true', help='input is one selected raw PCMU RTP stream, not an Apple capture directory')
    args=parser.parse_args()
    prefix = 'codec-hardware' if args.boundary == 'hardware' else 'codec'
    if args.g711 and args.output is None:
        parser.error('--g711 requires a separate --output directory')
    out=args.output or args.recording/('analysis-hardware' if args.boundary == 'hardware' else 'analysis')
    out.mkdir(parents=True,exist_ok=True)
    events=[] if args.g711 else [json.loads(x) for x in (args.recording/f'{prefix}-frames.jsonl').read_text().splitlines()]
    result={}
    for channel in (('wire',) if args.g711 else ('tx','rx')):
        pcm=(ulaw_table()[np.frombuffer(args.recording.read_bytes(),dtype=np.uint8)]
             if args.g711 else decode(args.recording,events,channel,prefix))
        with wave.open(str(out/f'{channel}-8000.wav'),'wb') as f:
            f.setparams((1,2,RATE,0,'NONE','not compressed'))
            f.writeframes(pcm.astype('<i2').tobytes())
        result[channel]=timeline(pcm)
    (out/'timeline.json').write_text(json.dumps(result,indent=2)+'\n')
    for channel in result:
        print(channel,'seconds',result[channel]['seconds'])
        for event in result[channel]['events']:
            print(event)


if __name__=='__main__':
    main()
