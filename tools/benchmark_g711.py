#!/usr/bin/env python3
"""Compare scalar and native G.711 packet paths, including marshalling/queues.

Build/load the native library before timing. No sockets, firmware execution,
clock changes or live calls. These are codec-path costs, not end-to-end modem
throughput or stability results.
"""
import argparse
from collections import deque
import hashlib
import json
import platform
import statistics
import time

from courier_emu import g711_native
from courier_emu.dsp import load_library
from courier_emu.sip import (SipSession, linear_to_ulaw, linear_to_alaw,
                             ulaw_to_linear, alaw_to_linear)


def benchmark(packets=10000, pairs=4):
    if packets <= 0 or pairs <= 0:
        raise ValueError('packets and pairs must be positive')
    load_library()  # Compilation/dlopen are deliberately outside measurements.
    if not g711_native.available():
        raise RuntimeError('native G.711 ABI unavailable or COURIER_NATIVE_G711=0')
    result = {'packets_per_sample': packets, 'packet_samples': 160,
              'platform': platform.platform(), 'codecs': {}}
    for name, encode, decode in (('pcmu', linear_to_ulaw, ulaw_to_linear),
                                  ('pcma', linear_to_alaw, alaw_to_linear)):
        law = 0 if name == 'pcmu' else 1
        samples = [(k * 7919) % 65536 - 32768 for k in range(160)]
        expected = bytes(map(encode, samples))
        octets = bytes(range(160))
        expected_rx = list(map(decode, octets))
        session = object.__new__(SipSession)
        session._encode = encode
        session._tx_audio = deque()
        target = deque()
        timings = {direction: {'scalar': [], 'native': []}
                   for direction in ('encode_packet', 'decode_block')}
        # Warm bindings and both paths before alternating unprofiled samples.
        assert g711_native.encode_pcm16(samples, law) == expected
        assert g711_native.decode_octets(octets, law) == expected_rx
        for trial in range(pairs):
            order = ('scalar', 'native') if trial % 2 == 0 else ('native', 'scalar')
            for kind in order:
                start = time.perf_counter()
                for _ in range(packets):
                    session._tx_audio.extend(samples)
                    if kind == 'native':
                        actual = session._encode_rtp_audio()
                    else:
                        actual = bytes(encode(session._tx_audio.popleft()) for _ in range(160))
                elapsed = time.perf_counter() - start
                assert actual == expected and not session._tx_audio
                timings['encode_packet'][kind].append(elapsed)
                start = time.perf_counter()
                for _ in range(packets):
                    target.clear()
                    if kind == 'native':
                        target.extend(g711_native.decode_octets(octets, law))
                    else:
                        target.extend(decode(value) for value in octets)
                elapsed = time.perf_counter() - start
                assert list(target) == expected_rx
                timings['decode_block'][kind].append(elapsed)
        summary = {}
        for direction, values in timings.items():
            scalar = statistics.median(values['scalar'])
            native = statistics.median(values['native'])
            summary[direction] = {'scalar_seconds': scalar, 'native_seconds': native,
                                  'speedup': scalar / native, 'samples': values}
        summary['payload_sha256'] = hashlib.sha256(expected).hexdigest()
        result['codecs'][name] = summary
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packets', type=int, default=10000)
    parser.add_argument('--pairs', type=int, default=4)
    args = parser.parse_args()
    if args.packets <= 0 or args.pairs <= 0:
        parser.error('packets and pairs must be positive')
    print(json.dumps(benchmark(args.packets, args.pairs), indent=2))


if __name__ == '__main__':
    main()
