import json
import struct
import wave

import pytest

from tools.render_apple_audio import render


def capture(tmp_path, **changes):
    event = dict(off_hook=True, resetting=False, rate=10286,
                 tx_start=1, rx_start=1, tx_count=2, rx_count=2)
    event.update(changes)
    (tmp_path / 'codec-hardware-frames.jsonl').write_text(json.dumps(event) + '\n')
    for channel, samples in [('tx', [999, 100, -200]), ('rx', [888, -300, 400])]:
        (tmp_path / f'codec-hardware-{channel}.s16').write_bytes(struct.pack('<3h', *samples))
    return tmp_path / 'stereo.wav'


def test_preserves_raw_levels_and_channel_order(tmp_path):
    output = capture(tmp_path)
    report = render(tmp_path, output)
    with wave.open(str(output), 'rb') as wav:
        assert wav.getnchannels() == 2
        assert wav.getframerate() == 10286
        assert struct.unpack('<4h', wav.readframes(2)) == (100, -300, -200, 400)
    assert report['seconds'] == 2 / 10286


@pytest.mark.parametrize('changes, message', [
    ({'off_hook': False}, 'no complete'),
    ({'resetting': True}, 'no complete'),
    ({'failed': True}, 'no complete'),
    ({'rx_count': 1}, 'unequal'),
    ({'tx_start': 3}, 'truncated'),
    ({'rate': 7200.5}, 'integer'),
])
def test_rejects_unpairable_or_absent_audio(tmp_path, changes, message):
    output = capture(tmp_path, **changes)
    with pytest.raises(ValueError, match=message):
        render(tmp_path, output)
    assert not output.exists()
