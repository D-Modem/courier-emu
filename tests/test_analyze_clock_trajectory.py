import pytest

from tools.analyze_clock_trajectory import summarize


def sample(cpu, *, epoch=1, period=4200):
    return dict(cpu_instructions=cpu, epoch=epoch, codec_period=period,
                dsp_cycles=12 * cpu, dsp_instructions=10 * cpu,
                dsp_xf_edges=4 * cpu, codec_primary_frames=12 * cpu,
                line_input_queued=10 * cpu + 32, line_input_consumed=10 * cpu,
                line_input_pending=32, codec_tx_samples=12 * cpu,
                frame_irq_entries=3 * cpu, frame_eoi_observations=3 * cpu)


def analyze(rows):
    return summarize(rows, cpu_hz=100, dsp_hz=1200, dsp_per_cpu=12)


def test_summarize_distinguishes_stable_clock_ratio_from_missing_frame_irqs():
    segment, = analyze([sample(100), sample(150), sample(200)])
    assert segment['cpu_seconds'] == segment['dsp_seconds'] == 1
    assert segment['dsp_cycles_per_cpu_instruction'] == 12
    assert segment['relative_cycle_debt'] == dict(first=0, last=0, min=0, max=0)
    assert segment['xf_edges_per_dsp_second'] == 400
    assert segment['frame_irqs_per_dsp_second'] == 300
    assert segment['irq_minus_xf_delta'] == -100
    assert segment['raw_line_pending'] == dict(first=32, last=32, min=32, max=32)


def test_dsp_epochs_and_codec_retunes_are_not_interpolated():
    rows = [sample(10), sample(20), sample(30, epoch=2), sample(40, epoch=2),
            sample(50, epoch=2, period=5600), sample(60, epoch=2, period=5600)]
    segments = analyze(rows)
    assert [(s['epoch'], s['codec_period']) for s in segments] == [(1, 4200), (2, 4200), (2, 5600)]
    assert [s['cpu_end'] - s['cpu_start'] for s in segments] == [10, 10, 10]


@pytest.mark.parametrize('corrupt,match', [
    ({'cpu_instructions': 9}, 'strictly increase'),
    ({'dsp_cycles': 0}, 'rewind'),
    ({'line_input_pending': 31}, 'PCM accounting'),
])
def test_inconsistent_clock_capture_fails_closed(corrupt, match):
    a, b = sample(10), sample(20)
    b.update(corrupt)
    with pytest.raises(ValueError, match=match):
        analyze([a, b])


def test_relative_cycle_debt_reports_step_and_drift_instead_of_rounding_them_away():
    rows = [sample(100), sample(150), sample(200)]
    rows[1]['dsp_cycles'] += 5
    rows[2]['dsp_cycles'] += 10
    segment, = analyze(rows)
    assert segment['relative_cycle_debt'] == dict(first=0, last=10, min=0, max=10)
    assert segment['dsp_cycles_per_cpu_instruction'] == 12.1
