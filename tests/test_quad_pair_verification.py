import pytest

from tools.probe_quad_pair import check_pair, verification_results


def reports():
    summary = {'imodem_connect': 'CONNECT 31200/ARQ/V34/LAPM',
               'quad_connect': 'CONNECT 33600/ARQ',
               'payload_checks': {'imodem_to_quad': True, 'quad_to_imodem': True}}
    imodem = {'error': None, 'mailbox': {'error': None, 'pcm': {'rx_empty_frames': 0}}}
    quad = {'error': None, 'endpoint': {'pcm_rx_underruns': 0}, 'peek': {'8311': '04'}}
    return summary, imodem, quad


def test_working_fallback_data_is_distinct_from_verified_x2():
    result = verification_results(*reports(), require_data=True, require_x2=True)
    assert result['connect_verified'] is True
    assert result['data_verified'] is True
    assert result['x2_verified'] is False
    assert 'does not identify x2' in result['verification_failure']


def test_x2_carrier_does_not_manufacture_verified_payloads():
    summary, imodem, quad = reports()
    summary['imodem_connect'] = 'CONNECT 64000/ARQ/x2/LAPM'
    summary['quad_connect'] = 'CONNECT 64000/ARQ/x2'
    summary['payload_checks']['imodem_to_quad'] = False
    result = verification_results(summary, imodem, quad, require_data=True, require_x2=True)
    assert result['connect_verified'] is True
    assert result['x2_verified'] is True
    assert result['data_verified'] is False
    assert 'bidirectional' in result['verification_failure']


def test_setup_must_be_acknowledged_even_if_carrier_strings_exist():
    summary, imodem, quad = reports()
    quad['initialization_completed_at'] = None
    with pytest.raises(RuntimeError, match='initialization did not complete'):
        check_pair(summary, imodem, quad, require_data=True)


def test_both_carriers_and_verified_data_pass():
    check_pair(*reports(), require_data=True)


@pytest.mark.parametrize('role', ['imodem', 'quad'])
def test_x2_check_rejects_v34_fallback_even_with_working_data(role):
    summary, imodem, quad = reports()
    summary['imodem_connect'] = 'CONNECT 64000/ARQ/x2/LAPM'
    summary['quad_connect'] = 'CONNECT 64000/ARQ/x2'
    summary[f'{role}_connect'] = 'CONNECT 31200/ARQ/V34/LAPM'
    with pytest.raises(RuntimeError, match=f'{role} CONNECT does not identify x2'):
        check_pair(summary, imodem, quad, require_data=True, require_x2=True)


@pytest.mark.parametrize('result', ['CONNECT 64000/ARQ', 'CONNECT 64000/DIGITAL',
                                   'CONNECT 64000/NOTX2', 'CONNECT 31200/ARQ/V34/LAPM'])
def test_rate_or_transparent_digital_carrier_does_not_prove_x2(result):
    summary, imodem, quad = reports()
    summary['imodem_connect'] = result
    summary['quad_connect'] = 'CONNECT 64000/ARQ/x2'
    with pytest.raises(RuntimeError, match='imodem CONNECT does not identify x2'):
        check_pair(summary, imodem, quad, require_x2=True)


@pytest.mark.parametrize('modulation', ['x2', 'X2', 'x2client', 'x2symmetric'])
def test_x2_check_accepts_explicit_modulation_not_merely_carrier(modulation):
    summary, imodem, quad = reports()
    summary['imodem_connect'] = f'CONNECT 64000/ARQ/{modulation}/LAPM'
    summary['quad_connect'] = f'CONNECT 64000/ARQ/{modulation}'
    check_pair(summary, imodem, quad, require_data=True, require_x2=True)


@pytest.mark.parametrize('role', ['imodem_connect', 'quad_connect'])
def test_one_carrier_is_not_a_working_pair(role):
    summary, imodem, quad = reports()
    summary[role] = None
    with pytest.raises(RuntimeError, match='both modems'):
        check_pair(summary, imodem, quad)


@pytest.mark.parametrize('direction', ['imodem_to_quad', 'quad_to_imodem'])
def test_one_way_or_missing_payload_is_not_bidirectional_data(direction):
    summary, imodem, quad = reports()
    del summary['payload_checks'][direction]
    with pytest.raises(RuntimeError, match='bidirectional'):
        check_pair(summary, imodem, quad, require_data=True)


@pytest.mark.parametrize('endpoint', ['imodem', 'quad', 'dsp'])
def test_execution_failure_is_not_success(endpoint):
    summary, imodem, quad = reports()
    if endpoint == 'dsp':
        imodem['mailbox']['error'] = 'bad opcode'
    else:
        (imodem if endpoint == 'imodem' else quad)['error'] = 'bad opcode'
    with pytest.raises(RuntimeError, match='CPU/DSP'):
        check_pair(summary, imodem, quad, require_data=True)


@pytest.mark.parametrize('endpoint', ['imodem', 'quad'])
def test_data_check_rejects_terminal_byte_loss(endpoint):
    summary, imodem, quad = reports()
    if endpoint == 'imodem':
        imodem['serial'] = {'a': {'output_dropped': 1}}
    else:
        quad['host_serial'] = {'overruns': 1}
    with pytest.raises(RuntimeError, match='terminal bytes lost'):
        check_pair(summary, imodem, quad, require_data=True)


def test_payloads_do_not_hide_a_cleared_quad_call():
    summary, imodem, quad = reports()
    quad['peek']['8311'] = '00'
    with pytest.raises(RuntimeError, match='Quad cleared'):
        check_pair(summary, imodem, quad, require_data=True)


@pytest.mark.parametrize('endpoint', ['imodem', 'quad'])
def test_data_check_rejects_pcm_underruns(endpoint):
    summary, imodem, quad = reports()
    if endpoint == 'imodem':
        imodem['mailbox']['pcm']['rx_empty_frames'] = 1
    else:
        quad['endpoint']['pcm_rx_underruns'] = 1
    with pytest.raises(RuntimeError, match='PCM underrun'):
        check_pair(summary, imodem, quad, require_data=True)
