"""Offline decoder tests; NumPy is an optional analysis-only dependency."""
import pytest

np = pytest.importorskip('numpy')

from tools.analyze_bearer_handshake import crc16, info0, main


def waveform(body, carrier, complement=True):
    crc = crc16(body) ^ (0xffff if complement else 0)
    frame = [1]*4 + [0,1,1,1,0,0,1,0] + body + [(crc>>i)&1 for i in range(16)] + [1]*4
    bits = np.array(frame*3)
    n = np.arange(int(len(bits)*8000/600))
    phase = np.cumsum(bits)[np.minimum((n*600//8000).astype(int), len(bits)-1)]
    return 10000*np.cos(2*np.pi*carrier*n/8000 + np.pi*phase)


@pytest.mark.parametrize('length,carrier', [(17,2400), (30,1200), (38,2400), (77,1200)])
@pytest.mark.parametrize('complement', [False, True])
def test_crc_and_framing_decode_known_dpsk_payload(length, carrier, complement):
    body = np.random.default_rng(length).integers(0,2,length).tolist()
    x = waveform(body, carrier, complement)
    frames = info0(x, carrier, 0, len(x)/8000, body_lengths=(17,30,38,77))
    matching = [f for f in frames if f['body_length']==length and f['body_bits']==''.join(map(str,body))]
    assert matching
    assert any(f['fill_before']=='1111' and f['fill_after']=='1111' for f in matching)
    assert all(f['crc_residue']==(0xf0b8 if complement else 0) for f in matching)


def test_short_7e_silence_is_not_startup_or_scrambled_data(tmp_path):
    path=tmp_path/'quiet.g711'
    path.write_bytes(bytes([0x7e])*8000)
    result=main(str(path))
    assert not result['events']


def test_info1a_protocol_selection_field_is_decoded_without_claiming_connect():
    from tools.analyze_apple_call import crc_frames
    body = list(map(int, '00000000000000111001000010110000000000'))
    frames = crc_frames(waveform(body, 2400, False))
    matching = [f for f in frames if f['body_length']==38 and f['body_bits']==''.join(map(str,body))]
    assert matching
    assert matching[0]['info1a_protocol_selector'] == 6
    assert matching[0]['protocol_request'] == 'V.90'
    assert matching[0]['sequence'] == 'INFO1a'
    assert matching[0]['kind'] == 'DPSK-CRC-frame'
