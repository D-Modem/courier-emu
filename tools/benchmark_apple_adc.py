#!/usr/bin/env python3
"""Offline ADC retune control: no USB, HAL, line seizure or calls. Needs numpy.

A deliberately queued old-rate waveform demonstrates the clock-label hazard;
its duration is not a claim about the actual live FIFO's occupancy.
"""
import json
from pathlib import Path
import struct
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from courier_emu.dsp import NativeC5x, prepare_line_input


def measure(hardware_grid):
    source_rate = 10286 if hardware_grid else 7200
    if hardware_grid:
        for rate in (7200, 9600):
            prepare_line_input(source_rate, rate)
    with NativeC5x.from_program(0, struct.pack('<H', 0xbe22)) as core:
        core.configure_rom_codec()
        core.configure_line_frame_interrupt(5, 0xffff)
        for word in (3, 0x010a, 3, 0x0214):
            core.host_write(0x21, word)
        values = np.rint(10000*np.sin(2*np.pi*2400*np.arange(source_rate)/source_rate)).astype(int).tolist()
        if hardware_grid:
            core.set_line_input_rate(source_rate, cushion=0, prepared_only=True)
            core.queue_line_rx(values)
        else:
            core.queue_codec_rx(values)
        output = []
        for clock, frames in ((2880000, 720), (3840000, 960)):
            core.set_codec_mclk(clock)
            for k in range(frames):
                state = core.codec_state()
                core.step_cycles(state['line_frame_next_cycle']-state['cycles'])
                if clock == 3840000 and k >= 480:
                    value = core.register(0x20)
                    output.append(value-65536 if value >= 32768 else value)
        spectrum = abs(np.fft.rfft(np.array(output)*np.hanning(len(output))))
        return {'input_tone_hz':2400, 'source_rate':source_rate,
                'adc_before_hz':7200,'adc_after_hz':9600,
                'measured_after_hz':float(np.argmax(spectrum)*9600/len(output)),
                'empty_adc_frames':core.codec_state()['rx_empty_frames'],
                'extra_receive_cushion':0}


if __name__ == '__main__':
    result = {'preconverted_control':measure(False),'hardware_clocked':measure(True),
              'hardware_opened':False,
              'caution':'Control queues extra old-rate audio to expose the hazard, not to reproduce live FIFO occupancy.'}
    assert result['preconverted_control']['measured_after_hz'] == 3200
    assert result['hardware_clocked']['measured_after_hz'] == 2400
    assert result['hardware_clocked']['empty_adc_frames'] == 0
    print(json.dumps(result,indent=2))
