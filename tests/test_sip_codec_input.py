"""SIP line PCM must use the same codec-clocked ADC as socket line PCM."""
from collections import deque

import pytest

from courier_emu.bridge import CourierDspBridge
from courier_emu.dsp import NativeC5x


class Core:
    codec_sample_rate = 9600

    def __init__(self):
        self.line = []
        self.codec = []

    def queue_line_rx(self, samples):
        self.line.extend(samples)

    def queue_codec_rx(self, samples):
        self.codec.extend(samples)

    def codec_state(self):
        return {'codec_rx_size': len(self.line)}


class NoConversion:
    def convert(self, *args):
        pytest.fail('raw SIP PCM was resampled before reaching the codec ADC')


def bridge(core, source='sip'):
    b = CourierDspBridge.__new__(CourierDspBridge)
    b.core = core
    b.boot_rom_enabled = True
    b.line = object() if source == 'socket' else None
    b._sip_line = object() if source == 'sip' else None
    b._line_to_codec = NoConversion()
    b._codec_in_peak = b._codec_handed_peak = 0
    b._codec_handed_at = b._codec_handed_ever = 0
    b._instructions = 12345
    b._codec_in_flight = deque()
    return b


@pytest.mark.parametrize('source', ['sip', 'socket'])
def test_retunes_never_relabel_or_preconvert_line_samples(source):
    core = Core()
    b = bridge(core, source)
    expected = []
    for rate in (7200, 40320000 / 5320, 8000, 9600, 10266.666667):
        core.codec_sample_rate = rate
        block = list(range(1, 801))
        expected.extend(block)
        b._queue_line_audio(block)
    assert core.line == expected
    assert core.codec == []
    assert list(b._codec_in_flight) == expected
    assert b._codec_handed_at == b._instructions


def test_actual_native_sip_input_enters_raw_line_fifo():
    with NativeC5x.from_program(0x6000, b'\x22\xbe') as core:
        core.configure_rom_codec()
        b = bridge(core)
        b._queue_line_audio([123] * 800)
        # The native ADC primes its own one-time source cushion. The bridge
        # must not queue 960 codec-rate words or add a separate codec cushion.
        assert core.codec_state()['codec_rx_size'] == 832
        assert list(b._codec_in_flight) == [123] * 800


@pytest.mark.parametrize('source', ['sip', 'socket', 'none'])
def test_legacy_firmware_keeps_external_conversion(source):
    b = bridge(Core(), source)
    b.boot_rom_enabled = False
    assert not b._clocked_line_input()


def test_silent_rom_without_external_peer_keeps_legacy_input_selection():
    b = bridge(Core(), 'none')
    assert not b._clocked_line_input()
