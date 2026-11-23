import struct
from types import SimpleNamespace

import pytest

from courier_emu import resample


def packed(table):
    return b''.join(struct.pack(f'{len(row)}d', *row) for row in table)


def test_native_kaiser_windows_match_every_python_coefficient(monkeypatch):
    monkeypatch.setattr(resample, '_WINDOWS', None)
    monkeypatch.setattr(resample, '_NATIVE', None)
    monkeypatch.setenv('COURIER_NATIVE_RESAMPLE', '0')
    reference = resample._windows()
    monkeypatch.setattr(resample, '_WINDOWS', None)
    monkeypatch.setattr(resample, '_NATIVE', None)
    monkeypatch.setenv('COURIER_NATIVE_RESAMPLE', '1')
    assert resample._native_retuned(), 'native resampler must be available for parity test'
    native = resample._native_windows()
    assert native is not None
    assert len(native) == resample.PHASES
    assert all(len(row) == resample.TAPS for row in native)
    assert packed(native) == packed(reference)
    assert packed(resample._windows()) == packed(reference)


def test_missing_window_symbol_in_older_library_falls_back(monkeypatch):
    from courier_emu import dsp
    monkeypatch.setattr(dsp, 'loaded_library', lambda: SimpleNamespace())
    assert resample._native_windows() is None
    monkeypatch.setattr(resample, '_WINDOWS', None)
    reference = resample._windows()
    assert len(reference) == resample.PHASES
    assert reference[0][0] > 0


def test_native_window_api_rejects_short_buffers_and_invalid_norm():
    import ctypes
    from courier_emu.dsp import load_library
    function = load_library().courier_resample_windows
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double]
    function.restype = ctypes.c_size_t
    values = (ctypes.c_double * 2)(123.0, 456.0)
    address = ctypes.addressof(values)
    count = resample.PHASES * resample.TAPS
    assert function(address, 2, resample._NORM) == 0
    assert function(None, count, resample._NORM) == 0
    for norm in (0.0, -1.0, float('nan'), float('inf')):
        assert function(address, count, norm) == 0
    assert list(values) == [123.0, 456.0]


def test_windows_do_not_trigger_native_loading_or_building(monkeypatch):
    from courier_emu import dsp
    monkeypatch.setattr(dsp, '_LIBRARY_HANDLE', None)
    monkeypatch.setattr(dsp, 'load_library', lambda: pytest.fail('must not load a core'))
    monkeypatch.setattr(resample, '_native_retuned', lambda: pytest.fail('must not probe native conversion'))
    assert resample._native_windows() is None


def test_disabled_native_resampling_does_not_inspect_a_loaded_core(monkeypatch):
    from courier_emu import dsp
    monkeypatch.setenv('COURIER_NATIVE_RESAMPLE', '0')
    monkeypatch.setattr(dsp, 'loaded_library', lambda: pytest.fail('native path disabled'))
    assert resample._native_windows() is None


def test_windows_cache_does_not_repeat_native_work(monkeypatch):
    table = [(1.0,)]
    calls = []
    monkeypatch.setattr(resample, '_WINDOWS', None)
    monkeypatch.setattr(resample, '_native_windows', lambda: calls.append(1) or table)
    assert resample._windows() is table
    assert resample._windows() is table
    assert calls == [1]


def test_native_rejection_is_not_silently_replaced_with_a_table(monkeypatch):
    from courier_emu import dsp
    class Function:
        def __call__(self, *args):
            return 0
    monkeypatch.setattr(dsp, 'loaded_library', lambda: SimpleNamespace(courier_resample_windows=Function()))
    with pytest.raises(RuntimeError, match='window construction failed'):
        resample._native_windows()
