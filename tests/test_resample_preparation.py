"""Preflight prepares caches, never stream history or a different waveform."""
import math

import pytest

from courier_emu import resample as rs


def training_sequence():
    tx, rx = rs.BandLimitedResampler(), rs.BandLimitedResampler()
    time = 0.0
    output = []
    for rate, count in ((7200., 1440), (7200., 43),
                        (8641.23446206601, 1), (9600., 151), (9600., 193)):
        samples = [round(9000 * math.sin(2 * math.pi * 1700 * (time + i / rate)))
                   for i in range(count)]
        hardware = tx.convert(samples, rate, 10286.)
        output.append((hardware, rx.convert(hardware, 10286., rate)))
        time += count / rate
    return output


def test_preparation_preserves_samples_and_avoids_live_table_or_library_work(monkeypatch):
    monkeypatch.setattr(rs, '_KERNELS', {})
    monkeypatch.setattr(rs, '_FLAT_KERNELS', {})
    reference = training_sequence()
    # Simulate fresh caches again; retain exactly the same kernel generator.
    monkeypatch.setattr(rs, '_KERNELS', {})
    monkeypatch.setattr(rs, '_FLAT_KERNELS', {})
    untouched = rs.BandLimitedResampler()
    for rate in (7200., 8641.23446206601, 9600.):
        assert not rs.resampling_prepared(10286., rate)
        rs.prepare_resampling(rate, 10286., retuned=True)
        rs.prepare_resampling(10286., rate)
        assert rs.resampling_prepared(rate, 10286., retuned=True)
        assert rs.resampling_prepared(10286., rate)
    assert untouched.input_rate == untouched.output_rate == untouched.converted == 0
    assert untouched._timed_samples is None and untouched._position == 0

    def forbidden(*args, **kwargs):
        pytest.fail('lazy filter/library preparation during live retune')

    monkeypatch.setattr(rs, '_kernel', forbidden)
    monkeypatch.setattr('courier_emu.dsp.load_library', forbidden)
    assert training_sequence() == reference


@pytest.mark.parametrize('input_rate,output_rate', [
    (0, 8000), (-1, 8000), (8000, 0), (math.nan, 8000), (8000, math.inf)])
def test_invalid_preparation_rates(input_rate, output_rate):
    assert not rs.resampling_prepared(input_rate, output_rate)
    with pytest.raises(ValueError):
        rs.prepare_resampling(input_rate, output_rate)


def test_native_tables_are_prepared_when_available():
    rs.prepare_resampling(7200., 10286., retuned=True)
    assert rs.resampling_prepared(7200., 10286., retuned=True)
    if rs._NATIVE:
        assert rs._TIMED_LIBRARY is not None
        assert 0.49 in rs._FLAT_KERNELS
