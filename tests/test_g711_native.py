from collections import deque
import ctypes
from types import SimpleNamespace

import pytest

from courier_emu import dsp, g711_native
from courier_emu.sip import (SipSession, linear_to_ulaw, linear_to_alaw,
                             ulaw_to_linear, alaw_to_linear)


@pytest.fixture(autouse=True)
def native(monkeypatch):
    dsp.load_library()
    monkeypatch.setenv('COURIER_NATIVE_G711', '1')
    monkeypatch.setattr(g711_native, '_binding', None)
    assert g711_native.available()


@pytest.mark.parametrize('law,encode', [(0, linear_to_ulaw), (1, linear_to_alaw)])
def test_every_pcm16_value_encodes_exactly(law, encode):
    samples = list(range(-32768, 32768))
    assert g711_native.encode_pcm16(samples, law) == bytes(map(encode, samples))


@pytest.mark.parametrize('law,decode', [(0, ulaw_to_linear), (1, alaw_to_linear)])
def test_every_codeword_decodes_exactly(law, decode):
    octets = bytes(range(256))
    assert g711_native.decode_octets(octets, law) == list(map(decode, octets))
    assert g711_native.decode_octets(bytearray(octets), law) == list(map(decode, octets))


@pytest.mark.parametrize('size', [0, 1, 159, 160, 161, 3000])
@pytest.mark.parametrize('law,encode,decode', [(0, linear_to_ulaw, ulaw_to_linear),
                                             (1, linear_to_alaw, alaw_to_linear)])
def test_arbitrary_batch_sizes(size, law, encode, decode):
    samples = [(i * 7919) % 65536 - 32768 for i in range(size)]
    encoded = g711_native.encode_pcm16(samples, law)
    assert encoded == bytes(map(encode, samples))
    assert g711_native.decode_octets(encoded, law) == list(map(decode, encoded))


@pytest.mark.parametrize('values', [[-32769], [32768], [2**100], [1.5], [True], ['2']])
def test_non_pcm16_inputs_decline_without_mutation(values):
    before = list(values)
    assert g711_native.encode_pcm16(values, 0) is None
    assert values == before


def test_iterators_and_custom_integers_are_not_coerced_when_declining():
    iterator = iter([1, 2])
    assert g711_native.encode_pcm16(iterator, 0) is None
    assert next(iterator) == 1
    class Integer(int):
        def __int__(self):
            pytest.fail('must not convert on a declined fast path')
    assert g711_native.encode_pcm16([Integer(1)], 0) is None


def test_missing_library_symbol_and_no_loaded_core_remain_safe(monkeypatch):
    monkeypatch.setattr(dsp, 'loaded_library', lambda: None)
    monkeypatch.setattr(dsp, 'load_library', lambda: pytest.fail('must not build/load a core'))
    assert not g711_native.available()
    assert g711_native.encode_pcm16([1], 0) is None
    assert g711_native.decode_octets(b'\0', 0) is None
    old = SimpleNamespace()
    monkeypatch.setattr(dsp, 'loaded_library', lambda: old)
    assert not g711_native.available()
    assert not g711_native.available()  # Missing optional ABI is cached safely.


def test_explicit_disable_and_invalid_laws(monkeypatch):
    assert g711_native.encode_pcm16([1], 2) is None
    assert g711_native.decode_octets(b'\0', 2) is None
    monkeypatch.setenv('COURIER_NATIVE_G711', '0')
    assert not g711_native.available()
    assert g711_native.encode_pcm16([1], 0) is None
    assert g711_native.decode_octets(b'\0', 0) is None


def test_benchmark_smoke_covers_codec_paths_without_a_speed_threshold():
    from tools.benchmark_g711 import benchmark
    report = benchmark(packets=3, pairs=2)
    assert set(report['codecs']) == {'pcmu', 'pcma'}
    for codec in report['codecs'].values():
        for direction in ('encode_packet', 'decode_block'):
            assert codec[direction]['speedup'] > 0
            assert len(codec[direction]['samples']['scalar']) == 2
            assert len(codec[direction]['samples']['native']) == 2
    with pytest.raises(ValueError):
        benchmark(packets=0)


def test_native_failure_raises_instead_of_dropping_samples(monkeypatch):
    monkeypatch.setattr(g711_native, '_functions', lambda: (lambda *args: 0, lambda *args: 0))
    with pytest.raises(RuntimeError, match='encoding failed'):
        g711_native.encode_pcm16([1], 0)
    with pytest.raises(RuntimeError, match='decoding failed'):
        g711_native.decode_octets(b'\0', 0)


def test_native_api_rejects_bad_bounds_and_pointers_without_writing():
    encode, decode = g711_native._functions()
    assert encode._flags_ & ctypes._FUNCFLAG_PYTHONAPI
    assert decode._flags_ & ctypes._FUNCFLAG_PYTHONAPI
    pcm = (ctypes.c_int16 * 1)(123)
    octet = (ctypes.c_uint8 * 1)(42)
    p, o = ctypes.addressof(pcm), ctypes.addressof(octet)
    for law in (0, 1):
        assert encode(p, 1, o, 0, law) == 0
        assert decode(o, 1, p, 0, law) == 0
        assert encode(None, 1, o, 1, law) == 0
        assert decode(o, 1, None, 1, law) == 0
    assert encode(p, 1, o, 1, 2) == 0
    assert decode(o, 1, p, 1, 2) == 0
    assert pcm[0] == 123 and octet[0] == 42


@pytest.mark.parametrize('encode', [linear_to_ulaw, linear_to_alaw])
def test_packet_path_consumes_exactly_one_packet_and_uses_bulk_codec(encode, monkeypatch):
    session = object.__new__(SipSession)
    session._encode = encode
    samples = [i * 103 - 15000 for i in range(170)]
    session._tx_audio = deque(samples)
    calls = []
    original = g711_native.encode_pcm16
    def tracked(values, law):
        calls.append((len(values), law))
        return original(values, law)
    monkeypatch.setattr(g711_native, 'encode_pcm16', tracked)
    assert session._encode_rtp_audio() == bytes(map(encode, samples[:160]))
    assert list(session._tx_audio) == samples[160:]
    assert calls == [(160, 0 if encode is linear_to_ulaw else 1)]


def test_failed_native_encoding_does_not_consume_the_packet(monkeypatch):
    session = object.__new__(SipSession)
    session._encode = linear_to_ulaw
    session._tx_audio = deque(range(160))
    monkeypatch.setattr(g711_native, '_functions', lambda: (lambda *args: 0, lambda *args: 0))
    with pytest.raises(RuntimeError, match='encoding failed'):
        session._encode_rtp_audio()
    assert list(session._tx_audio) == list(range(160))


@pytest.mark.parametrize('codewords', [False, True])
@pytest.mark.parametrize('encode', [linear_to_ulaw, linear_to_alaw])
def test_complete_rtp_packets_and_transmit_accounting_match_scalar_path(codewords, encode, monkeypatch):
    monkeypatch.setattr('courier_emu.sip.time.monotonic', lambda: 10.06)
    results = []
    for enabled in ('0', '1'):
        monkeypatch.setenv('COURIER_NATIVE_G711', enabled)
        s = object.__new__(SipSession)
        s.state = 'connected'
        s._encode = encode
        s.codewords = codewords
        s._tx_audio = deque((k * 7919) % 65536 - 32768 for k in range(480))
        s._tx_codewords = deque(k % 256 for k in range(480))
        s._rtp_clock_thread = None
        s.remote_rtp = ('127.0.0.1', 5000)
        s.payload_type = 0 if encode is linear_to_ulaw else 8
        s._rtp_sequence = s._rtp_timestamp = 0
        s._rtp_ssrc = 1
        s._next_rtp_at = 10.0
        s.rtp_packets_sent = s.rtp_octets_sent = 0
        packets = []
        s.rtp_socket = SimpleNamespace(sendto=lambda packet, peer: packets.append(packet))
        s._flush_rtp_locked(10.06)
        source = s._tx_codewords if codewords else s._tx_audio
        assert not source
        assert s.rtp_packets_sent == 3 and s.rtp_octets_sent == 480
        results.append((packets, s._rtp_sequence, s._rtp_timestamp,
                        s._next_rtp_at, s._rtp_tx_stats.status()))
    assert results[0] == results[1]


def test_custom_encoder_keeps_original_path(monkeypatch):
    session = object.__new__(SipSession)
    session._encode = lambda value: value
    session._tx_audio = deque(range(160))
    monkeypatch.setattr(g711_native, 'available', lambda: pytest.fail('custom codec must bypass bulk path'))
    assert session._encode_rtp_audio() == bytes(range(160))
    assert not session._tx_audio


@pytest.mark.parametrize('sample', [40000, -40000, 1.5, True])
def test_packet_path_preserves_scalar_clipping_and_conversion(sample):
    session = object.__new__(SipSession)
    session._encode = linear_to_alaw
    session._tx_audio = deque([sample] * 160)
    assert session._encode_rtp_audio() == bytes([linear_to_alaw(sample)]) * 160


@pytest.mark.parametrize('codewords', [False, True])
def test_receive_custom_codec_and_opaque_codewords_bypass_bulk_path(codewords, monkeypatch):
    s = object.__new__(SipSession)
    s.state = 'connected'
    s.codewords = codewords
    s._decode = lambda value: value
    s._rx_audio = deque()
    s._rx_codewords = deque()
    s._rtp_playout = SimpleNamespace(drain=lambda now: b'\x00\x80\xff')
    def empty_socket(size):
        raise BlockingIOError
    s.rtp_socket = SimpleNamespace(recvfrom=empty_socket)
    monkeypatch.setattr(g711_native, 'decode_octets', lambda *args: pytest.fail('must bypass bulk codec'))
    s._receive_rtp_locked()
    assert list(s._rx_codewords if codewords else s._rx_audio) == [0, 128, 255]


@pytest.mark.parametrize('decode', [ulaw_to_linear, alaw_to_linear])
def test_receive_path_uses_bulk_codec_after_existing_capacity_guard(decode, monkeypatch):
    session = object.__new__(SipSession)
    session.state = 'connected'
    session.codewords = False
    session._decode = decode
    session._rx_audio = deque()
    octets = bytes(range(160))
    session._rtp_playout = SimpleNamespace(drain=lambda now: octets)
    def empty_socket(size):
        raise BlockingIOError
    session.rtp_socket = SimpleNamespace(recvfrom=empty_socket)
    calls = []
    original = g711_native.decode_octets
    def tracked(values, law):
        calls.append(law)
        return original(values, law)
    monkeypatch.setattr(g711_native, 'decode_octets', tracked)
    session._receive_rtp_locked()
    assert list(session._rx_audio) == list(map(decode, octets))
    assert calls == [0 if decode is ulaw_to_linear else 1]
    session._rtp_receive_capacity = 1
    calls.clear()
    with pytest.raises(RuntimeError, match='receive backlog'):
        session._receive_rtp_locked()
    assert calls == []
