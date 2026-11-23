from copy import deepcopy

import pytest

from tools.analyze_tx_timing import aggregate, summarize


def row(t, samples, cpu):
    return dict(monotonic_seconds=t, online_mode=True, sip_state='connected',
                epoch=0, codec=dict(sample_rate=9600, frame_period=4200),
                thread_cpu_seconds=cpu, process_cpu_seconds=cpu + 1,
                cpu_instructions=int(cpu * 1000),
                pacing=dict(paced_seconds=0.1), rtp_tx_queue_samples=480,
                rtp_tx=dict(produced_samples=samples, sent_samples=samples,
                            sample_clock_late_ms=0))


def test_cpu_bound_production_deficit_is_separate_from_send_deficit():
    a, b = row(10, 8000, 1), row(11, 14400, 2)
    b['rtp_tx']['sent_samples'] = 16000
    b['rtp_tx_queue_samples'] = 0
    result = summarize([a, b])['intervals'][0]
    assert result['production_deficit_ms'] == pytest.approx(200)
    assert result['send_deficit_ms'] == 0
    assert result['thread_cpu_fraction'] == 1
    assert result['queue_end_samples'] == 0


def test_non_cpu_time_is_not_labeled_as_scheduler_or_gil_stall():
    a, b = row(10, 8000, 1), row(11, 16000, 1.2)
    b['pacing']['paced_seconds'] = .7
    result = summarize([a, b])['intervals'][0]
    assert result['non_thread_cpu_seconds'] == pytest.approx(.8)
    assert result['requested_pacing_sleep_seconds'] == pytest.approx(.6)


@pytest.mark.parametrize('change', ['offline', 'sip', 'epoch', 'period', 'rate'])
def test_boundaries_are_not_turned_into_timing_intervals(change):
    a, b = row(10, 8000, 1), row(11, 16000, 2)
    if change == 'offline':
        b['online_mode'] = False
    elif change == 'sip':
        b['sip_state'] = 'closed'
    elif change == 'epoch':
        b['epoch'] = 1
    elif change == 'period':
        b['codec']['frame_period'] = 4300
    else:
        b['codec']['sample_rate'] = 7200
    assert summarize([a, b]) == dict(intervals=[], skipped_boundary_intervals=1)


def test_old_snapshots_without_sip_phase_are_skipped_not_assumed_connected():
    a, b = row(10, 8000, 1), row(11, 16000, 2)
    del a['sip_state']
    assert summarize([a, b])['intervals'] == []


@pytest.mark.parametrize('window', [(10, 10), (11, 10), (float('-inf'), 12),
                                  (10, float('nan'))])
def test_legacy_window_requires_finite_increasing_bounds(window):
    with pytest.raises(ValueError, match='finite increasing'):
        summarize([], verified_connected_window=window)


def test_legacy_phase_is_explicit_bounded_and_does_not_override_closed_sip():
    rows = [row(t, t * 8000, t) for t in (9, 10, 11, 12)]
    for r in rows:
        del r['sip_state']
    before = deepcopy(rows)
    result = summarize(rows, verified_connected_window=(10, 11))
    assert len(result['intervals']) == 1
    assert result['skipped_boundary_intervals'] == 2
    assert result['intervals'][0]['sip_phase_source'] == 'externally_verified_window'
    assert rows == before
    rows[2]['sip_state'] = 'closed'
    assert summarize(rows, verified_connected_window=(10, 11))['intervals'] == []
    del rows[2]['sip_state']
    rows[2]['online_mode'] = False
    assert summarize(rows, verified_connected_window=(10, 11))['intervals'] == []


def test_aggregate_cpu_fraction_is_weighted_and_empty_is_unknown():
    rows = [row(10, 8000, 1), row(11, 16000, 2), row(14, 40000, 3)]
    result = aggregate(summarize(rows)['intervals'])
    assert result['analyzed_wall_seconds'] == 4
    assert result['thread_cpu_fraction'] == .5
    assert result['externally_verified_intervals'] == 0
    assert aggregate([])['thread_cpu_fraction'] is None


def test_cli_rejects_unbounded_legacy_attestation(tmp_path):
    import subprocess
    import sys
    source = tmp_path / 'audit.jsonl'
    source.write_text('')
    result = subprocess.run([sys.executable, '-m', 'tools.analyze_tx_timing', str(source),
                             '--verified-legacy-connected-window'], capture_output=True, text=True)
    assert result.returncode == 2
    assert 'requires finite increasing' in result.stderr


def test_cli_legacy_window_emits_provenance_aggregate_and_ranked_intervals(tmp_path):
    import json
    import subprocess
    import sys
    rows = [row(t, samples, cpu) for t, samples, cpu in
            ((10, 8000, 1), (11, 14400, 2), (12, 24000, 2.5))]
    for r in rows:
        del r['sip_state']
    source = tmp_path / 'audit.jsonl'
    source.write_text('\n'.join(json.dumps(r) for r in rows))
    result = subprocess.run([sys.executable, '-m', 'tools.analyze_tx_timing', str(source),
                             '--start', '10', '--end', '12',
                             '--verified-legacy-connected-window'],
                            capture_output=True, text=True, check=True)
    report = json.loads(result.stdout)
    assert report['aggregate']['externally_verified_intervals'] == 2
    assert report['aggregate']['thread_cpu_fraction'] == .75
    assert report['largest_production_deficits'][0]['production_deficit_ms'] == pytest.approx(200)
    assert report['largest_production_deficits'][1]['production_deficit_ms'] == pytest.approx(-200)


def test_rewind_and_duplicate_times_are_rejected():
    a = row(10, 8000, 1)
    with pytest.raises(ValueError, match='times'):
        summarize([a, deepcopy(a)])
    with pytest.raises(ValueError, match='rewind'):
        summarize([a, row(11, 7000, 2)])


def test_analysis_does_not_mutate_snapshots_and_retains_catchup():
    rows = [row(10, 8000, 1), row(11, 17600, 1.5)]
    before = deepcopy(rows)
    assert summarize(rows)['intervals'][0]['production_deficit_ms'] == pytest.approx(-200)
    assert rows == before
