"""Quiet SIP clock passes must be identical to the full clock's early return."""
from types import SimpleNamespace

import pytest

from courier_emu.bridge import CourierDspBridge, LINE_FRAME_INSTRUCTIONS


def bridge():
    b = CourierDspBridge.__new__(CourierDspBridge)
    b._sip_line = object()
    b.line = None
    b.exchange = object()
    b.active = b.launched = b.boot_rom_enabled = True
    b.error = None
    b._runtime_mode = False
    b._runtime_ready = True
    b.batch = 4096
    b._instructions = 0
    b._exchange_instructions = 0
    b._codec_instructions = 0
    b._x86_ticks = 0
    b.codec = object()
    b.core = SimpleNamespace(state=lambda: {'instructions': 11, 'cycles': 17})
    b._service_exchange = lambda: pytest.fail('exchange deadline was crossed')
    b._service_codec = lambda: pytest.fail('codec deadline was crossed')
    return b


def counters(b):
    return {k: v for k, v in b.__dict__.items()
            if k in ('_instructions', '_exchange_instructions', '_codec_instructions',
                     '_x86_ticks', '_probe_clock_last', 'probe_clock')}


@pytest.mark.parametrize('with_codec', [True, False])
@pytest.mark.parametrize('instructions', [0, 199980])
def test_quiet_pass_matches_full_clock_exactly(with_codec, instructions):
    fast, full = bridge(), bridge()
    for b in (fast, full):
        b._instructions = instructions
        if not with_codec:
            b.codec = None
    for _ in range(63):
        assert fast.clock_x86_fast(64)
        full.clock_x86(64)
        assert counters(fast) == counters(full)
    assert fast._x86_ticks == 4032
    before = counters(fast)
    assert not fast._clock_sip_waiting(64)
    assert counters(fast) == before


@pytest.mark.parametrize('field,value', [
    ('_sip_line', None), ('line', object()), ('exchange', None),
    ('active', False), ('error', 'failed'), ('launched', False),
    ('_exchange_instructions', 4032), ('_x86_ticks', 4032),
    ('_codec_instructions', LINE_FRAME_INSTRUCTIONS - 64),
])
def test_quiet_guard_has_no_side_effects(field, value):
    b = bridge()
    setattr(b, field, value)
    before = counters(b)
    assert not b._clock_sip_waiting(64)
    assert counters(b) == before


def test_runtime_ready_transition_is_not_skipped():
    b = bridge()
    b._runtime_mode = True
    b._runtime_ready = False
    b._runtime_ready_delay = 64
    before = counters(b)
    assert not b._clock_sip_waiting(64)
    assert counters(b) == before
    assert b._runtime_ready_delay == 64


@pytest.mark.parametrize('count', [0, -1, 4096, 5000])
def test_invalid_or_deadline_crossing_counts_use_full_path(count):
    b = bridge()
    before = counters(b)
    assert not b._clock_sip_waiting(count)
    assert counters(b) == before
