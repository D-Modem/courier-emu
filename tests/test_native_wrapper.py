"""The native call-setup path must preserve Python hook/event ordering."""
import ctypes
from types import SimpleNamespace

import pytest

from courier_emu import x86_interpreter as x86
from courier_emu import x86_native


HOST = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_int,
                        ctypes.c_uint16, ctypes.c_int, ctypes.c_uint16,
                        ctypes.c_uint64, ctypes.POINTER(ctypes.c_uint16))
POLL = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_uint64,
                        ctypes.c_uint32, ctypes.c_void_p)


def setup(monkeypatch, enabled):
    monkeypatch.setenv('COURIER_X86_NATIVE_WRAPPER', str(int(enabled)))
    cpu = x86.Uc(0, 0)
    cpu.mem_map(0, len(cpu.memory))
    cpu.memory[0x100:0x110] = b'\x90' * 16
    cpu.regs[x86.UC_X86_REG_IP] = 0x100
    # Select the gated-worker wrapper without suppressing ordinary test hooks.
    cpu.native_after_run_gate = (None, 0, 0)
    native = x86_native.NativeInterpreter(cpu)
    assert (native._run_cpu is not None) == enabled
    return cpu, native


def snapshot(cpu, native):
    return (cpu.regs.copy(), bytes(cpu.memory), cpu.retired, cpu._clock_next,
            bytes(native.int_counts), native.statistics(), native.poll_code)


def test_captures_host_metadata_before_hook_but_cpu_buffers_after_it(monkeypatch):
    results = []
    for enabled in (False, True):
        cpu, native = setup(monkeypatch, enabled)
        events = []
        @HOST
        def first(context, direction, port, size, value, now, out):
            events.append(('first', now, direction, port, size))
            out[0] = 0x5a
            return 1
        @HOST
        def second(*args):
            events.append(('wrong-host',))
            return 0
        ports = bytearray(65536)
        ports[0x40] = 1
        cpu.native_host_io = (ctypes.cast(first, ctypes.c_void_p).value, 0, ports)
        cpu.native_host_base = 1000
        cpu.retired = 7
        def before():
            events.append(('before', cpu.regs[x86.UC_X86_REG_IP]))
            cpu.native_host_io = (ctypes.cast(second, ctypes.c_void_p).value, 0, ports)
            cpu.native_host_base = 9000
            cpu.retired = 99
            cpu.regs = cpu.regs.copy()
            cpu.regs[x86.UC_X86_REG_IP] = 0x200
            cpu.memory = bytearray(cpu.memory)
            cpu.memory[0x200:0x203] = bytes.fromhex('e4 40 90')
        cpu.native_before_run = before
        cpu.native_after_run = lambda: events.append(('after', cpu.regs[x86.UC_X86_REG_IP]))
        done = native.execute(cpu, 2)
        results.append((snapshot(cpu, native), events, done))
    assert results[0] == results[1]
    assert results[0][1] == [('before', 0x100), ('first', 1008, 1, 0x40, 1), ('after', 0x203)]


def test_poll_state_is_captured_before_hooks_and_clock_progress_published_after(monkeypatch):
    results = []
    for enabled in (False, True):
        cpu, native = setup(monkeypatch, enabled)
        events = []
        @HOST
        def host(*args):
            return 0
        @POLL
        def poll(context, now, flags, registers):
            events.append(('poll', now))
            return 1
        @POLL
        def wrong(*args):
            events.append(('wrong-poll',))
            return 0
        cpu.native_host_io = (ctypes.cast(host, ctypes.c_void_p).value, 0, bytearray(65536))
        cpu.native_poll = (ctypes.cast(poll, ctypes.c_void_p).value, 0)
        cpu._clock_callback = lambda *args: None
        cpu._clock_next = cpu._clock_period = 2
        def before():
            cpu._clock_next = cpu._clock_period = 100
            cpu._clock_callback = None
            cpu.native_poll = (ctypes.cast(wrong, ctypes.c_void_p).value, 0)
        cpu.native_before_run = before
        cpu.native_after_run = lambda: events.append(('after', cpu._clock_next))
        done = native.execute(cpu, 5)
        results.append((snapshot(cpu, native), events, done))
    assert results[0] == results[1]
    assert ('after', 100) in results[0][1]
    assert not any(e[0] == 'wrong-poll' for e in results[0][1])


@pytest.mark.parametrize('where', ['before', 'after'])
def test_callback_failures_preserve_progress_and_skip_later_bookkeeping(where, monkeypatch):
    results = []
    for enabled in (False, True):
        cpu, native = setup(monkeypatch, enabled)
        events = []
        def before():
            events.append('before')
            if where == 'before':
                raise ValueError('before failed')
        def after():
            events.append('after')
            raise ValueError('after failed')
        cpu.native_before_run, cpu.native_after_run = before, after
        with pytest.raises(ValueError, match=f'{where} failed'):
            native.execute(cpu, 3)
        results.append((snapshot(cpu, native), events))
    assert results[0] == results[1]
    assert results[0][1] == (['before'] if where == 'before' else ['before', 'after'])


@pytest.mark.parametrize('host_enabled,poll_enabled,mmio_enabled', [
    (False, False, False), (True, False, False), (True, True, False),
    (False, False, True), (True, False, True), (True, True, True),
])
def test_replaced_run_keeps_argument_shape_even_when_replaced_by_before_hook(
        host_enabled, poll_enabled, mmio_enabled, monkeypatch):
    results = []
    for enabled in (False, True):
        cpu, native = setup(monkeypatch, enabled)
        events = []
        @HOST
        def host(*args):
            return 0
        @POLL
        def poll(*args):
            return 1
        if host_enabled:
            cpu.native_host_io = (ctypes.cast(host, ctypes.c_void_p).value, 0, bytearray(65536))
        if poll_enabled:
            cpu.native_poll = (ctypes.cast(poll, ctypes.c_void_p).value, 0)
            cpu._clock_callback = lambda *args: None
            cpu._clock_next = cpu._clock_period = 2
        if mmio_enabled:
            cpu.native_mmio_callback = lambda *args: None
            cpu.native_mmio_batch = ((0x400, 0x410),)
        original = native.run
        def tracked(*args):
            events.append(('run', len(args)))
            return original(*args)
        cpu.native_before_run = lambda: setattr(native, 'run', tracked)
        cpu.native_after_run = lambda: events.append(('after',))
        done = native.execute(cpu, 5)
        results.append((snapshot(cpu, native), events, done))
    assert results[0] == results[1]
    expected = 16 if mmio_enabled else 15 if poll_enabled else 12 if host_enabled else 8
    assert results[0][1] == [('run', expected), ('after',)]


def test_native_io_can_replace_buffers_and_after_hook_without_dangling_storage(monkeypatch):
    results = []
    for enabled in (False, True):
        cpu, native = setup(monkeypatch, enabled)
        events = []
        @HOST
        def host(context, direction, port, size, value, now, out):
            events.append(('host', now))
            cpu.regs = cpu.regs.copy()
            cpu.memory = bytearray(cpu.memory)
            native.guard = bytearray(native.guard)
            native.fast_out = bytearray(native.fast_out)
            native.io_events = bytearray(native.io_events)
            cpu.native_after_run = lambda: events.append(('new-after',))
            out[0] = 0x5a
            return 1
        ports = bytearray(65536)
        ports[0x40] = 1
        cpu.memory[0x100:0x103] = bytes.fromhex('e4 40 90')
        cpu.native_host_io = (ctypes.cast(host, ctypes.c_void_p).value, 0, ports)
        cpu.native_after_run = lambda: events.append(('old-after',))
        done = native.execute(cpu, 2)
        results.append((snapshot(cpu, native), events, done))
    assert results[0] == results[1]
    assert results[0][1] == [('host', 1), ('new-after',)]


@pytest.mark.parametrize('size', [0, 9, 11])
def test_bad_replacement_result_does_not_run_after_hook(size, monkeypatch):
    for enabled in (False, True):
        cpu, native = setup(monkeypatch, enabled)
        events = []
        native.run = lambda *args: [0] * size
        cpu.native_after_run = lambda: events.append('after')
        with pytest.raises(ValueError):
            native.execute(cpu, 1)
        assert events == []


def test_engine_validation_error_does_not_run_after_hook(monkeypatch):
    for enabled in (False, True):
        cpu, native = setup(monkeypatch, enabled)
        events = []
        def before():
            events.append('before')
            cpu.memory = bytearray(32)
        cpu.native_before_run = before
        cpu.native_after_run = lambda: events.append('after')
        with pytest.raises(ValueError, match='invalid native CPU buffers'):
            native.execute(cpu, 1)
        assert events == ['before']


@pytest.mark.parametrize('armed', [0, 1])
@pytest.mark.parametrize('dirty,error', [(0, 0), (1, 0), (0, 7), (1, 7)])
def test_worker_after_gate_only_disarms_and_reports_publication_work(armed, dirty, error):
    from courier_emu.worker_poll import WorkerPoll, WorkerPollState
    worker = WorkerPoll()
    assert worker.after_run_gate is not None
    worker.state.armed, worker.state.dirty, worker.state.presend_error = armed, dirty, error
    expected = WorkerPollState.from_buffer_copy(bytes(worker.state))
    expected.armed = 0
    function, context = worker.after_run_gate
    invoke = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p)(function)
    assert invoke(context) == bool(dirty or error)
    assert bytes(worker.state) == bytes(expected)
    assert invoke(None) == 1


@pytest.mark.parametrize('dirty,error', [(0, 0), (1, 0), (0, 7), (1, 7)])
def test_native_after_gate_preserves_state_and_only_skips_empty_publications(dirty, error, monkeypatch):
    from courier_emu.worker_poll import WorkerPoll
    results = []
    for enabled in (False, True):
        cpu, native = setup(monkeypatch, enabled)
        worker = WorkerPoll()
        worker.state.armed = 1
        worker.state.dirty, worker.state.presend_error = dirty, error
        events, calls = [], []
        def after():
            calls.append('after')
            worker.state.armed = 0
            if worker.state.presend_error:
                events.append(('error', worker.state.presend_error))
                worker.state.presend_error = 0
            if worker.state.dirty:
                events.append(('dirty',))
                worker.state.dirty = 0
        cpu.native_after_run = after
        cpu.native_after_run_gate = (after, *worker.after_run_gate)
        native.execute(cpu, 3)
        results.append((snapshot(cpu, native), bytes(worker.state), events))
        assert len(calls) == int(not enabled or bool(dirty or error))
    assert results[0] == results[1]


def test_after_gate_is_bound_to_callback_identity(monkeypatch):
    from courier_emu.worker_poll import WorkerPoll
    cpu, native = setup(monkeypatch, True)
    worker = WorkerPoll()
    worker.state.armed = 1
    events = []
    def old():
        pytest.fail('old callback must not run')
    cpu.native_after_run_gate = (old, *worker.after_run_gate)
    cpu.native_after_run = lambda: events.append(worker.state.armed)
    native.execute(cpu, 3)
    assert events == [1]  # Neither the stale gate nor old callback ran.


def test_worker_older_library_has_no_after_gate(monkeypatch):
    from courier_emu import worker_poll
    library = worker_poll.load_library()
    class OldLibrary:
        def __getattr__(self, name):
            if name == 'courier_worker_after_run_gate':
                raise AttributeError(name)
            return getattr(library, name)
    monkeypatch.setattr(worker_poll, 'load_library', lambda: OldLibrary())
    assert worker_poll.WorkerPoll().after_run_gate is None


def test_subclasses_keep_attribute_dispatch_in_python(monkeypatch):
    monkeypatch.setenv('COURIER_X86_NATIVE_WRAPPER', '1')
    class CustomCpu(x86.Uc):
        pass
    class CustomRunner(x86_native.NativeInterpreter):
        pass
    assert x86_native.NativeInterpreter(CustomCpu(0, 0))._run_cpu is None
    assert CustomRunner(x86.Uc(0, 0))._run_cpu is None


def test_ordinary_cpu_without_worker_gate_keeps_python_wrapper(monkeypatch):
    monkeypatch.setenv('COURIER_X86_NATIVE_WRAPPER', '1')
    assert x86_native.NativeInterpreter(x86.Uc(0, 0))._run_cpu is None


def test_missing_optional_extension_entrypoint_keeps_python_wrapper(monkeypatch):
    cpu, reference = setup(monkeypatch, True)
    old_module = SimpleNamespace(run=reference.run, inject_interrupt=reference._inject_interrupt)
    spec = SimpleNamespace(loader=SimpleNamespace(exec_module=lambda module: None))
    monkeypatch.setattr(x86_native.importlib.util, 'spec_from_file_location', lambda *args: spec)
    monkeypatch.setattr(x86_native.importlib.util, 'module_from_spec', lambda spec: old_module)
    native = x86_native.NativeInterpreter(cpu)
    assert native._run_cpu is None
    assert native.execute(cpu, 3) == 3
