"""Clock-boundary native reentry must preserve scheduler and hook semantics."""
import pytest

from courier_emu import x86_interpreter as x86


def run(monkeypatch, *, reentry, native=True, profile='186eb', period=4,
        action='plain', code=b'\x40\xeb\xfd', count=40):
    monkeypatch.setenv('COURIER_X86_SERVICE_REENTRY', str(int(reentry)))
    cpu = x86.Uc(0, 0, profile=profile)
    cpu.native_enabled = native
    cpu.mem_map(0, len(cpu.memory))
    cpu.memory[0x100:0x100 + len(code)] = code
    cpu.memory[0x200:0x203] = b'\x43\xeb\xfd'
    events = []

    def clock(uc, total, _):
        events.append(('clock', total, uc.retired, tuple(uc.regs)))
        if action == 'stop' and total >= period * 2:
            uc.emu_stop()
        elif action in ('redirect', 'free-redirect') and total == period:
            uc.regs[x86.UC_X86_REG_IP] = 0x200
            uc.redirect_is_free = action == 'free-redirect'
        elif action == 'deferred':
            uc._after_instruction = lambda: events.append(('deferred', uc.retired))
        elif action == 'code-write':
            # Replace the *pending* instruction, not the one before it.
            uc.memory[uc.regs[x86.UC_X86_REG_IP]] = 0x43

    cpu.instruction_clock_add(period, clock)
    if action == 'code-hook':
        cpu.hook_add(x86.UC_HOOK_CODE,
                     lambda uc, addr, size, _: events.append(('code', addr, uc.retired)),
                     None, 0x100, 0x100)
    if action == 'memory-hook':
        for kind in (x86.UC_HOOK_MEM_READ, x86.UC_HOOK_MEM_WRITE):
            cpu.hook_add(kind,
                         lambda uc, kind, addr, size, value, _: events.append(
                             ('memory', kind, addr, value, uc.retired, tuple(uc.regs))),
                         None, 0x400, 0x400)
    cpu.emu_start(0x100, 0, count=count)
    return cpu, events


@pytest.mark.parametrize('profile', ['186eb', '386ex'])
@pytest.mark.parametrize('period', [1, 4, 64])
@pytest.mark.parametrize('action', ['plain', 'stop', 'redirect', 'free-redirect',
                                   'deferred', 'code-write', 'code-hook'])
def test_reentry_matches_original_boundary_path(monkeypatch, profile, period, action):
    before, log_before = run(monkeypatch, reentry=False, profile=profile,
                             period=period, action=action, count=period * 3 + 1)
    after, log_after = run(monkeypatch, reentry=True, profile=profile,
                           period=period, action=action, count=period * 3 + 1)
    assert log_before == log_after
    assert before.regs == after.regs
    assert before.memory == after.memory
    assert before.retired == after.retired
    assert before._clock_next == after._clock_next
    assert before.redirect_is_free == after.redirect_is_free
    if action == 'plain':
        assert after._native.retired > before._native.retired


@pytest.mark.parametrize('code,action', [
    (bytes.fromhex('d7 eb fd'), 'plain'),  # XLAT: unsupported by native dispatch.
    (bytes.fromhex('a0 00 04 eb fb'), 'memory-hook'),
    (bytes.fromhex('a2 00 04 eb fb'), 'memory-hook'),
    (bytes.fromhex('26 40 eb fc'), 'plain'),  # Prefixed boundary stays in Python.
])
@pytest.mark.parametrize('period', [1, 4])
def test_reentry_preserves_fallback_and_watchpoints(monkeypatch, code, action, period):
    results = [run(monkeypatch, reentry=enabled, native=native, code=code,
                   action=action, period=period)
               for enabled, native in ((False, True), (True, True), (False, False))]
    before, logs = results[0]
    for after, log_after in results[1:]:
        assert logs == log_after
        assert before.regs == after.regs
        assert before.memory == after.memory
        assert before.retired == after.retired
        assert before._clock_next == after._clock_next


def test_boundary_port_io_keeps_original_path(monkeypatch):
    # The OUT at every callback must remain Python-observed, even when native
    # batching could otherwise handle it with approximate diagnostic stamps.
    results = []
    for enabled in (False, True):
        monkeypatch.setenv('COURIER_X86_SERVICE_REENTRY', str(int(enabled)))
        cpu = x86.Uc(0, 0)
        cpu.mem_map(0, len(cpu.memory))
        cpu.memory[0x100:0x104] = bytes.fromhex('e6 14 eb fc')
        cpu.instruction_clock_add(1, lambda *_: None)
        events = []
        cpu.native_out_batch_add((0x14,), lambda values, count: events.append(('native', count)))
        cpu.hook_add(x86.UC_HOOK_INSN,
                     lambda uc, port, size, value, _: events.append(('out', port, value, uc.retired)),
                     None, 1, 0, x86.UC_X86_INS_OUT)
        cpu.emu_start(0x100, 0, count=10)
        results.append((events, list(cpu.regs), cpu.retired))
    assert results[0] == results[1]
    assert results[0][0] == [('out', 0x14, 0, i) for i in range(0, 10, 2)]
