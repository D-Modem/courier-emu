import pytest

from tools.analog_disconnect_diagnostics import AnalogDisconnectDiagnostics


def test_normal_queries_are_guarded_and_retain_all_responses():
    d = AnalogDisconnectDiagnostics(100.)
    assert d.poll(100.9) == b''
    assert d.poll(101.) == b'ATI6\r'
    report = b'\r\nDisconnect Reason is Retrain Failure\r\nOK\r\n'
    for b in report:
        d.feed(bytes([b]))
    assert d.poll(102.) == b''
    assert d.poll(103., dte_idle=False) == b''
    assert d.poll(103.1) == b'ATI11\r'
    d.feed(b'\r\nPhysical diagnostics\r\nOK\r\n')
    assert d.poll(104.) == b''
    assert d.poll(105.) == b'ATI4\r'
    d.feed(b'\r\nSettings\r\nOK\r\n')
    assert d.poll(106.) == b''
    assert d.done and d.error is None
    assert 'Retrain Failure' in d.status()['text']
    assert [r['command'] for r in d.sent] == ['ATI6', 'ATI11', 'ATI4']
    assert d.poll(1000.) == b''


@pytest.mark.parametrize('response', [b'\r\nERROR\r\n', b'\r\nNO CARRIER\r\n'])
def test_rejected_query_is_not_retried(response):
    d = AnalogDisconnectDiagnostics(0.)
    assert d.poll(1.) == b'ATI6\r'
    d.feed(response)
    assert d.poll(2.) == b''
    assert d.done and d.error == 'diagnostic command rejected'
    assert len(d.sent) == 1


def test_idle_and_response_timeouts_are_bounded():
    d = AnalogDisconnectDiagnostics(0.)
    assert d.poll(11., dte_idle=False) == b''
    assert d.done and d.error == 'DTE did not drain before query'
    d = AnalogDisconnectDiagnostics(0.)
    assert d.poll(1.) == b'ATI6\r'
    assert d.poll(11.) == b''
    assert d.done and d.error == 'timeout waiting for ATI6'


def test_online_escape_requires_guards_and_ack_before_information_query():
    with pytest.raises(ValueError):
        AnalogDisconnectDiagnostics(0., guard_seconds=.5, escape_online=True)
    d = AnalogDisconnectDiagnostics(0., escape_online=True)
    assert d.poll(.9) == b''
    assert d.poll(1.) == b'+++'
    d.feed(b'\r\nOK\r\n')
    assert d.poll(2.) == b''
    assert d.poll(3.) == b'ATI6\r'
    d.feed(b'\r\nDiagnostics\r\nOK\r\n')
    assert d.poll(4.) == b''
    assert d.poll(5.) == b'ATI11\r'


def test_capture_is_bounded_and_commands_cannot_change_settings():
    d = AnalogDisconnectDiagnostics(0., max_bytes=4)
    d.feed(b'1234')
    d.feed(b'5')
    assert d.done and d.text == b'1234'
    for commands in ((), ('ATH',), ('ATI6\rATH',)):
        with pytest.raises(ValueError):
            AnalogDisconnectDiagnostics(0., commands=commands)
