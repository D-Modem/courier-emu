"""The terminal must not add a second clock to an externally paced bearer."""
from io import StringIO
from types import SimpleNamespace

from courier_emu.isdn_console import interactive_pump
from courier_emu.pit import INSTRUCTIONS_PER_SECOND


def setup(monkeypatch):
    now = [0.0]
    sleeps = []
    monkeypatch.setattr('courier_emu.isdn_console.time.monotonic', lambda: now[0])
    monkeypatch.setattr('courier_emu.isdn_console.time.sleep', sleeps.append)
    monkeypatch.setattr('courier_emu.isdn_console.select.select', lambda *args: ([], [], []))
    active = [False]
    machine = SimpleNamespace(instructions=0, with_dsp=True,
                              _live_bearer=lambda: active[0],
                              dte_framing=lambda: 0, take_serial=lambda: b'')
    pump = interactive_pump(after=0, input_stream=StringIO(), output_stream=StringIO())
    return pump, machine, now, sleeps, active


def test_offline_terminal_retains_instruction_pacing(monkeypatch):
    pump, machine, now, sleeps, active = setup(monkeypatch)
    pump(machine)
    machine.instructions = INSTRUCTIONS_PER_SECOND // 100
    pump(machine)
    assert sleeps == [.01]


def test_live_bearer_has_no_terminal_sleep_and_exit_rebases_clock(monkeypatch):
    pump, machine, now, sleeps, active = setup(monkeypatch)
    pump(machine)
    active[0] = True
    machine.instructions = INSTRUCTIONS_PER_SECOND
    pump(machine)
    machine.instructions += 20 * INSTRUCTIONS_PER_SECOND
    pump(machine)
    assert sleeps == []
    # Returning to idle must not sleep for the CPU instructions retired
    # during the externally clocked call.
    active[0] = False
    now[0] = 2
    pump(machine)
    assert sleeps == []
    machine.instructions += INSTRUCTIONS_PER_SECOND // 100
    pump(machine)
    assert abs(sleeps[-1] - .01) < 1e-12


def test_bearer_without_dsp_does_not_disable_terminal_pacing(monkeypatch):
    pump, machine, now, sleeps, active = setup(monkeypatch)
    machine.with_dsp = False
    active[0] = True
    pump(machine)
    machine.instructions = INSTRUCTIONS_PER_SECOND // 100
    pump(machine)
    assert sleeps == [.01]
