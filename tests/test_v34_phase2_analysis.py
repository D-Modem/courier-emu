import pytest

np = pytest.importorskip('numpy')
from tools.analyze_bearer_handshake import crc16
from tools.analyze_v34_phase2 import decode, fields


@pytest.mark.parametrize('length,carrier', [(17,2400),(30,1200),(38,2400),(77,1200)])
def test_info_frames_acquired_across_timing_phases(length,carrier):
    body=[(i*7//3)&1 for i in range(length)]
    fcs=crc16(body)
    bits=[0]*120+[int(b) for b in '111101110010']+body
    bits += [(fcs>>i)&1 for i in range(16)]+[1]*4+[0]*160
    n=np.arange(int(len(bits)*8000/600))
    phase=np.cumsum(bits)*np.pi
    x=1500*np.cos(2*np.pi*carrier*n/8000+phase[(n*600//8000).astype(int)])
    if carrier==2400:
        x+=2000*np.cos(2*np.pi*1800*n/8000)
    frames=decode(x,carrier)
    assert any(f['body_bits']==''.join(map(str,body)) and f['timing_phase_votes']>=3
               for f in frames)


@pytest.mark.parametrize('selector,protocol', [(0,'V.34'),(4,'V.34'),
                                             (5,'V.34'),(6,'V.90'),(7,'reserved')])
def test_info1a_protocol_selector_uses_itu_numbering(selector, protocol):
    body = list('0' * 38)
    body[22:25] = f'{5:03b}'[::-1]
    body[25:28] = f'{selector:03b}'[::-1]
    # Last three body bits are reserved, NOT the protocol selector.
    body[-3:] = '111'
    assert fields(''.join(body)) == dict(upstream_symbol_rate_code=5,
        downstream_symbol_rate_code=selector, protocol_request=protocol)


def test_recorded_v90_request_then_v34_fallback():
    request = '00000000000000011001000010110000000000'
    fallback = '01000000000000000010110010011111111111'
    assert fields(request)['protocol_request'] == 'V.90'
    assert fields(fallback)['protocol_request'] == 'V.34'


@pytest.mark.parametrize('law,expected', [('0', 'mu-law'), ('1', 'A-law')])
def test_info0d_law_is_body_bit_27_not_the_legacy_clock_field(law, expected):
    body = list('0' * 30)
    body[14:16] = '11'  # Common INFO0 clock bits are not this extension.
    body[26] = '1'
    body[27] = law
    assert fields(''.join(body)) == {
        'pcm_law': expected, 'power_measured_at_codec_output': True}


def test_recorded_7910_info0d_advertises_alaw():
    body = '111001101000010000101100011100'
    assert fields(body)['pcm_law'] == 'A-law'
    assert fields('0' * 17) == {'ack': 0}


def test_silence_does_not_form_info1():
    assert decode(np.zeros(8000),1200)==[]
