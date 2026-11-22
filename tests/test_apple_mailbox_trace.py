import json
import struct
from pathlib import Path

import pytest

from tools.apple_mailbox_trace import MailboxRecorder, install, summarize


class Core:
    def __init__(self):
        self.handle = 1
        self.events = []
        self.actions = []

    def state(self):
        return {'pc': 0x8000, 'instructions': len(self.events)}

    def program(self, address):
        return address

    def data(self, address):
        return address ^ 0xffff

    def reset(self):
        self.actions.append('reset')
        self.events.clear()
        return 42

    def close(self):
        self.actions.append('close')
        self.handle = None


def event(port, value, instruction=1):
    return dict(port=port, value=value, pc=0x83eb, instruction=instruction)


def recorder(tmp_path, **kwargs):
    return MailboxRecorder(tmp_path/'codec', count=lambda c: len(c.events),
                           events=lambda c, a, b: c.events[a:b], **kwargs)


def rows(r):
    r.file.flush()
    return [json.loads(x) for x in Path(r.file.name).read_text().splitlines()]


def test_incremental_events_preserve_tag_word_order_and_do_not_duplicate(tmp_path):
    r = recorder(tmp_path)
    c = Core()
    c.events = [event(0x5e, 0x48), event(0x5f, 0xc1)]
    r.collect(c)
    c.events.extend([event(0x5e, 0x34), event(0x5f, 4)])
    r.collect(c)
    r.collect(c)
    assert [(e['port'], e['value']) for e in rows(r) if e['kind']=='io'] == [
        (0x5e, 0x48), (0x5f, 0xc1), (0x5e, 0x34), (0x5f, 4)]
    assert not c.actions
    r.close()


def test_reset_and_close_archive_before_destruction_and_separate_epochs(tmp_path):
    r = recorder(tmp_path)
    c = Core()
    c.events = [event(0x5e, 0x47), event(0x5f, 6)]
    restore = install(r, Core)
    try:
        assert c.reset() == 42
        c.events = [event(0x5e, 0x34), event(0x5f, 4)]
        c.close()
        saved = rows(r)
        assert [e['epoch'] for e in saved if e['kind']=='epoch'] == [1, 2]
        snapshots = [e for e in saved if e['kind']=='snapshot']
        assert [e['reason'] for e in snapshots] == ['before-reset', 'before-close']
        for snapshot in snapshots:
            files=snapshot['files']
            assert (tmp_path/files['program']['path']).read_bytes()[:4] == struct.pack('<HH', 0, 1)
            assert (tmp_path/files['data']['path']).read_bytes()[:4] == struct.pack('<HH', 0xffff, 0xfffe)
        assert c.actions == ['reset', 'close']
    finally:
        restore()
        r.close()


def test_capture_failure_never_prevents_real_close(tmp_path):
    r = recorder(tmp_path)
    c = Core()
    def broken(*args, **kwargs):
        raise OSError('disk full')
    r.boundary = broken
    restore = install(r, Core)
    try:
        c.close()
        assert not c.handle
        assert any(e['kind']=='error' and 'disk full' in e['error'] for e in rows(r))
    finally:
        restore()
        r.close()


def test_recording_and_ring_limits_are_explicit_not_silent_loss(tmp_path):
    r = recorder(tmp_path, batch_limit=1, final_limit=2, total_limit=2, ring_limit=3)
    c = Core()
    c.events = [event(0x5e, 0x47), event(0x5f, 6), event(0x5e, 0x34), event(0x5f, 4)]
    r.collect(c, final=True)
    saved = rows(r)
    assert len([e for e in saved if e['kind']=='io']) == 2
    assert {e['reason'] for e in saved if e['kind']=='loss'} == {
        'possible mailbox ring eviction', 'recording budget exhausted'}
    r.close()


def test_unobserved_reset_is_reported(tmp_path):
    r = recorder(tmp_path)
    c = Core()
    c.events = [event(0x5e, 8), event(0x5f, 2)]
    r.collect(c)
    c.events.clear()
    r.collect(c)
    assert any(e['kind']=='loss' for e in rows(r))
    r.close()


@pytest.mark.parametrize('limits', [dict(batch_limit=0), dict(final_limit=1),
                                   dict(total_limit=0), dict(snapshots=-1)])
def test_invalid_recording_budgets(tmp_path, limits):
    with pytest.raises(ValueError):
        recorder(tmp_path, **limits)


def test_summary_handles_cross_batch_payload_and_preserves_header_word(tmp_path):
    r = recorder(tmp_path)
    c = Core()
    c.events = [event(0x5e, 0x48), event(0x5f, 0)]
    r.collect(c)
    c.events.append(event(0x5f, 0xc1))
    r.collect(c)
    report = summarize(rows(r))
    assert report['exact_events_complete']
    assert report['messages'][0]['words'] == ['0000', '00c1']
    assert len(report['messages']) == 1
    r.close()


def test_summary_cannot_pair_a_word_with_previous_epoch_tag(tmp_path):
    r = recorder(tmp_path)
    c = Core()
    c.events = [event(0x5e, 0x48)]
    r.collect(c)
    r.reset_done(c)
    c.events = [event(0x5f, 0xc1)]
    r.collect(c)
    report = summarize(rows(r))
    assert report['messages'][0]['words'] == []
    assert len(report['orphan_words']) == 1
    r.close()


def test_empty_saved_trace_is_not_verified_complete():
    assert not summarize([])['exact_events_complete']


def test_summary_rejects_saved_missing_event(tmp_path):
    r = recorder(tmp_path)
    c = Core()
    c.events = [event(0x5e, 0x48), event(0x5f, 0)]
    r.collect(c)
    saved = rows(r)
    assert not summarize(saved[:-1])['exact_events_complete']
    r.close()
