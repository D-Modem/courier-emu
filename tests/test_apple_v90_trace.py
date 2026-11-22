import json
import struct

from courier_emu.dsp import NativeC5x
from tools.apple_v90_trace import ADDRESSES, ENTRY, FINGERPRINTS, V90MailboxRecorder


def recorder(tmp_path):
    return V90MailboxRecorder(tmp_path/'codec', count=lambda c: 0,
                              events=lambda *args: iter(()), snapshots=0)


def saved(tmp_path):
    return [json.loads(line) for line in (tmp_path/'codec-v90.jsonl').read_text().splitlines()]


class Core:
    handle = 1

    def __init__(self):
        self.program_words = {}
        self.records = []
        self.selections = []

    def load_signature(self):
        for address, words in FINGERPRINTS.items():
            self.program_words.update({address+i: w for i, w in enumerate(words)})

    def program(self, address):
        return self.program_words.get(address, 0)

    def set_pc_capture(self, pc, addresses):
        self.selections.append((pc, addresses))
        self.records.clear()

    def pc_captures(self):
        return self.records[:]

    def clear_pc_captures(self):
        self.records.clear()


def row():
    return [100, 120, 0xffffffff, 6, 1] + list(range(len(ADDRESSES)))


def test_does_not_arm_on_unverified_or_partially_matching_program(tmp_path):
    r = recorder(tmp_path)
    c = Core()
    r.collect(c)
    c.load_signature()
    c.program_words[0x8dcf] ^= 1
    r.collect(c)
    assert c.selections == []
    assert not any(e['kind'] == 'armed' for e in saved(tmp_path))
    r.close()


def test_drains_rare_entry_once_and_rearms_after_observed_reset(tmp_path):
    r = recorder(tmp_path)
    c = Core()
    c.load_signature()
    r.collect(c)
    c.records.append(row())
    r.boundary(c, 'before-reset')
    r.reset_done(c)
    r.collect(c)
    r.collect(c)
    entries = [e for e in saved(tmp_path) if e['kind'] == 'entry']
    assert len(entries) == 1
    assert entries[0]['ram']['031a'] == ADDRESSES.index(0x031a)
    assert entries[0]['acc'] == 0xffffffff
    assert entries[0]['reason'] == 'before-reset'
    assert len(c.selections) == 2
    r.close()


def test_changed_program_disarms_and_does_not_publish_unverified_records(tmp_path):
    r = recorder(tmp_path)
    c = Core()
    c.load_signature()
    r.collect(c)
    c.records.append(row())
    c.program_words[ENTRY] ^= 1
    r.collect(c)
    rows = saved(tmp_path)
    assert not any(e['kind'] == 'entry' for e in rows)
    loss, = [e for e in rows if e['kind'] == 'loss']
    assert loss['discarded_records'] == 1
    assert c.selections[-1] == (0, [])
    r.close()


def test_full_ring_and_exhausted_budget_are_reported_not_silently_complete(tmp_path):
    r = recorder(tmp_path)
    c = Core()
    c.load_signature()
    r.collect(c)
    for _ in range(3):
        c.records.extend([row() for _ in range(64)])
        r.collect(c)
    rows = saved(tmp_path)
    assert len([e for e in rows if e['kind'] == 'entry']) == 128
    reasons = [e['reason'] for e in rows if e['kind'] == 'loss']
    assert 'possible native PC ring eviction' in reasons
    assert 'probe recording budget exhausted' in reasons
    assert c.selections[-1] == (0, [])
    r.close()


def test_native_direct_timeout_route_cannot_bypass_sender_probe(tmp_path):
    origin = min(FINGERPRINTS)
    end = max(a+len(signature) for a, signature in FINGERPRINTS.items())
    words = [0xbe22] * (end-origin)
    for address, signature in FINGERPRINTS.items():
        words[address-origin:address-origin+len(signature)] = signature
    # LDP #6; LACC #-5; CALL 8dcf at 8d9a; IDLE. Never execute 8d5b.
    words[0x8d97-origin:0x8d9d-origin] = [0xbc06, 0xbf80, 0xfffb, 0x7a80, 0x8dcf, 0xbe22]
    image = struct.pack(f'<{len(words)}H', *words)
    r = recorder(tmp_path)
    with NativeC5x.from_program(origin, image) as core:
        core.set_data(0x031a, 0xfffb)
        core.set_pc(0x8d97)
        r.collect(core)
        core.step(4)
        r.collect(core)
        entry, = [e for e in saved(tmp_path) if e['kind'] == 'entry']
        assert entry['acc'] == 0xfffffffb
        assert entry['dp'] == 6
        assert entry['ram']['031a'] == 0xfffb
    r.close()


def test_native_probe_captures_exact_pre_instruction_data_without_guest_changes(tmp_path):
    origin = min(FINGERPRINTS)
    end = max(a+len(signature) for a, signature in FINGERPRINTS.items())
    words = [0xbe22] * (end-origin)
    for address, signature in FINGERPRINTS.items():
        words[address-origin:address-origin+len(signature)] = signature
    image = struct.pack(f'<{len(words)}H', *words)
    r = recorder(tmp_path)
    with NativeC5x.from_program(origin, image) as probed, NativeC5x.from_program(origin, image) as plain:
        for core in (probed, plain):
            core.set_data(0x031a, 0xffff)
            core.set_data(0x0337, 7)
            core.set_pc(ENTRY)
        before = plain.state()
        r.collect(probed)
        probed.step(1)
        plain.step(1)
        assert probed.state() == plain.state()
        assert [probed.data(a) for a in ADDRESSES] == [plain.data(a) for a in ADDRESSES]
        r.collect(probed)
        entry, = [e for e in saved(tmp_path) if e['kind'] == 'entry']
        assert entry['ram']['031a'] == 0xffff
        assert entry['ram']['0337'] == 7
        assert entry['dp'] == before['dp']
    r.close()
