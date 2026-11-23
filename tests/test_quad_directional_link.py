"""Directional x2/V.34 evidence must come from the DSPs, not two CONNECTs."""
import json
from pathlib import Path

import pytest

from tools.quad_directional_link import inspect_directional_link, pcm_nominal_bps


CAPTURE = Path(__file__).with_name('fixtures') / 'quad-asymmetric-peer-20261019.json'


def capture():
    report = json.loads(CAPTURE.read_text())
    return report['analog'], report['quad']


def test_saved_call_has_reciprocal_pcm_and_v34_rates_despite_connect_labels():
    analog, quad = capture()
    assert '33333/ARQ/x2' in quad['terminal']
    result = inspect_directional_link(analog, quad)
    assert result['quad_rate_word'] == '0c0b'
    assert result['analog_rate_word'] == '0b0c'
    assert result['upstream'] == dict(modulation='V.34', bps=26400, rate_index=11)
    assert result['downstream'] == dict(modulation='x2 PCM', nominal_bps=53333, rate_index=12)


@pytest.mark.parametrize('index,bps', [(1, 33333), (2, 37333), (3, 41333),
                                      (11, 52000), (12, 53333), (15, 57333)])
def test_sparse_pcm_ladder_is_not_the_v34_rate_ladder(index, bps):
    assert pcm_nominal_bps(index) == bps


@pytest.mark.parametrize('fault', ['role', 'callback', 'tx_callback', 'code', 'missing_server',
                                  'missing_client', 'disagreement', 'symmetric_rate'])
def test_connect_labels_cannot_hide_missing_or_conflicting_dsp_evidence(fault):
    analog, quad = capture()
    if fault == 'role':
        quad['x2_status_inputs']['8954'] = 4
    elif fault == 'callback':
        quad['dsp_cells']['039b'] = 0xF5E9
    elif fault == 'tx_callback':
        quad['dsp_cells']['039a'] = 0xC354
    elif fault == 'code':
        quad['v34_receive_code_sha256'] = 'changed overlay'
    elif fault == 'missing_server':
        quad['endpoint']['exchanges'] = []
    elif fault == 'missing_client':
        analog['dsp_bridge']['dsp_mailbox_log'] = []
    elif fault == 'disagreement':
        quad['endpoint']['exchanges'].append(
            dict(direction='dsp-to-cpu', command=0x6a, argument=0x0c0a))
    else:
        quad['endpoint']['exchanges'].append(
            dict(direction='dsp-to-cpu', command=0x6a, argument=0x1010))
    with pytest.raises(AssertionError):
        inspect_directional_link(analog, quad)
