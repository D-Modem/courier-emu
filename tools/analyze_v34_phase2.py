#!/usr/bin/env python3
"""Offline V.34 DPSK frames, including INFO1, with a timing-phase search.

Input: mono PCM16 8-kHz WAV. No hardware opened. Full fill pattern and CRC
are required; nearby timing phases vote on each candidate. Signal times are
estimates on the recording clock, not physical wire timestamps.
"""
import argparse
import json
from pathlib import Path
import sys
import wave

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.analyze_bearer_handshake import crc16

RATE = 8000
LENGTHS = (7, 17, 30, 38, 77)
NAMES = {7:'7-bit vendor frame',17:'INFO0',30:'INFO0d',38:'INFO1a',77:'INFO1c/INFO1d'}


def fields(body):
    if len(body) == 17:
        return {'ack': int(body[16])}
    def value(start, count):
        return int(body[start:start+count][::-1], 2)
    if len(body) == 30:
        # INFO0d extension: after the 17 common bits, nominal/max power
        # occupy 4/5 bits, followed by the measurement point and PCM law.
        # This describes the digital peer, not necessarily the RTP codec.
        return {'pcm_law': 'A-law' if value(27, 1) else 'mu-law',
                'power_measured_at_codec_output': bool(value(26, 1))}
    if len(body) == 38:
        # Body begins at ITU bit 12, after the 12-bit sync. V.90 Table 10
        # reuses the V.34 downstream symbol-rate field (ITU bits 37:39).
        selector = value(25, 3)
        return {'upstream_symbol_rate_code': value(22, 3),
                'downstream_symbol_rate_code': selector,
                'protocol_request': ('V.90' if selector == 6 else
                                     'V.34' if selector <= 5 else 'reserved')}
    if len(body) != 77:
        return {}
    return {'probing_rows': [dict(symbol_rate=baud,
            high_carrier=value(13+9*i,1),preemphasis=value(14+9*i,4),
            projected_rate_code=value(18+9*i,4))
            for i,baud in enumerate((2400,2743,2800,3000,3200))]}


def decode(x, carrier):
    candidates = []
    step = RATE/600
    kernel = np.ones(13)/13
    for first in range(0,len(x)-int(.12*RATE),RATE//4):
        crop = x[first:first+RATE//2].astype(float)
        z = crop*np.exp(-2j*np.pi*carrier*np.arange(len(crop))/RATE)
        z = np.convolve(z.real,kernel,'same') + 1j*np.convolve(z.imag,kernel,'same')
        for phase,off in enumerate(np.arange(0,step,.25)):
            symbols=z[np.round(np.arange(off,len(z)-1,step)).astype(int)]
            bits=[int(v.real<0) for v in symbols[1:]*np.conj(symbols[:-1])]
            text=''.join(map(str,bits))
            pos=text.find('111101110010')
            while pos>=0:
                for length in LENGTHS:
                    end=pos+12+length+16
                    if end>len(bits):
                        continue
                    if crc16(bits[pos+12:end]) not in (0,0xf0b8):
                        continue
                    body=text[pos+12:pos+12+length]
                    candidates.append((first+off+(pos+1)*step,length,body,phase))
                pos=text.find('111101110010',pos+1)
    groups=[]
    for instant,length,body,phase in sorted(candidates):
        group=next((g for g in reversed(groups) if g['length']==length and g['body']==body
                    and abs(instant-g['times'][-1])<1.5*step),None)
        if group is None:
            group=dict(length=length,body=body,times=[],phases=set())
            groups.append(group)
        group['times'].append(instant)
        group['phases'].add(phase)
    return [dict(time_s=round(float(np.median(g['times']))/RATE,5),
                 kind=NAMES[g['length']],body_length=g['length'],body_bits=g['body'],
                 crc_ok=True,timing_phase_votes=len(g['phases']),**fields(g['body']))
            for g in groups if len(g['phases'])>=3]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('wav',type=Path)
    parser.add_argument('--carrier',type=float,choices=(1200,2400),required=True)
    args=parser.parse_args()
    with wave.open(str(args.wav)) as f:
        if (f.getframerate(),f.getnchannels(),f.getsampwidth()) != (RATE,1,2):
            parser.error('requires mono PCM16 8-kHz WAV')
        x=np.frombuffer(f.readframes(f.getnframes()),dtype='<i2')
    print(json.dumps(dict(file=str(args.wav),carrier_hz=args.carrier,
                         events=decode(x,args.carrier)),indent=2))


if __name__=='__main__':
    main()
