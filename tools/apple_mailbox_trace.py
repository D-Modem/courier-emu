"""Opt-in passive DSP mailbox recording, surviving reset/close.

Only debug accessors are used, never consuming IO reads or guest writes.
Observation times bound batches, not exact DSP emission times. Keep this out
of normal execution: trace_worker enables it only with diagnostics requested.
"""
from __future__ import annotations

import ctypes
import hashlib
import json
from pathlib import Path
import struct
import sys
import time


def native_count(core):
    return int(core.library.courier_c5x_get_mailbox_event_count(core.handle))


def native_events(core, start, stop):
    for index in range(start, stop):
        values = (ctypes.c_uint64 * 5)()
        core.library.courier_c5x_get_mailbox_event(core.handle, index, values, len(values))
        yield dict(port=int(values[1]), value=int(values[2]), pc=int(values[3]),
                   instruction=int(values[4]))


class MailboxRecorder:
    def __init__(self, prefix, *, count=native_count, events=native_events,
                 batch_limit=2048, final_limit=8192, total_limit=65536,
                 ring_limit=8192, snapshots=4):
        if not (0 < batch_limit <= final_limit and total_limit > 0 and ring_limit > 0 and snapshots >= 0):
            raise ValueError('invalid diagnostic recording budget')
        self.prefix = Path(prefix)
        self.file = Path(str(prefix) + '-mailbox.jsonl').open('x')
        self.count, self.events = count, events
        self.batch_limit, self.final_limit = batch_limit, final_limit
        self.total_limit, self.ring_limit = total_limit, ring_limit
        self.snapshot_budget = snapshots
        self.core = None
        self.epoch = self.cursor = self.total = 0
        self.last_time = time.monotonic()
        self.meaningful = False
        self.limited = False
        self.host_limited = False
        self.emit(kind='start', monotonic=self.last_time,
                  timing='batch observation bounds, not exact emission timestamps',
                  limits=dict(batch=batch_limit, final=final_limit, total=total_limit,
                              ring_conservative=ring_limit, snapshots=snapshots))

    def emit(self, **row):
        self.file.write(json.dumps(row) + '\n')

    def collect(self, core, reason='periodic', *, final=False):
        if not core.handle:
            return
        now = time.monotonic()
        if core is not self.core:
            self.core = core
            self.epoch += 1
            self.cursor = 0
            self.meaningful = False
            self.emit(kind='epoch', epoch=self.epoch, observed=now)
        count = self.count(core)
        if count < self.cursor:
            self.emit(kind='loss', epoch=self.epoch, reason='unobserved reset or ring shrink',
                      previous_cursor=self.cursor, count=count)
            self.epoch += 1
            self.cursor = 0
        if count >= self.ring_limit and not self.limited:
            self.emit(kind='loss', epoch=self.epoch, reason='possible mailbox ring eviction', count=count)
            self.limited = True
        limit = self.final_limit if final else self.batch_limit
        stop = min(count, self.cursor + limit,
                   self.cursor + max(0, self.total_limit - self.total))
        if stop > self.cursor:
            state = core.state()
            self.emit(kind='batch', epoch=self.epoch, reason=reason,
                      observed_from=self.last_time, observed_to=now,
                      first_index=self.cursor, stop_index=stop,
                      available=count, state=state)
            received = 0
            for index, event in enumerate(self.events(core, self.cursor, stop), self.cursor):
                self.emit(kind='io', epoch=self.epoch, index=index, **event)
                if event['port'] == 0x5e and event['value'] != 8:
                    self.meaningful = True
                self.total += 1
                received += 1
            if received != stop-self.cursor:
                raise RuntimeError('native event reader returned an incomplete batch')
            self.cursor = stop
        if (final and stop < count) or (self.total >= self.total_limit and stop < count):
            self.emit(kind='loss', epoch=self.epoch, reason='recording budget exhausted',
                      remaining=count-stop)
        self.last_time = now
        self.file.flush()

    def host_command(self, words, pc, instructions):
        if self.total >= self.total_limit:
            if not self.host_limited:
                self.emit(kind='loss', reason='host recording budget exhausted')
                self.host_limited = True
            return
        self.emit(kind='host', observed=time.monotonic(), words=list(words),
                  pc=pc, cpu_instructions=instructions)
        self.total += 1

    def snapshot(self, core, reason):
        if not self.meaningful or not self.snapshot_budget:
            return
        self.snapshot_budget -= 1
        started = time.monotonic()
        files = {}
        for space in ('program', 'data'):
            raw = struct.pack('<65536H', *(getattr(core, space)(i) for i in range(65536)))
            path = Path(str(self.prefix) + f'-dsp-{self.epoch}-{reason}-{space}.bin')
            with path.open('xb') as output:
                output.write(raw)
            files[space] = dict(path=path.name, sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
        self.emit(kind='snapshot', epoch=self.epoch, reason=reason, files=files,
                  started=started, finished=time.monotonic(), state=core.state())
        self.file.flush()

    def boundary(self, core, reason):
        self.collect(core, reason, final=True)
        if core.handle:
            self.snapshot(core, reason)

    def reset_done(self, core):
        if core is self.core:
            self.core = None
            self.cursor = 0

    def safe(self, method, *args, **kwargs):
        try:
            return method(*args, **kwargs)
        except Exception as exc:
            # Never prevent physical cleanup because diagnostic IO failed.
            print(f'[trace] mailbox capture incomplete: {exc}', file=sys.stderr)
            try:
                self.emit(kind='error', error=str(exc), observed=time.monotonic())
                self.file.flush()
            except Exception:
                pass

    def close(self):
        self.file.close()


def install(recorder, core_type):
    """Wrap destructive lifecycle operations, not DSP message handling.

    The Apple bridge notifies reset silence before reset/rebuild, and closes
    the physical line before final core.close(). Recording changes no results.
    """
    old_reset, old_close = core_type.reset, core_type.close

    def reset(core, *args, **kwargs):
        recorder.safe(recorder.boundary, core, 'before-reset')
        result = old_reset(core, *args, **kwargs)
        recorder.reset_done(core)
        return result

    def close(core, *args, **kwargs):
        recorder.safe(recorder.boundary, core, 'before-close')
        return old_close(core, *args, **kwargs)

    core_type.reset, core_type.close = reset, close

    def restore():
        core_type.reset, core_type.close = old_reset, old_close
    return restore


def summarize(rows):
    """Decode ordered writes; do not turn sampled counters into messages."""
    messages, hosts, warnings, orphans = [], [], [], []
    current = batch = None
    expected = 0
    started = False

    def finish_batch():
        if batch is not None and expected != batch['stop_index']:
            warnings.append(dict(kind='loss', reason='incomplete saved batch'))

    for row in rows:
        kind = row['kind']
        if kind == 'start':
            if started:
                warnings.append(dict(kind='error', reason='duplicate recording start'))
            started = True
        elif kind in ('loss', 'error'):
            warnings.append(row)
        elif kind == 'host':
            hosts.append(row)
        elif kind == 'epoch':
            finish_batch()
            batch = current = None
        elif kind == 'batch':
            finish_batch()
            batch = row
            expected = row['first_index']
        elif kind == 'io':
            if batch is None or row['epoch'] != batch['epoch'] or row['index'] != expected:
                warnings.append(dict(kind='loss', reason='event outside ordered batch'))
                current = None
            expected = row['index']+1
            bounds = None if batch is None else [batch['observed_from'], batch['observed_to']]
            if row['port'] == 0x5e:
                current = dict(epoch=row['epoch'], tag=f"{row['value']:04x}", words=[],
                               pc=f"{row['pc']:04x}", instruction=row['instruction'],
                               observed_between=bounds)
                messages.append(current)
            elif row['port'] == 0x5f:
                if current is None:
                    orphans.append(row)
                else:
                    current['words'].append(f"{row['value']:04x}")
                    if bounds is not None:
                        current['observed_between'][1] = bounds[1]
    finish_batch()
    if not started:
        warnings.append(dict(kind='error', reason='missing recording start'))
    menus, menu = [], []
    for message in messages:
        # The resident sender writes the header's high word (zero here),
        # then its optional data word. Keep BOTH in raw message evidence.
        if message['tag'] != '0048' or len(message['words']) != 2 or message['words'][0] != '0000':
            continue
        word = int(message['words'][1], 16)
        index, value = word >> 8, word & 255
        if index == 0:
            menu = []
        if index != len(menu):
            menu = []
            continue
        menu.append(value)
        if value == 0 and index:
            menus.append(dict(epoch=message['epoch'], indexed_bytes_hex=bytes(menu).hex(' '),
                              observed_by=message['observed_between'][1]))
            menu = []
    return dict(exact_events_complete=not warnings, warnings=warnings,
                timing='host observation bounds, not exact DSP emission times',
                messages=messages, host_commands=hosts, orphan_words=orphans,
                received_v8_menus=menus)


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trace', type=Path, help='codec-mailbox.jsonl')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--clock-reference', type=Path, help='parent clock-reference.json')
    parser.add_argument('--rtp-start', type=float, help='epoch timestamp of selected RTP stream first packet')
    args = parser.parse_args()
    report = summarize(json.loads(line) for line in args.trace.read_text().splitlines())
    if args.rtp_start is not None:
        import math
        if args.clock_reference is None or not math.isfinite(args.rtp_start):
            parser.error('--rtp-start requires --clock-reference and a finite timestamp')
        anchors = json.loads(args.clock_reference.read_text())
        offsets = [(a['epoch_ns']-a['monotonic_ns'])/1e9 for a in anchors.values()]
        uncertainty = max(a['uncertainty_ns'] for a in anchors.values())/1e9
        report['clock_model'] = dict(method='endpoint clock-offset bounds; assumes no hidden clock step',
                                    anchor_offset_change_ms=1000*(max(offsets)-min(offsets)),
                                    anchor_uncertainty_s=uncertainty, rtp_start=args.rtp_start)
        for row in report['messages']:
            bounds = row['observed_between']
            if bounds is not None:
                row['rtp_observed_between'] = [bounds[0]+min(offsets)-uncertainty-args.rtp_start,
                                               bounds[1]+max(offsets)+uncertainty-args.rtp_start]
        for row in report['host_commands']:
            row['rtp_observed_between'] = [row['observed']+min(offsets)-uncertainty-args.rtp_start,
                                           row['observed']+max(offsets)+uncertainty-args.rtp_start]
    text = json.dumps(report, indent=2)+'\n'
    if args.output:
        with args.output.open('x') as stream:
            stream.write(text)
    else:
        print(text, end='')
    return 0 if report['exact_events_complete'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
