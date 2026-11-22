import json
import math
import struct

import pytest

np = pytest.importorskip('numpy')
from courier_emu.resample import BandLimitedResampler
from tools.audit_apple_audio_path import pcm_metrics, replay_tx


def capture(tmp_path):
    codec = []
    hardware = []
    ce, he = [], []
    converter = BandLimitedResampler()
    for index, (rate, hook, reset) in enumerate([(7200, False, False),
                                                (9600, True, False),
                                                (7200, True, True)]):
        t = index * 2 + 1
        if reset:
            converter = BandLimitedResampler()
            he.append(dict(time=t - .5, rate=10286, resetting=True, tx_count=0))
        samples = [round(3000 * math.sin(2 * math.pi * 1200 * i / rate)) for i in range(144)]
        output = converter.convert(samples, rate, 10286)
        ce.append(dict(time=t, rate=rate, tx_start=len(codec), tx_count=len(samples),
                       off_hook=hook, tx_gain=.5))
        he.append(dict(time=t + .01, rate=10286, resetting=False, tx_count=len(output)))
        codec.extend(samples)
        hardware.extend(round(v * .5) if hook else 0 for v in output)
    for name, values in [('codec-tx', codec), ('codec-hardware-tx', hardware)]:
        (tmp_path / (name + '.s16')).write_bytes(struct.pack(f'<{len(values)}h', *values))
    for name, rows in [('codec', ce), ('codec-hardware', he)]:
        (tmp_path / (name + '-frames.jsonl')).write_text(''.join(json.dumps(r) + '\n' for r in rows))
    return hardware


def test_converter_replay_follows_rates_gain_mute_and_generation_reset(tmp_path):
    capture(tmp_path)
    report = replay_tx(tmp_path)
    assert report['exact_match']
    assert report['reset_generations'] == 1


def test_replay_identifies_a_single_modified_sample(tmp_path):
    samples = capture(tmp_path)
    samples[20] = 123
    (tmp_path / 'codec-hardware-tx.s16').write_bytes(struct.pack(f'<{len(samples)}h', *samples))
    report = replay_tx(tmp_path)
    assert not report['exact_match']
    assert report['different_samples_in_common_prefix'] == 1
    assert report['first_different_sample'] == 20


def test_metrics_do_not_normalize_away_dc_or_clipping():
    report = pcm_metrics([-32768, -32768, -32768])
    assert report['near_rail_samples'] == 3
    assert report['mean'] == -32768
    assert report['ac_rms'] == 0
    assert report['rms'] == 32768
