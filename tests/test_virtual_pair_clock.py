from types import SimpleNamespace

import pytest

from courier_emu.bearer_line import BearerLineLink, CPU_INSTRUCTIONS_PER_SAMPLE, LINE_FRAME_SAMPLES
from courier_emu.nac import NacImage
from courier_emu.isdn import IsdnMachine
from courier_emu.peripheral_clock import PeripheralClock
from courier_emu.poll_state import PollState


@pytest.mark.parametrize('realtime,coupled,paced,external', [
    (True, False, True, True), (True, True, True, False),
    (False, True, False, False), (False, False, False, False),
])
def test_virtual_pacing_is_distinct_from_independent_external_clock(realtime, coupled, paced, external):
    m = IsdnMachine.__new__(IsdnMachine)
    m.bri = SimpleNamespace(call_state='active', media_peer=SimpleNamespace(
        realtime_clock=realtime, instruction_clocked=coupled))
    assert m._paced_bearer() == paced
    assert m._live_bearer() == external
    m.bri.call_state = 'null'
    assert not m._paced_bearer() and not m._live_bearer()


def test_coupled_peripheral_time_advances_only_with_the_machine(monkeypatch):
    now = [100.0]
    monkeypatch.setattr('courier_emu.peripheral_clock.time.monotonic', lambda: now[0])
    m = IsdnMachine.__new__(IsdnMachine)
    m.with_dsp = True
    m.instructions = 1000
    m._peripheral_clock = PeripheralClock(5_000_000)
    m.bri = SimpleNamespace(call_state='active', media_peer=SimpleNamespace(
        realtime_clock=True, instruction_clocked=True))
    assert m._peripheral_instructions() == 1000
    now[0] += 100
    assert m._peripheral_instructions() == 1000
    m.instructions += 500000
    assert m._peripheral_instructions() == 501000
    assert m._peripheral_clock.origin_time is None


def test_coupled_pit_keeps_100_hz_guest_time_not_independent_wall_time(monkeypatch):
    now = [100.0]
    monkeypatch.setattr('courier_emu.peripheral_clock.time.monotonic', lambda: now[0])
    monkeypatch.setattr('courier_emu.isdn.native_monotonic_ns', lambda: 10_000_000_000)
    monkeypatch.setattr('courier_emu.isdn.time.sleep', lambda _: None)
    m = IsdnMachine(NacImage.load('Ie030002.nac'))
    m.with_dsp = True
    m.bri = SimpleNamespace(call_state='active', media_peer=SimpleNamespace(
        realtime_clock=True, instruction_clocked=True), service=lambda *args: None)
    m._advance_dsp = lambda *, supervisor_turn: None
    m.write_port(0xf043, 0x74)
    m.write_port(0xf041, 8928 & 255)
    m.write_port(0xf041, 8928 >> 8)
    m.poll_timers()
    now[0] += 100
    m.instructions += 500000
    m.poll_timers()
    assert m.pit.status(m._peripheral_instructions())['counters'][1]['wraps'] == 10
    m._pace_live_cpu()
    assert m._ps.live_cpu_ns  # Coupled does not mean unpaced/offline CPU.


def test_coupled_cpu_is_still_wall_paced_without_native_elision(monkeypatch):
    m = IsdnMachine.__new__(IsdnMachine)
    m.bri = SimpleNamespace(call_state='active', media_peer=SimpleNamespace(
        realtime_clock=True, instruction_clocked=True))
    m.instructions = 1000
    m._ps = PollState()
    sleeps = []
    monkeypatch.setattr('courier_emu.isdn.native_monotonic_ns', lambda: 10_000_000_000)
    monkeypatch.setattr('courier_emu.isdn.time.sleep', sleeps.append)
    m._pace_live_cpu()
    assert m._ps.live_cpu_ns == 10_000_000_000
    m.instructions += 5000
    m._pace_live_cpu()
    assert sleeps == [.001]


def test_coupled_fallback_does_not_turn_host_stalls_into_pcm_silence(monkeypatch):
    now = [100.0]
    monkeypatch.setattr('courier_emu.peripheral_clock.time.monotonic', lambda: now[0])
    line = SimpleNamespace(digital=True, connected=True, closed=False)
    peer = BearerLineLink(line, realtime_clock=True, instruction_clocked=True)
    peer.answered = True
    dsc = SimpleNamespace(bearer_tx={1: bytearray(), 2: bytearray()})
    exchanges = []
    peer._exchange = lambda dsc, channel, octets: exchanges.append(octets)
    peer.clock(dsc, 1, 0)
    now[0] += 100
    peer.clock(dsc, 1, 0)
    assert not exchanges and peer.active_idle_samples == 0
    # Legitimate elapsed guest time still clocks idle samples normally.
    peer.clock(dsc, 1, LINE_FRAME_SAMPLES * CPU_INSTRUCTIONS_PER_SAMPLE)
    assert exchanges == [b'\xff' * LINE_FRAME_SAMPLES]
    assert peer.active_idle_samples == LINE_FRAME_SAMPLES
