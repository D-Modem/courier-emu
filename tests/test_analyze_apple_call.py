"""Offline capture analysis; numpy is an optional analysis-tool dependency."""
import pytest

np = pytest.importorskip('numpy')
from tools.analyze_apple_call import crc_frames, decode
from tools.analyze_bearer_handshake import crc16


def test_info0_detected_under_stronger_guard_tone():
    body = [int(b) for b in '11111111100001000']
    fcs = crc16(body) ^ 0xffff
    bits = [0]*120 + [int(b) for b in '01110010'] + body
    bits += [(fcs >> i) & 1 for i in range(16)] + [0]*240
    n = np.arange(int(len(bits)*8000/600))
    symbols = (n*600//8000).astype(int)
    phase = np.cumsum(bits)*np.pi
    x = 1000*np.cos(2*np.pi*2400*n/8000 + phase[symbols])
    x += 1400*np.cos(2*np.pi*1800*n/8000)
    frames = crc_frames(x)
    assert any(f['carrier_hz'] == 2400 and f['body_bits'] == ''.join(map(str, body))
               and f['crc_ok'] for f in frames)


def test_quiet_capture_does_not_create_crc_frames():
    assert crc_frames(np.zeros(8000)) == []


def test_hardware_rx_rate_metadata_is_not_treated_as_codec_rate(tmp_path):
    pcm = np.array([2000]*1029, dtype='<i2')
    (tmp_path/'codec-rx.s16').write_bytes(pcm.tobytes())
    event = dict(off_hook=True, rate=7200, rx_rate=10286, rx_start=0, rx_count=1029)
    rx = decode(tmp_path, [event], 'rx')
    assert abs(len(rx)-800) <= 2


def test_recorded_gain_is_applied_without_changing_rx(tmp_path):
    pcm = np.array([2000]*800, dtype='<i2')
    for channel in ('tx', 'rx'):
        (tmp_path/f'codec-{channel}.s16').write_bytes(pcm.tobytes())
    events = [dict(off_hook=True,rate=8000,tx_gain=.25,
                   tx_start=0,tx_count=800,rx_start=0,rx_count=800)]
    tx = decode(tmp_path, events, 'tx')
    rx = decode(tmp_path, events, 'rx')
    assert np.max(np.abs(tx.astype(float)-rx.astype(float)*.25)) <= 1
