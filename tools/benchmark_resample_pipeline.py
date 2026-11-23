#!/usr/bin/env python3
"""Socket-free PCM -> resample -> RTP codec/queue -> resample pipeline.

Compare pinned alternating child processes, optionally loading the *actual*
pre-change resample.py/sip.py via --reference-dir. No clocks or buffers change.
Compilation, filter design, and a one-block warm-up are outside the measurement.
"""
import argparse
from array import array
from collections import deque
import hashlib
import importlib
import json
import math
from pathlib import Path
import platform
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kind', choices=('fixed', 'polyphase'), required=True)
    parser.add_argument('--seconds', type=int, default=20)
    parser.add_argument('--reference-dir', type=Path)
    args = parser.parse_args()
    if args.seconds <= 0:
        parser.error('--seconds must be positive')
    from courier_emu.dsp import load_library
    load_library()
    if args.reference_dir:
        for name in ('resample', 'sip'):
            module = importlib.import_module('courier_emu.' + name)
            source = args.reference_dir / (name + '.py')
            exec(compile(source.read_text(), str(source), 'exec'), module.__dict__)
    from courier_emu.resample import BandLimitedResampler
    from courier_emu.sip import PolyphaseResampler, SipSession, linear_to_ulaw
    from courier_emu import g711_native
    if not g711_native.available():
        raise RuntimeError('benchmark requires native G.711 for both variants')
    rate = 48000 if args.kind == 'fixed' else 7200
    if args.kind == 'fixed':
        tx, rx = BandLimitedResampler(), BandLimitedResampler()
        send = lambda values: tx.convert(values, rate, 8000)
        receive = lambda values: rx.convert(values, 8000, rate)
    else:
        tx, rx = PolyphaseResampler(rate, 8000), PolyphaseResampler(8000, rate)
        send, receive = tx.convert, rx.convert
    session = object.__new__(SipSession)  # No SIP socket or network activity.
    session._encode = linear_to_ulaw
    session._tx_audio = deque()
    size = rate // 50
    source = [int(23000 * math.sin(2 * math.pi * 697 * n / rate))
              + (n * 7919 % 3001 - 1500) for n in range(rate)]
    blocks = [source[n:n + size] for n in range(0, rate, size)]
    def process(block, wire, pcm):
        packets = count = 0
        session._tx_audio.extend(send(block))
        while len(session._tx_audio) >= 160:
            payload = session._encode_rtp_audio()
            decoded = g711_native.decode_octets(payload, 0)
            output = receive(decoded)
            wire.update(payload)
            pcm.update(array('h', output).tobytes())
            count += len(output)
            packets += 1
        return packets, count
    wire, pcm = hashlib.sha256(), hashlib.sha256()
    process(blocks[0], wire, pcm)  # Warm table packing and bindings too.
    wire, pcm = hashlib.sha256(), hashlib.sha256()
    packets = count = 0
    start_cpu, start_wall = time.process_time(), time.perf_counter()
    for n in range(args.seconds * 50):
        p, c = process(blocks[(n + 1) % len(blocks)], wire, pcm)
        packets += p
        count += c
    elapsed_wall, elapsed_cpu = time.perf_counter() - start_wall, time.process_time() - start_cpu
    def state(r):
        if args.kind == 'fixed':
            values = [r._position, *r._history, *r._recent_input]
            counters = [r.converted, r.input_rate, r.output_rate]
        else:
            values, counters = r._buffer, [r._origin, r._output, r.up, r.down]
        return {'counters': counters,
                'float_state_sha256': hashlib.sha256(array('d', values).tobytes()).hexdigest()}
    print(json.dumps({'kind': args.kind, 'seconds': args.seconds,
        'platform': platform.platform(), 'python': sys.version,
        'reference_dir': str(args.reference_dir) if args.reference_dir else None,
        'wall_seconds': elapsed_wall, 'cpu_seconds': elapsed_cpu,
        'result': {'packets': packets, 'pcm_samples': count,
                   'wire_sha256': wire.hexdigest(), 'pcm_sha256': pcm.hexdigest(),
                   'tx': state(tx), 'rx': state(rx), 'queued_tx': list(session._tx_audio)}}))


if __name__ == '__main__':
    main()
