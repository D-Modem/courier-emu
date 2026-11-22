"""Separate outgoing scheduling headroom from B-channel receive latency."""
import pytest

from courier_emu.cli import _bri_sip_buffer_samples, build_parser


@pytest.mark.parametrize('flags,expected', [
    ([], (320, 480)),
    (['--bri-sip-buffer-ms', '200'], (1600, 1600)),
    (['--bri-sip-tx-buffer-ms', '200'], (320, 1600)),
    (['--bri-sip-tx-buffer-ms', '20'], (320, 160)),
    (['--bri-sip-buffer-ms', '200', '--bri-sip-tx-buffer-ms', '20'], (1600, 160)),
    (['--bri-sip-buffer-ms', '40', '--bri-sip-tx-buffer-ms', '200'], (320, 1600)),
    (['--bri-sip-buffer-ms', '80', '--bri-sip-tx-buffer-ms', '200',
      '--bri-sip-rtp-delay-ms', '60'], (640, 1600)),
])
def test_buffer_defaults_legacy_and_transmit_override(flags, expected):
    args = build_parser().parse_args(['isdn-run', 'Ie030002.nac', *flags])
    assert _bri_sip_buffer_samples(args) == expected
    assert args.bri_sip_rtp_delay_ms == 60


@pytest.mark.parametrize('value', ['-1', '0', '19'])
def test_transmit_override_requires_one_packet_reserve(value):
    with pytest.raises(SystemExit):
        build_parser().parse_args(['isdn-run', 'Ie030002.nac',
                                  '--bri-sip-tx-buffer-ms', value])


def test_receive_rtp_delay_remains_independent_of_both_bearer_reserves():
    args = build_parser().parse_args(['isdn-run', 'Ie030002.nac',
        '--bri-sip-buffer-ms', '40', '--bri-sip-tx-buffer-ms', '200',
        '--bri-sip-rtp-delay-ms', '80'])
    assert args.bri_sip_rtp_delay_ms == 80
    assert _bri_sip_buffer_samples(args) == (320, 1600)
