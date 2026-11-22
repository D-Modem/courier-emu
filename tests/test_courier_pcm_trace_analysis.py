import pytest

from tools.analyze_courier_pcm_trace import repeating_period, signed16, summarize


def record(value, sample=0xff00, width=8, mode=0x843, kind='pcm-raw'):
    return {'kind': kind, 'dp': 6, 'ram': {
        '006f': mode, '0320': value, '0322': width,
        '0300': sample, '0338': sample,
    }}


def test_observed_stuck_inverse_mapper_pattern():
    # Observed live pre-descrambler chunks, not a modem success fixture.
    rows = [record(v) for v in [0, 0x7e, 3] * 10]
    result = summarize(rows)
    assert result['records'] == 30
    assert result['chunk_value_counts'] == {0: 10, 3: 10, 126: 10}
    assert result['repeating_chunks'] == [0, 126, 3]
    assert result['samples']['0300']['mean'] == -256
    assert result['samples']['0300']['standard_deviation'] == 0
    assert result['capture_completeness'].startswith('not established')


def test_excludes_other_modes_and_rate_selection_records():
    rows = [record(1), record(2, mode=0x43), record(3, kind='rate-selection')]
    rows.append({**record(4), 'dp': 7})
    assert summarize(rows)['chunk_value_counts'] == {1: 1}


def test_variable_width_chunks_have_no_fixed_value_period():
    result = summarize([record(1, width=6), record(1, width=8)] * 2)
    assert result['repeating_chunks'] is None
    assert result['chunk_width_counts'] == {6: 2, 8: 2}


def test_invalid_width_is_not_silently_decoded():
    with pytest.raises(ValueError, match='chunk width'):
        summarize([record(1, width=0)])


def test_empty_trace_and_partial_period():
    assert summarize([])['records'] == 0
    assert repeating_period([]) is None
    assert repeating_period([1, 2, 1, 2, 1]) == [1, 2]
    assert repeating_period([1, 2, 3]) is None
    assert repeating_period([1, 2, 1, 3]) is None


def test_signed_adc_word():
    assert signed16(0x8000) == -32768
    assert signed16(0xffff) == -1
    assert signed16(0x7fff) == 32767
