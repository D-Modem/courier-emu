"""Offline demodulator/byte-splice controls; no hardware or firmware mutation."""
import pytest

np = pytest.importorskip('numpy')
from tools.analyze_apple_bell103 import decode, first_codeword_splice


@pytest.mark.parametrize('rate', [7200, 8000, 10286])
@pytest.mark.parametrize('mark,space', [(1270, 1070), (2225, 2025)])
def test_audit_recovers_known_marker_at_both_hardware_grids(rate, mark, space):
    payload = b'APPLE-TO-SIP-123'
    bits = [1] * 32
    for value in payload:
        bits.extend([0, *[(value >> k) & 1 for k in range(8)], 1])
    bits.extend([1] * 32)
    bit_index = np.minimum((np.arange(int(len(bits) * rate / 300)) * 300 / rate).astype(int),
                           len(bits) - 1)
    frequency = np.where(np.array(bits)[bit_index], mark, space)
    phase = .37 + 2 * np.pi * np.cumsum(frequency) / rate
    samples = np.round(3000 * np.sin(phase))
    result = decode(samples, rate, mark, space, payload)
    assert result['exact_payload_found']


def test_silence_is_not_a_payload():
    result = decode(np.zeros(8000), 8000, 2225, 2025, b'KNOWN')
    assert not result['exact_payload_found']
    assert not result['ascii7_payload_found']


def test_exact_comparison_identifies_inserted_mu_law_silence():
    source = np.random.default_rng(103).integers(0, 254, size=2000, dtype=np.uint8).tobytes()
    heard = b'\xff' * 300 + source[:1000] + b'\xff' * 30 + source[1000:]
    report = first_codeword_splice(source, heard, 400, 1400)
    assert report['identical_prefix_samples'] == 600
    assert report['source_divergence'] == 1000
    assert report['heard_divergence'] == 1300
    assert report['inserted_samples'] == 30
    assert report['inserted_hex'] == 'ff' * 30


def test_identical_digital_stream_has_no_splice():
    source = np.random.default_rng(103).integers(0, 254, size=1000, dtype=np.uint8).tobytes()
    report = first_codeword_splice(source, b'\xff' * 100 + source, 100, 900)
    assert report['interval_identical']
    assert 'inserted_samples' not in report
