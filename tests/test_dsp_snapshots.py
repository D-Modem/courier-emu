import json
import struct

import pytest

from tools.dsp_snapshots import DspSnapshots


@pytest.mark.parametrize('frames, read_range', [
    ([-1], None), ([1], (0xbd0, 0xbdf)),
    ([1, 2], (0xbdf, 0xbd0)), ([1, 2], (-1, 0xbdf)),
    ([1, 2], (0, 0x10000)), ([1, 2], (0, 1, 2)),
])
def test_snapshot_rejects_invalid_capture_requests(tmp_path, frames, read_range):
    with pytest.raises(ValueError):
        DspSnapshots(tmp_path, frames, read_range)


def test_snapshots_capture_mapped_words_and_live_registers_without_stepping(tmp_path):
    class Core:
        calls = []
        events = []

        def program(self, address):
            return address

        def data(self, address):
            return address ^ 0xffff

        def register(self, address):
            return address + 0x100

        def state(self):
            return {'pc': 0x8000}

        def serial_state(self):
            return {}

        def codec_state(self):
            return {'frame_period': 5040}

        def set_data_trace_range(self, *args):
            self.calls.append(args)

        def trace_filtered_reads(self):
            self.calls.append('reads')

        def set_data_event_limit(self, limit):
            self.calls.append(limit)

        def trace_data_writes(self):
            self.calls.append('writes')

        def data_events(self):
            return self.events

    core = Core()
    snapshots = DspSnapshots(tmp_path, [2, 1, 1], (0xbd0, 0xbdf))
    snapshots.poll(None, 1, 10)
    snapshots.poll(core, 0, 10)
    assert not core.calls
    snapshots.poll(core, 1, 20)
    core.events.append({'pc': 0x840d, 'address': 0xbd1, 'value': 0xff34, 'instruction': 42})
    snapshots.poll(core, 2, 30)
    snapshots.poll(core, 3, 40)
    assert core.calls == [(0xbd0, 0xbdf), 'reads', 1_000_000, 'writes']
    assert (tmp_path / 'frame-00001-program.bin').stat().st_size == 131072
    assert (tmp_path / 'frame-00001-data.bin').read_bytes()[:4] == struct.pack('<2H', 0xffff, 0xfffe)
    metadata = json.loads((tmp_path / 'snapshots.json').read_text())
    assert [entry['frame'] for entry in metadata] == [1, 2]
    assert metadata[1]['registers']['20'] == 0x120
    assert json.loads((tmp_path / 'memory-events.json').read_text()) == core.events
