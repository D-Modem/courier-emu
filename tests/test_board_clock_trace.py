import struct

import pytest

from courier_emu.dsp import LaneHostIo, NativeC5x
from tests.test_output_exhaustion_trace import configure


def test_clock_samples_account_for_edges_irqs_and_raw_pcm_without_advancing_core():
    with NativeC5x.from_program(0, struct.pack('<H', 0xbe22)) as core:
        model = LaneHostIo()
        try:
            configure(model, core)
            core.configure_rom_codec()
            core.configure_line_frame_interrupt(5, 0xffff)
            for word in (3, 0x010a, 3, 0x0214):
                core.host_write(0x21, word)
            core.queue_line_rx([1234] * 2400)
            model.record_irq(1, 6, 12, 0, 0x93a34, 0x202)
            assert model.clock_trace() == []  # Opt-in, independent of core clocking.
            model.set_recent()
            model.record_irq(1, 6, 12, 0, 0x93a34, 0x202)
            first, = model.clock_trace()
            assert first['line_input_queued'] == 2432  # Includes the one-time cushion.
            assert first['line_input_consumed'] == 0
            assert first['line_input_pending'] == 2432
            for now in range(2, 10):
                model.record_irq(now, 7, 12, 0x8000, 0x80000, 0x202)
                model.record_irq(now, 6, 20, 0, 0x80000, 0x202)
                model.record_irq(now, 6, 21, 0, 0x80000, 0x202)
                model.record_irq(now, 6, 15, 0, 0x80000, 0x202)
                model.record_irq(now, 6, 12, 0, 0x93a34, 0x202)
            assert len(model.clock_trace()) == 1  # Sparse, not every IRQ.
            core.step_cycles(4032000)
            before = core.state()
            model.record_irq(60001, 6, 12, 0, 0x93a34, 0x202)
            last = model.clock_trace()[-1]
            assert core.state() == before
            assert last['line_input_queued'] == 2432
            assert last['line_input_consumed'] + last['line_input_pending'] == 2432
            assert abs(last['line_input_consumed'] - 800) <= 2
            assert last['frame_irq_entries'] == 10
            assert last['frame_eoi_observations'] == 8
            assert last['serial_rx_entries'] == last['serial_tx_entries'] == last['tick_entries'] == 8
            assert last['epoch'] == first['epoch']
            assert model.clock_trace(limit=1) == [last]
            assert model.clock_trace(limit=0) == []
            assert model.clock_trace()[-1] == last  # Non-draining.
        finally:
            model.close()


def test_clock_history_is_bounded_and_marks_reset_epochs():
    with NativeC5x.from_program(0, struct.pack('<H', 0xbe22)) as core:
        model = LaneHostIo()
        try:
            configure(model, core)
            model.set_recent()
            core.step(1)
            model.record_irq(1, 6, 12, 0, 0, 0x202)
            core.reset()
            model.record_irq(2, 6, 12, 0, 0, 0x202)
            assert [r['epoch'] for r in model.clock_trace()] == [1, 2]
            for index in range(9000):
                model.record_irq(60002 + index * 60000, 6, 12, 0, 0, 0x202)
            rows = model.clock_trace()
            assert len(rows) == 8192
            assert rows[-1]['frame_irq_entries'] == 9002
            model.set_recent(False)
            assert model.clock_trace() == []
            for limit in (-1, 8193):
                with pytest.raises(ValueError, match='limit'):
                    model.clock_trace(limit)
        finally:
            model.close()
