"""Batch extraction only: DSP time/steps are not part of this optimization."""
import math
from types import SimpleNamespace
import pytest
from courier_emu.bridge import CourierDspBridge, LINE_FRAME_SAMPLES
from courier_emu.resample import BandLimitedResampler


def bridge_for(enabled, events, samples):
    b = CourierDspBridge.__new__(CourierDspBridge)
    c = SimpleNamespace(writes=0, codec_sample_rate=events[0][1])
    c.line_tx_writes = lambda: c.writes
    c.line_tx_samples = lambda start: samples[start:c.writes]
    c.line_tx_clock_events = lambda: [e for e in events if e[0] <= c.writes]
    b.core = c
    b.is3453 = False
    b.boot_rom_enabled = True
    b._sip_line = object()
    b._sip_codec_batch = enabled
    b.batch = 1024
    b._exchange_instructions = 0
    b._exchange_idle = 0
    b._exchange_codec_last = 0
    b._exchange_tx_index = 0
    b._exchange_line_buffer = []
    b._codec_to_line = BandLimitedResampler()
    b._line_service = dict(tx_consumed=0, tx_index=0, tx_peak_codec=0, tx_peak_line=0)
    b.frames = []
    def service_frame():
        b.frames.extend(b._exchange_line_buffer[:LINE_FRAME_SAMPLES])
        del b._exchange_line_buffer[:LINE_FRAME_SAMPLES]
    b._service_exchange_frame = service_frame
    take = b._take_line_audio
    b.takes = []
    def counted_take():
        b.takes.append(c.writes)
        take()
    b._take_line_audio = counted_take
    return b


@pytest.mark.parametrize('events', [
    [(0, 7200)], [(0, 9600)],
    [(0, 7200), (51, 9600), (126, 10266.6666667), (431, 7200), (901, 9600)],
])
def test_batch_is_sample_exact_across_retunes_and_flushes_stalled_tail(events):
    samples = [round(13000 * math.sin(k * .19) + 2000 * math.cos(k * .71))
               for k in range(2047)]
    plain = bridge_for(False, events, samples)
    batched = bridge_for(True, events, samples)
    for end in [*range(3, len(samples), 3), len(samples)]:
        for b in (plain, batched):
            b.core.writes = end
            b.core.codec_sample_rate = [r for n, r in events if n <= end][-1]
            b._exchange_instructions += b.batch
            b._service_exchange()
            assert end - b._exchange_tx_index < 16
    # No new codec output: a short held tail must be extracted immediately,
    # not stranded indefinitely waiting for sixteen samples.
    for b in (plain, batched):
        b._exchange_instructions += b.batch
        b._service_exchange()
    assert batched._exchange_tx_index == plain._exchange_tx_index == len(samples)
    assert batched.frames == plain.frames
    assert batched._exchange_line_buffer == plain._exchange_line_buffer
    assert batched._line_service['tx_consumed'] == plain._line_service['tx_consumed']
    assert len(batched.takes) < len(plain.takes) / 4


@pytest.mark.parametrize('missing_sip,rom', [(True, True), (False, False)])
def test_batch_does_not_affect_other_transports_or_non_rom(missing_sip, rom):
    b = bridge_for(True, [(0, 7200)], [1, 2, 3])
    b._sip_line = None if missing_sip else object()
    b.boot_rom_enabled = rom
    b.core.writes = 3
    b._exchange_instructions = b.batch
    b._service_exchange()
    assert b._exchange_tx_index == 3
