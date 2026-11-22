import math
from types import SimpleNamespace

import pytest

from courier_emu.bearer_line import BearerLineLink, ULAW_FULL_SCALE_DBM0
from courier_emu.line import LineLink


def test_si3034_bearer_levels_match_tip_ring_electrical_characteristics():
    peer = BearerLineLink(LineLink('/tmp/unused-si3034-test.sock', digital=True), codec='si3034')
    # A digital full-scale sine represents 1 V peak into 600 ohms at TIP/RING.
    line_power_dbm = 10 * math.log10(0.5 / 600 * 1000)
    assert ULAW_FULL_SCALE_DBM0 + 20 * math.log10(peer.from_line) == pytest.approx(line_power_dbm)
    # The same physical receive sine reaches SDO 0.9 dB below full scale.
    sine_at_line = 32767 * 10 ** ((line_power_dbm - ULAW_FULL_SCALE_DBM0) / 20)
    assert sine_at_line * peer.into_courier == pytest.approx(32767 * 10 ** (-0.9 / 20))


def test_default_ac01_bearer_levels_retain_the_board_daa_loss():
    peer = BearerLineLink(LineLink('/tmp/unused-ac01-test.sock', digital=True))
    assert 20 * math.log10(peer.from_line) == pytest.approx(8.75 - 3.21 - 11.4)
    assert 20 * math.log10(peer.into_courier) == pytest.approx(3.21 - 8.75)


def test_wallclock_idle_poll_cannot_manufacture_line_samples(monkeypatch):
    now = [100.0]
    monkeypatch.setattr('courier_emu.peripheral_clock.time.monotonic', lambda: now[0])
    line = SimpleNamespace(digital=True, connected=True, closed=False)
    peer = BearerLineLink(line, realtime_clock=True)
    peer.answered = True
    dsc = SimpleNamespace(bearer_tx={1: bytearray(), 2: bytearray()})
    exchanges = []
    peer._exchange = lambda dsc, channel, octets: exchanges.append(octets)
    peer.clock(dsc, 1, 0)
    # A fast supervisor may retire a second's instructions without a single
    # sample period elapsing. The highway must stay put too.
    peer.clock(dsc, 1, 5_000_000)
    assert not exchanges
    from courier_emu.bearer_line import LINE_FRAME_SAMPLES
    now[0] += (LINE_FRAME_SAMPLES + 1) / 8000
    peer.clock(dsc, 1, 5_000_001)
    assert exchanges == [b'\xff' * LINE_FRAME_SAMPLES]
    assert peer.active_idle_samples == LINE_FRAME_SAMPLES + 1
    assert peer.feeds_ahead
