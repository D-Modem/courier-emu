"""Harness safety checks without opening USB, SIP or a physical line."""
import json

import pytest

from tools.apple_traffic import verify_saved
from tools.capture_apple_sip import modem_status, remote_capture_filter
from tools.probe_apple_sip_traffic import command_plan, online_diagnostics, receiver_diagnostics, transport_plan
from test_apple_binary_traffic import saved


def test_remote_filter_can_cover_both_pbx_legs_without_broadening_local_capture():
    assert remote_capture_filter('10.0.0.1') == 'udp and host 10.0.0.1'
    assert remote_capture_filter('10.0.0.1', ['10.0.0.2', '10.0.0.2']) == 'udp and (host 10.0.0.1 or host 10.0.0.2)'
    with pytest.raises(ValueError):
        remote_capture_filter('10.0.0.1', ['10.0.0.2 or host evil'])


@pytest.mark.parametrize('frames,cadence,budget', [(0,.02,16000), (128,.005,64000), (256,.02,16000)])
def test_transport_backstop_does_not_shrink_in_low_latency_mode(frames, cadence, budget):
    plan = transport_plan({'APPLE_MODEM_BUFFER_FRAMES': str(frames)})
    assert plan['codec_service_seconds'] == cadence
    assert plan['max_line_frames'] == budget
    assert plan['backstop_seconds'] == cadence * budget == 320
    assert not plan['async_status_requested']
    assert plan['post_dial_tx_gain'] is None
    assert transport_plan({'APPLE_POST_DIAL_GAIN': '.5'})['post_dial_tx_gain'] == .5
    assert transport_plan({'APPLE_LINE_ASYNC_STATUS': '1'})['async_status_requested']


@pytest.mark.parametrize('env', [{'APPLE_MODEM_BUFFER_FRAMES': 'nan'},
                                 {'APPLE_MODEM_BUFFER_FRAMES': '3'},
                                 {'APPLE_MODEM_BUFFER_FRAMES': '4097'},
                                 {'APPLE_LINE_ASYNC_STATUS': 'maybe'},
                                 {'APPLE_POST_DIAL_GAIN': 'nan'},
                                 {'APPLE_POST_DIAL_GAIN': 'inf'},
                                 {'APPLE_POST_DIAL_GAIN': '1.1'}])
def test_invalid_transport_settings_fail_before_dialing(env):
    with pytest.raises(ValueError): transport_plan(env)


def test_at_plan_preserves_known_modulation_dial_and_stays_within_command_buffer():
    from tools.apple_sip_profiles import settings
    plan = command_plan()
    assert plan['caller_dial'] == 'ATX1S27=1' + settings('v32-lapm') + 'S7=45DT2903'
    assert plan['caller_setup'] == 'ATS2=43&I0'
    assert max(map(len, [*plan['receiver'], plan['caller_setup'], plan['caller_dial']])) < 64


def test_owner_check_does_not_open_usb_during_sibling_experiment(monkeypatch):
    calls = []
    def run(command):
        calls.append(command)
        return dict(returncode=0, stdout='123 ./apple_usb_modem_coupler\n456 /usr/bin/python\n', stderr='')
    monkeypatch.setattr('tools.capture_apple_sip.run', run)
    result = modem_status('/test/apple_line')
    assert result['returncode'] and result['owners'] == ['123 ./apple_usb_modem_coupler']
    assert calls == [['ps', '-axo', 'pid=,comm=']]


def test_owner_check_failure_does_not_open_usb(monkeypatch):
    monkeypatch.setattr('tools.capture_apple_sip.run', lambda command:
                        dict(returncode=1, stdout='', stderr='ps failed'))
    assert modem_status('/test/apple_line')['returncode']


def test_event_log_cannot_hide_a_stall_with_forged_window_metrics(tmp_path):
    metadata = saved(tmp_path)
    events = [json.loads(line) for line in (tmp_path / 'events.jsonl').read_text().splitlines()]
    # Keep counts and source bytes intact but move the final receipt into drain.
    events[-1]['time'] = 162
    (tmp_path / 'events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
    with pytest.raises(AssertionError, match='statistics disagree'):
        verify_saved(tmp_path, metadata=metadata)


def test_event_log_rejects_more_than_one_outstanding_record(tmp_path):
    metadata = saved(tmp_path)
    events = [json.loads(line) for line in (tmp_path / 'events.jsonl').read_text().splitlines()]
    # Send record two before the remote actually completed record one.
    events.insert(2, dict(event='sent', side='apple', time=104.95, records=2))
    (tmp_path / 'events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
    with pytest.raises(AssertionError, match='outstanding-record'):
        verify_saved(tmp_path, metadata=metadata)


@pytest.mark.parametrize('escape_ok', [False, True])
def test_online_diagnostic_requires_real_escape_ok(tmp_path, monkeypatch, escape_ok):
    clock = [0]
    writes = []
    reads = [b'\r\nOK\r\n', b'link counters\r\nOK\r\n'] if escape_ok else [b'not a result']
    monkeypatch.setattr('tools.probe_apple_sip_traffic.time.monotonic', lambda: clock[0])
    monkeypatch.setattr('tools.probe_apple_sip_traffic.time.sleep', lambda dt: clock.__setitem__(0, clock[0]+1))
    def read(*args):
        if reads: return reads.pop(0)
        raise BlockingIOError()
    monkeypatch.setattr('tools.probe_apple_sip_traffic.os.read', read)
    monkeypatch.setattr('tools.probe_apple_sip_traffic.os.write', lambda fd, data: writes.append(data) or len(data))
    result = online_diagnostics(1, 2, tmp_path / 'online.bin')
    assert writes == ([b'+++', b'ATI6\r'] if escape_ok else [b'+++'])
    assert result['escaped'] == escape_ok
    if escape_ok: assert result['complete']


@pytest.mark.parametrize('carrier_lost', [False, True])
def test_diagnostic_at_is_never_sent_into_a_live_data_stream(tmp_path, monkeypatch, carrier_lost):
    from types import SimpleNamespace
    clock = [0]
    reads = [b'\r\nNO CARRIER\r\n' if carrier_lost else b'still online data', b'\r\nOK\r\n']
    writes = []
    monkeypatch.setattr('tools.probe_apple_sip_traffic.time.monotonic', lambda: clock[0])
    monkeypatch.setattr('tools.probe_apple_sip_traffic.time.sleep', lambda dt: clock.__setitem__(0, clock[0]+1))
    def read(*args):
        if reads: return reads.pop(0)
        raise BlockingIOError()
    monkeypatch.setattr('tools.probe_apple_sip_traffic.os.read', read)
    monkeypatch.setattr('tools.probe_apple_sip_traffic.os.write', lambda fd, data: writes.append(data) or len(data))
    process = SimpleNamespace(poll=lambda: None, stdin=SimpleNamespace(fileno=lambda: 1),
                              stdout=SimpleNamespace(fileno=lambda: 2))
    result = receiver_diagnostics(process, tmp_path)
    assert writes == ([b'ATI6\r'] if carrier_lost else [])
    assert result['queried'] == carrier_lost
