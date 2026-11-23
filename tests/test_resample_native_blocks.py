from array import array
import math
import random
import struct
from types import SimpleNamespace

import pytest

from courier_emu import dsp, resample, resample_native as native
from courier_emu.sip import PolyphaseResampler


@pytest.fixture(autouse=True, scope='module')
def library():
    dsp.load_library()
    assert native.fixed_available() and native.polyphase_available()


def doubles(values):
    return struct.pack(f'{len(values)}d', *values)


def fixed_state(r):
    return (doubles(r._history), doubles(r._recent_input), doubles([r._position]),
            r.converted, r.input_rate, r.output_rate)


def poly_state(r):
    return doubles(r._buffer), r._origin, r._output


@pytest.mark.parametrize('rates', [(48000, 8000), (8000, 48000), (9600, 8000),
                                   (8000, 9600), (44100, 8000), (8000, 8000),
                                   (8000.31, 8000), (7999.9, 8000)])
def test_fixed_stream_and_state_exact(rates, monkeypatch):
    rng = random.Random(39)
    chunks = [[rng.randrange(-40000, 40000) for _ in range(n)]
              for n in (0, 1, 19, 160, 0, 997, 3, 401, 160)]
    runs = []
    for enabled in ('0', '1'):
        monkeypatch.setenv('COURIER_NATIVE_FIXED_RESAMPLE', enabled)
        r = resample.BandLimitedResampler()
        runs.append([(r.convert(chunk, *rates), fixed_state(r)) for chunk in chunks])
    assert runs[0] == runs[1]


@pytest.mark.parametrize('position', [0., .5 / 1024, 1023.5 / 1024,
                                      math.nextafter(1., 0.), .375, 7.9999])
def test_fixed_phase_round_up_and_boundaries(position, monkeypatch):
    runs = []
    for enabled in ('0', '1'):
        monkeypatch.setenv('COURIER_NATIVE_FIXED_RESAMPLE', enabled)
        r = resample.BandLimitedResampler()
        r.convert([1], 9600, 8000)
        r._position = position
        runs.append((r.convert(list(range(160)), 9600, 8000), fixed_state(r)))
    assert runs[0] == runs[1]


@pytest.mark.parametrize('rates', [(7200, 8000), (8000, 7200), (48000, 8000),
                                   (8000, 48000), (44100, 8000), (8000, 8000),
                                   (8192, 8000), (8001, 8000)])
def test_polyphase_stream_flush_and_state_exact(rates, monkeypatch):
    rng = random.Random(17)
    chunks = [[rng.randrange(-40000, 40000) for _ in range(n)]
              for n in (0, 1, 19, 160, 0, 997, 3, 401, 160)]
    runs = []
    for enabled in ('0', '1'):
        monkeypatch.setenv('COURIER_NATIVE_POLYPHASE', enabled)
        r = PolyphaseResampler(*rates)
        result = [(r.convert(chunk), poly_state(r)) for chunk in chunks]
        result.append((r.flush(), poly_state(r)))
        runs.append(result)
    assert runs[0] == runs[1]


@pytest.mark.parametrize('mode', [0, 1])
def test_fixed_ties_even_saturation_and_nonfinite_decline(mode):
    weights = array('d', [0.]) * (1024 * 128)
    for p in range(1024):
        weights[p * 128] = 1.
    values = [-32768.5, -32767.5, -2.5, -1.5, -.5, .5, 1.5, 2.5,
              32766.5, 32767.5, -1e100, 1e100] + [0.] * 127
    result, position = native.fixed(values, weights, 1., 0., mode)
    assert result == [max(-32768, min(32767, round(v))) for v in values[:-127]]
    assert position == len(result)
    values[2] = float('nan')
    assert native.fixed(values, weights, 1., 0., mode) is None
    assert native.fixed(values, weights, 1., 2**60, mode) is None
    assert native.fixed([0.] * 512, weights, 1e-16, 100., mode) is None


def test_polyphase_ties_even_saturation_and_nonfinite_decline():
    values = [-32768.5, -32767.5, -2.5, -1.5, -.5, .5, 1.5, 2.5,
              32766.5, 32767.5, -1e100, 1e100]
    result, index = native.polyphase(values, array('d', [1.]), 1, 1, 1, 0, 0, 0)
    assert result == [max(-32768, min(32767, round(v))) for v in values]
    assert index == len(values)
    values[2] = float('inf')
    assert native.polyphase(values, array('d', [1.]), 1, 1, 1, 0, 0, 0) is None
    assert native.polyphase(values, array('d', [1.]), 1, 1, 1, 0, 0, 2**60) is None


@pytest.mark.parametrize('kind', ['fixed', 'polyphase'])
def test_scratch_chunk_boundary_does_not_discard_audio(kind, monkeypatch):
    rng = random.Random(13)
    samples = [rng.randrange(-32000, 32000) for _ in range(12000)]
    runs = []
    flag = 'COURIER_NATIVE_FIXED_RESAMPLE' if kind == 'fixed' else 'COURIER_NATIVE_POLYPHASE'
    for enabled in ('0', '1'):
        monkeypatch.setenv(flag, enabled)
        if kind == 'fixed':
            r = resample.BandLimitedResampler()
            result = r.convert(samples, 8000, 48000)
            state = fixed_state(r)
        else:
            r = PolyphaseResampler(8000, 48000)
            result = r.convert(samples)
            state = poly_state(r)
        assert len(result) > 65536
        runs.append((result, state))
    assert runs[0] == runs[1]


@pytest.mark.parametrize('kind', ['fixed', 'polyphase'])
def test_nonfinite_exception_preserves_partial_stream_state(kind, monkeypatch):
    runs = []
    flag = 'COURIER_NATIVE_FIXED_RESAMPLE' if kind == 'fixed' else 'COURIER_NATIVE_POLYPHASE'
    for enabled in ('0', '1'):
        monkeypatch.setenv(flag, enabled)
        samples = [1.] * 160
        samples[15] = float('nan')
        r = resample.BandLimitedResampler() if kind == 'fixed' else PolyphaseResampler(7200, 8000)
        with pytest.raises(ValueError) as error:
            if kind == 'fixed':
                r.convert(samples, 9600, 8000)
            else:
                r.convert(samples)
        runs.append((str(error.value), fixed_state(r) if kind == 'fixed' else poly_state(r)))
    assert runs[0] == runs[1]


def test_polyphase_coefficient_mutations_are_observed(monkeypatch):
    runs = []
    for enabled in ('0', '1'):
        monkeypatch.setenv('COURIER_NATIVE_POLYPHASE', enabled)
        calls = []
        class Tap(float):
            def __mul__(self, value):
                calls.append(1)
                return float(self) * value
        r = PolyphaseResampler(7200, 8000)
        results = [r.convert([123] * 160)]
        r._taps[0][0] += .125
        results.append(r.convert([321] * 160))
        # Integer/custom numeric taps retain their original Python semantics.
        r._taps[1][0] = Tap(1.)
        results.append(r.convert([100] * 160))
        assert calls
        runs.append((results, poly_state(r), len(calls)))
    assert runs[0] == runs[1]


def test_small_blocks_do_not_pay_native_marshalling(monkeypatch):
    monkeypatch.setattr(native, 'fixed', lambda *args: pytest.fail('tiny native FIR'))
    monkeypatch.setattr(native, 'polyphase', lambda *args: pytest.fail('tiny native polyphase'))
    fixed, poly = resample.BandLimitedResampler(), PolyphaseResampler(7200, 8000)
    assert fixed.convert([3] * 8, 48000, 8000) == [0, 0]
    assert poly.convert([3] * 8)


def test_custom_rate_arithmetic_is_not_bypassed(monkeypatch):
    runs = []
    calls = []
    class Step(float):
        def __radd__(self, other):
            calls.append(1)
            return other + float(self)
    class Rate(float):
        def __truediv__(self, other):
            return Step(float(self) / other)
    for enabled in ('0', '1'):
        calls.clear()
        monkeypatch.setenv('COURIER_NATIVE_FIXED_RESAMPLE', enabled)
        r = resample.BandLimitedResampler()
        result = r.convert([100] * 160, Rate(9600), 8000)
        assert len(calls) == len(result)
        runs.append((result, fixed_state(r), len(calls)))
    assert runs[0] == runs[1]


def test_import_time_custom_sumprod_is_not_bypassed(monkeypatch):
    from pathlib import Path
    from types import ModuleType
    calls = []
    reference = getattr(math, 'sumprod', resample._fallback_dot)
    def custom(a, b):
        calls.append(1)
        return reference(a, b)
    monkeypatch.setattr(math, 'sumprod', custom, raising=False)
    module = ModuleType('courier_emu._resample_custom_dot')
    module.__package__ = 'courier_emu'
    source = Path(resample.__file__)
    exec(compile(source.read_text(), str(source), 'exec'), module.__dict__)
    assert module._REFERENCE_DOT is None
    result = module.BandLimitedResampler().convert([100] * 160, 9600, 8000)
    assert len(calls) == len(result)


def test_custom_fixed_dot_is_not_bypassed(monkeypatch):
    calls = []
    monkeypatch.setattr(resample, '_dot', lambda a, b: calls.append(1) or 0.)
    r = resample.BandLimitedResampler()
    assert r.convert([100] * 160, 9600, 8000) == [0] * len(calls)
    assert calls


def test_sequential_products_are_not_fused_or_compensated():
    # Separate binary64 product/add gives 0; fused/compensated gives -1.
    a, b = float(2**27 + 1), float(2**27 - 1)
    weights = array('d', [0.]) * (1024 * 128)
    for p in range(1024):
        weights[p * 128:p * 128 + 2] = array('d', [1., a])
    values = [-float(2**54), b] + [0.] * 127
    assert native.fixed(values, weights, 1., 0., 0)[0][0] == 0
    assert native.fixed(values, weights, 1., 0., 1)[0][0] == -1
    assert native.polyphase([b, -float(2**54)], array('d', [1., a]),
                            1, 1, 2, 1, 0, 0) == ([0], 1)


def test_packet_kernels_keep_the_gil_and_invalid_tables_decline():
    import ctypes
    for kind in ('fixed', 'polyphase'):
        assert native._function(kind)._flags_ & ctypes._FUNCFLAG_PYTHONAPI
    assert native.fixed([0.] * 128, array('d', [1.]), 1., 0., 0) is None
    assert native.polyphase([0.], array('d', [1.]), 2, 1, 1, 0, 0, 0) is None


def test_missing_symbols_and_unloaded_library_do_not_load_core(monkeypatch):
    monkeypatch.setattr(dsp, 'load_library', lambda: pytest.fail('implicit library load'))
    for library in (None, SimpleNamespace()):
        monkeypatch.setattr(dsp, 'loaded_library', lambda: library)
        assert not native.fixed_available()
        assert not native.polyphase_available()
        assert native.fixed([], array('d'), 1., 0., 0) is None
        assert native.polyphase([], array('d'), 1, 1, 1, 0, 0, 0) is None
