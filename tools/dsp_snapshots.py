"""Read-only, media-frame-triggered DSP snapshots for paired-call diagnosis."""
import json
from pathlib import Path
import struct


class DspSnapshots:
    def __init__(self, directory, frames, read_range=None):
        self.directory = Path(directory)
        self.targets = sorted(set(frames))
        if any(frame < 0 for frame in self.targets):
            raise ValueError("snapshot frames must be nonnegative")
        if read_range is not None:
            if len(read_range) != 2 or not 0 <= read_range[0] <= read_range[1] <= 0xffff:
                raise ValueError("snapshot read range must be two ordered 16-bit addresses")
            if len(self.targets) < 2:
                raise ValueError("snapshot read tracing requires at least two snapshot frames")
        self.records = []
        self.read_range = read_range
        self.tracing_core = None

    def poll(self, core, frame, instructions):
        if core is None:
            return
        if self.targets and frame >= self.targets[0] and self.read_range and self.tracing_core is not core:
            core.set_data_trace_range(*self.read_range)
            core.trace_filtered_reads()
            core.set_data_event_limit(1_000_000)
            core.trace_data_writes()
            self.tracing_core = core
        while self.targets and frame >= self.targets[0]:
            requested = self.targets.pop(0)
            self.directory.mkdir(parents=True, exist_ok=True)
            for space in ("program", "data"):
                getter = getattr(core, space)
                (self.directory / f"frame-{requested:05d}-{space}.bin").write_bytes(
                    struct.pack("<65536H", *(getter(address) for address in range(65536))))
            self.records.append({"requested_frame": requested, "frame": frame,
                                 "cpu_instructions": instructions, "state": core.state(),
                                 "serial": core.serial_state(), "codec": core.codec_state(),
                                 "registers": {f"{a:02x}": core.register(a) for a in range(0x60)}})
            if self.read_range:
                (self.directory / "memory-events.json").write_text(json.dumps(core.data_events()) + "\n")
            (self.directory / "snapshots.json").write_text(json.dumps(self.records, indent=2) + "\n")
