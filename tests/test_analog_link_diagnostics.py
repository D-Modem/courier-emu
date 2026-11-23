import pytest

from tools.analog_link_diagnostics import AnalogLinkDiagnostics


def test_guard_and_complete_responses_are_required_before_each_command():
    session = AnalogLinkDiagnostics(100)
    assert session.poll(139, 'last payload') == b''
    assert session.poll(140) == b'+++'
    assert session.poll(141, '\r\nO') == b''
    assert session.poll(142, 'K\r\n') == b'ATI6\r'
    assert session.poll(143) == b''  # The earlier OK cannot acknowledge ATI6.
    assert session.poll(144, '\r\nBlers 123\r\nOK\r\n') == b'ATO\r'
    assert not session.done
    assert session.poll(145, '\r\nCONNECT 53333') == b''
    assert not session.done
    assert session.poll(146, '/ARQ/x2/LAPM\r\n') == b''
    assert session.done and session.stage == 'done'
    assert session.error is None
    assert [e['text'] for e in session.commands] == ['+++', 'ATI6\r', 'ATO\r']
    assert all(e['frame'] >= 140 for e in session.commands)
    assert 'Blers 123' in session.status()['text']
    assert session.poll(200, 'ignored') == b''
    assert 'ignored' not in session.text


@pytest.mark.parametrize('response', ['\r\nERROR\r\n', '\r\nNO CARRIER\r\n'])
def test_error_response_is_not_a_completed_diagnostic(response):
    session = AnalogLinkDiagnostics(0)
    session.poll(40)
    assert session.poll(41, response) == b''
    assert session.done and session.stage == 'failed'
    assert session.error
    assert len(session.commands) == 1


def test_missing_response_times_out_without_resending_escape_or_injecting_data():
    session = AnalogLinkDiagnostics(0, timeout_frames=5)
    assert session.poll(40) == b'+++'
    assert session.poll(44) == b''
    assert session.poll(45) == b''
    assert session.stage == 'failed' and 'escaping' in session.error
    assert len(session.commands) == 1


def test_response_buffer_and_guard_are_bounded():
    with pytest.raises(ValueError):
        AnalogLinkDiagnostics(0, guard_frames=9)
    session = AnalogLinkDiagnostics(0)
    assert session.poll(1, 'x' * 16385) == b''
    assert session.stage == 'failed' and session.error
    assert not session.commands
