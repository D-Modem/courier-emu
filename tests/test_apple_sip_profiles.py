import pytest

from tools.apple_sip_profiles import PROFILES, settings


@pytest.mark.parametrize('name,index', [('v22', 2), ('v22bis', 3), ('v32', 6)])
def test_fixed_controls_pin_both_rate_limits_and_disable_other_families(name, index):
    value = settings(name)
    assert f'&U{index}&N{index}' in value
    assert 'S54=192' in value and 'S56=192' in value and 'S58=33' in value
    assert 'B0&M0&B0' in value
    assert settings(name, caller=True) == 'S27=1' + value


def test_v34_keeps_v8_enabled_and_disables_pcm_without_claiming_a_fixed_rate():
    value = settings('v34')
    assert 'S54=0S56=0S58=33' in value
    assert '&U0&N0' in value


def test_lapm_control_requires_error_correction_instead_of_silent_normal_fallback():
    value = settings('v32-lapm')
    assert '&M5&B1&U6&N6&K0' in value
    assert '&M0' not in value


def test_bell103_control_keeps_original_mode_and_rate():
    assert 'B1&M0&B0&N1S56=192' in settings('bell103')
    assert all('\r' not in value and '\n' not in value for value in PROFILES.values())
