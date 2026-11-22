"""The hardware RX FIFO has one fixed clock, not yesterday's ADC rate."""
import math
import struct

import pytest

from courier_emu.dsp import NativeC5x, prepare_line_input


@pytest.mark.parametrize('frequency', [1200, 2400, 3000])
def test_hardware_waveform_has_no_time_warp_across_adc_retunes(frequency):
    source_rate = 10286
    for rate in (7200, 40320000/4666, 9600):
        prepare_line_input(source_rate, rate)
    with NativeC5x.from_program(0, struct.pack('<H', 0xbe22)) as core:
        core.configure_rom_codec()
        core.configure_line_frame_interrupt(5, 0xffff)
        core.set_line_input_rate(source_rate, cushion=0, prepared_only=True)
        for word in (3, 0x010a, 3, 0x0214):
            core.host_write(0x21, word)
        core.queue_line_rx([round(10000*math.sin(2*math.pi*frequency*k/source_rate))
                            for k in range(3000)])
        instant = error = signal = 0.0
        for mclk, divider, count in ((2880000,20,300), (3456000,20,1), (3456000,18,480)):
            for word in (3, 0x0200 | divider):
                core.host_write(0x21, word)
            core.set_codec_mclk(mclk)
            for _ in range(count):
                state = core.codec_state()
                core.step_cycles(state['line_frame_next_cycle']-state['cycles'])
                actual = core.register(0x20)
                if actual >= 32768:
                    actual -= 65536
                expected = 10000*math.sin(2*math.pi*frequency*(instant-65/source_rate))
                if instant > .02:
                    error += (actual-expected)**2
                    signal += expected**2
                instant += state['frame_period']/40320000
            assert core.codec_state()['rx_empty_frames'] == 0
        # Absolute amplitude/phase comparison; no fitting or dropped edge samples.
        assert 10*math.log10(signal/error) > 60
        assert abs(core.codec_state()['codec_rx_size']-(3000-instant*source_rate)) < 3


def test_hardware_input_grid_cannot_be_relabelled_while_queued():
    with NativeC5x.from_program(0, struct.pack('<H', 0xbe22)) as core:
        core.set_line_input_rate(10286, cushion=0)
        core.queue_line_rx([1234]*200)
        with pytest.raises(RuntimeError, match='source clock'):
            core.set_line_input_rate(8000, cushion=0)


def test_unprepared_hardware_adc_ratio_fails_without_live_table_construction():
    with NativeC5x.from_program(0, struct.pack('<H', 0xbe22)) as core:
        core.configure_rom_codec()
        core.configure_line_frame_interrupt(5, 0xffff)
        core.set_line_input_rate(12345, cushion=0, prepared_only=True)
        for word in (3, 0x010a, 3, 0x0214):
            core.host_write(0x21, word)
        core.queue_line_rx([1234]*200)
        state = core.codec_state()
        with pytest.raises(RuntimeError, match='unprepared physical ADC'):
            core.step_cycles(state['line_frame_next_cycle']-state['cycles'])
