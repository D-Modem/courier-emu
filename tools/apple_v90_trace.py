"""Opt-in, fingerprint-gated C51 retrain-entry capture; no hardware access.

This owns the core's single debug PC-capture slot. It is NOT a sample-stream
recorder. Only a matching loaded C51 handler is armed, and bounded native
captures read debug data without changing guest memory, thresholds or results.
"""
from __future__ import annotations

import json
from pathlib import Path
import time

from tools.apple_mailbox_trace import MailboxRecorder

# The active PCM receiver at ddc5 can call 8d9a directly, bypassing 8d5b.
# Capture the shared tag-6 sender, which both retrain paths reach.
ENTRY = 0x8dcf
FINGERPRINTS = {
    0x8d5b: (0xb16f, 0x4180, 0xed00, 0xbf09, 0x039f, 0x4980, 0xe100,
            0x8d9a, 0xbc06, 0x1037, 0xe304, 0x8d9a, 0xbf80, 0x80d9,
            0xbe3c, 0x7a80, 0x8dcf),
    0x8dcf: (0xb906, 0x7a80, 0x83b1, 0xbc06, 0x1037, 0xb801, 0x9037, 0xef00),
}
ADDRESSES = (0x006d, 0x006e, 0x006f, 0x031a, 0x031b, 0x0337, 0x033a,
             0x039f, 0x03cb, 0x03e1, 0x03e2, 0xff00, 0xff01,
             0xff18, 0xff19, 0xfff1, 0xfff2, 0xfff4, 0xfff6, 0xfff7)


class V90MailboxRecorder(MailboxRecorder):
    """Keep retrain-entry evidence across the same reset/close boundaries.

    ENTRY is the verified C51 common tag-6 sender, not a V.90-only failure
    point. Capturing only 8d5b misses the active PCM receiver's direct timeout
    route. A capture establishes sender input state, not every caller's cause.
    The native ring holds 64 records; saturation is explicitly unknown/loss.
    """

    def __init__(self, prefix, **kwargs):
        super().__init__(prefix, **kwargs)
        self.probe_file = Path(str(prefix) + '-v90.jsonl').open('x')
        self.probe_core = None
        self.probe_armed = False
        self.probe_total = 0
        self.probe_limited = False
        self.probe_last_time = time.monotonic()
        self.probe_emit(kind='start', entry=f'{ENTRY:04x}',
                        addresses=[f'{a:04x}' for a in ADDRESSES],
                        fingerprint={f'{a:04x}': list(words) for a, words in FINGERPRINTS.items()},
                        ring_limit=64, total_limit=128,
                        warning='Opt-in debug probe; live timing overhead not yet qualified. '
                                'No coverage before arming; not a consecutive ADC capture.')

    def probe_emit(self, **row):
        self.probe_file.write(json.dumps(row) + '\n')
        self.probe_file.flush()

    def collect(self, core, reason='periodic', *, final=False):
        super().collect(core, reason, final=final)
        if not core.handle:
            return
        now = time.monotonic()
        if core is not self.probe_core:
            self.probe_core, self.probe_armed = core, False
        matching = all(core.program(a+i) == word
                       for a, words in FINGERPRINTS.items() for i, word in enumerate(words))
        if self.probe_armed and not matching:
            discarded = len(core.pc_captures())
            core.set_pc_capture(0, [])
            self.probe_armed = False
            self.probe_emit(kind='loss', epoch=self.epoch, observed=now,
                            reason='loaded handler changed; capture context unknown',
                            discarded_records=discarded)
        if not self.probe_armed and not self.probe_limited and matching:
            core.set_pc_capture(ENTRY, list(ADDRESSES))
            self.probe_armed = True
            self.probe_emit(kind='armed', epoch=self.epoch, observed=now,
                            timing='native pre-instruction register/data snapshot')
            self.probe_last_time = now
        if not self.probe_armed:
            return
        records = core.pc_captures()
        if len(records) >= 64:
            self.probe_emit(kind='loss', epoch=self.epoch, reason='possible native PC ring eviction')
        for record in records:
            if self.probe_total >= 128:
                self.probe_limited = True
                self.probe_emit(kind='loss', epoch=self.epoch, reason='probe recording budget exhausted')
                break
            if len(record) != 5 + len(ADDRESSES):
                raise ValueError('incomplete native PC-capture record')
            instruction, cycles, acc, dp, carry, *values = record
            self.probe_emit(kind='entry', epoch=self.epoch, reason=reason,
                            observed_between=[self.probe_last_time, now],
                            instruction=instruction, cycles=cycles, acc=acc, dp=dp, carry=carry,
                            ram={f'{a:04x}': v for a, v in zip(ADDRESSES, values, strict=True)})
            self.probe_total += 1
        core.clear_pc_captures()
        if self.probe_limited:
            core.set_pc_capture(0, [])
            self.probe_armed = False
        self.probe_last_time = now

    def reset_done(self, core):
        if core is self.probe_core:
            self.probe_core, self.probe_armed = None, False
        super().reset_done(core)

    def close(self):
        self.probe_file.close()
        super().close()
