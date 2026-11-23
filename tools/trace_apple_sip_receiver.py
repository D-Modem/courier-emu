"""Read-only DSP data-bank trace for the Apple/SIP experiment.

Run as a courier_emu CLI wrapper with APPLE_SIP_DATA_TRACE naming a new JSONL.
Collects the existing native IO event history; no PC/RAM/byte injection.
"""
import json
import os
from pathlib import Path
import runpy
import time

from courier_emu import isdn_console

original = isdn_console.interactive_pump
path = Path(os.environ['APPLE_SIP_DATA_TRACE'])
stream = path.open('x')


def traced_pump(*args, **kwargs):
    pump = original(*args, **kwargs)
    core_seen = None
    cursor = 0
    started = None
    last_snapshot = 0

    def observed(current):
        nonlocal core_seen, cursor, started, last_snapshot
        pump(current)
        core = current.mailbox.core
        if core is None:
            return
        if core is not core_seen:
            core_seen, cursor = core, core.io_event_total()
        connected = b'\r\nCONNECT' in bytes(current.channels[current.command_base].tx)
        if not connected:
            cursor = core.io_event_total()
            return
        now = time.monotonic()
        if started is None:
            started = now
        if now - started > 4:
            return
        total = core.io_event_total()
        delta = total - cursor
        if not 0 <= delta <= 8192:
            raise RuntimeError('DSP IO history overrun: trace invalid')
        rows = [e for e in core.io_events(limit=delta) if 0x58 <= e['port'] <= 0x5d] if delta else []
        if rows or now - last_snapshot > .05:
            stream.write(json.dumps({'time': now, 'cpu': current.instructions,
                'cycles': core.state()['cycles'], 'events': rows,
                'clock': current._native_io.clock_stats() if current._native_io else {},
                'dte': {name: int.from_bytes(current.machine.mem_read(0x26000 + a, n), 'little')
                        for name, a, n in [('receiver', 0xe834, 2), ('callback', 0xc922, 2), ('mode', 0xd1ea, 1)]}
            }) + '\n')
            last_snapshot = now
        cursor = total

    return observed


isdn_console.interactive_pump = traced_pump
try:
    runpy.run_module('courier_emu', run_name='__main__')
finally:
    stream.close()
