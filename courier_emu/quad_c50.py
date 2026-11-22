"""The Quad's CPU-side link to its C51 datapumps.

The supervisor at `0xcec04` resets the DSP, sends a command word, and streams a
program image to it. Decoded from QF060003:

* Eight 16-bit lanes at ports `0xc0, 0xc4, ... 0xdc`, each split low byte at the
  port and high byte at the port + 2. `0xcec3f` initialises all eight with
  `0x0083`; the transfer loops use four at a time.
* `[0x9d38]` selects the lane group - `0xc0` for the path at `0xced05`, `0xd0`
  for the one at `0xced12` - and `[0x9d37]` is that group's strobe value, 1 or 2.
* After each four-word burst the CPU writes the strobe to `0x98` and spins at
  `0xced9e` until `test [0x9d37], al` on a read of `0x98` is non-zero.
* The final word comes from `[0x9d3a]`, strobed with 4 and acknowledged on bit 2
  at `0xcee12`.
* `0xcec72` writes `0xffff` to `0x98`/`0x9a` and `0x9c`/`0x9e` and then polls
  both pairs until they read `0xffff` back, which is the reset presence check.

`QuadC50Link` remains the passive decoder for saved I/O logs.
`QuadC50Endpoint` is the active device: it boots the CPU-streamed resident on a
native C51, acknowledges `0x98` bursts only after that core consumes them, and
implements the distinct runtime-overlay protocol on `0x9e`. It also exposes
the card's byte-wide 8 kHz digital timeslot without converting its G.711
codewords.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Eight lanes, four ports apart, low byte at the port and high byte at +2.
LANE_BASE = 0xC0
LANE_COUNT = 8
LANE_STRIDE = 4
LANE_PORTS = tuple(LANE_BASE + LANE_STRIDE * index for index in range(LANE_COUNT))

# Status and strobe. 0x98 carries the per-group ready bits the transfer loop
# waits on; the reset check reads 0x98/0x9a and 0x9c/0x9e as word pairs.
STATUS_PORT = 0x98
STATUS_PORTS = (0x98, 0x9A, 0x9C, 0x9E)
RUNTIME_STATUS_PORT = 0x9E


@dataclass
class QuadC50Transfer:
    """One strobed burst: the lane group and the words the CPU placed in it."""

    strobe: int
    words: tuple[int, ...]


@dataclass
class QuadC50Link:
    lanes: dict[int, int] = field(default_factory=dict)
    transfers: list[QuadC50Transfer] = field(default_factory=list)
    words: list[int] = field(default_factory=list)
    strobes: dict[int, int] = field(default_factory=dict)
    status_writes: list[int] = field(default_factory=list)
    resets: int = 0
    max_transfers: int = 200_000

    @classmethod
    def from_io_events(cls, events) -> "QuadC50Link":
        """Reassemble the stream from a completed run's recorded port writes."""
        link = cls()
        for event in events:
            if event.direction == "out":
                link.write(event.port, event.size, event.value)
        return link

    def write(self, port: int, size: int, value: int) -> bool:
        if port in self.lanes_low:
            self.lanes[port] = (self.lanes.get(port, 0) & 0xFF00) | (value & 0xFF)
            return False
        if port in self.lanes_high:
            base = port - 2
            self.lanes[base] = (self.lanes.get(base, 0) & 0x00FF) | ((value & 0xFF) << 8)
            return False
        if port == STATUS_PORT:
            self._strobe(value & 0xFF)
            return False
        if port in STATUS_PORTS:
            self.status_writes.append(value & 0xFFFF)
            return False
        return False

    @property
    def lanes_low(self) -> tuple[int, ...]:
        return LANE_PORTS

    @property
    def lanes_high(self) -> tuple[int, ...]:
        return tuple(port + 2 for port in LANE_PORTS)

    def _strobe(self, value: int) -> None:
        self.strobes[value] = self.strobes.get(value, 0) + 1
        if value == 0xFF:
            # 0xcec97's presence write, not a burst.
            self.resets += 1
            self.lanes.clear()
            return
        group = LANE_BASE if value & 1 else (LANE_BASE + 0x10 if value & 2 else None)
        if group is None:
            return
        ports = [group + LANE_STRIDE * index for index in range(4)]
        words = tuple(self.lanes.get(port, 0) for port in ports)
        if len(self.transfers) < self.max_transfers:
            self.transfers.append(QuadC50Transfer(value, words))
            self.words.extend(words)
        for port in ports:
            self.lanes.pop(port, None)

    def status(self) -> dict[str, object]:
        return {
            "transfers": len(self.transfers),
            "words": len(self.words),
            "strobes": dict(sorted(self.strobes.items())),
            "resets": self.resets,
            "status_writes": len(self.status_writes),
        }

    def image(self) -> bytes:
        """The streamed words, little-endian, in the order the CPU sent them."""
        return b"".join(word.to_bytes(2, "little") for word in self.words)


# The DSP-side host link. `docs/quad-c50-overlay-loader.md` identifies MMR 0x57
# as the status/request register the resident's fetch stub polls and 0x58 as the
# word-fetch port it pulls program words through.
DSP_STATUS_MMR = 0x57
DSP_FETCH_MMR = 0x58
# The stub at 0x23f1 is one `lamm *` with ar1 auto-incrementing, so it walks a
# five-word window from 0x57: the status word and four data words. Four is the
# CPU's burst size, and the lanes correspond one for one - 0xc0 to 0x58, 0xc4 to
# 0x59, 0xc8 to 0x5a, 0xcc to 0x5b.
DSP_WINDOW = (0x58, 0x59, 0x5A, 0x5B)

# The resident's origin, from the load table: source paragraph 0x2000, length
# 0xf450, destination 0x8000. The captured stream spans 0x8000..0xfa28.
RESIDENT_ORIGIN = 0x8000
RESIDENT_WORDS = 0xF450 // 2

# 0xcec3f writes 0x0083 into all eight lanes and strobes both groups, so every
# load begins with eight of these before the image itself.
LANE_INIT_WORDS = 8
LANE_INIT_VALUE = 0x0083

# The recovered on-chip mask ROM, shared with the 302/403 path in bridge.py.
from .bridge import C50_ROM_FRAME_IRQ as ROM_FRAME_IRQ  # noqa: E402

ROM_SHA256 = "d57bc46e1bcd6d4dc8872b97bba2d98ba8fb6b8661440c566b534f0b3f82fac9"

# The C50 is clocked from the same 40.32 MHz can through the same ASIC as the
# 302/403's C52, so it advances against the 80186 exactly as bridge.py derives
# it, and its DS0 period is counted in that clock. Both are reused rather than
# restated so the two boards cannot drift apart. Inferred, not measured.
from .bridge import DSP_CYCLES_PER_X86  # noqa: E402
from .timebase import ASIC_DSP_CLOCK_HZ  # noqa: E402


@dataclass
class QuadC50Endpoint:
    """An active link: the CPU's lanes feed a C5x core that answers on 0x98.

    The CPU strobes four-word bursts and spins until the strobed bit reads back
    on `0x98` (`0xced9e`). Here that bit is raised only once the DSP has pulled
    the queued words through its fetch port, so the CPU waits on the DSP rather
    than on a floating bus.

    The core is stepped on an instruction budget alongside the CPU, carrying the
    fractional remainder between batches the way `bridge.py` does, so the average
    ratio stays exact instead of truncating once per service call.
    """

    core: object | None = None
    lanes: dict[int, int] = field(default_factory=dict)
    window: tuple[int, ...] | None = None
    window_group: int | None = None
    acks: int = 0
    reboots: int = 0
    program: list[int] = field(default_factory=list)
    steps: int = 0
    cycles: int = 0
    pulls: int = 0
    bursts: int = 0
    resets: int = 0
    started: bool = False
    _debt: float = 0.0
    _in_reset: bool = True
    _completion: bool = False
    _event_cursor: int = 0
    resets_seen: int = 0
    digital_call: bool = False
    media_peer: object | None = None
    _media_started: bool = False
    _tx_cursor: int = 0
    g711_idle: int = 0xff
    _g711_rx: bytearray = field(default_factory=bytearray)
    _boot_pending: bool = False
    _pcm_active: bool = False
    runtime_active: bool = False
    runtime_bursts: int = 0
    runtime_acks: int = 0
    _runtime_waiting: bool = False
    _overlay_ready: bool = False
    _window_read_mask: int = 0
    _cpu_status: int = 0
    _reply: dict[int, int] = field(default_factory=dict)
    _xf_cursor: int = 0
    irq_pending: bool = False
    commands_sent: int = 0
    commands_acked: int = 0
    replies_posted: int = 0
    replies_acked: int = 0
    exchanges: list[dict[str, object]] = field(default_factory=list)
    trace_data_lanes: bool = False
    data_lane_events: list[dict[str, int | str]] = field(default_factory=list)
    data_lane_limit: int = 4096
    service_slice_cycles: int = 64
    data_words_sent: int = 0
    data_words_received: int = 0

    def __post_init__(self):
        if self.service_slice_cycles <= 0:
            raise ValueError("DSP service slice must be positive")

    def _record_data_lane(self, direction: str, bank: int, word: int) -> None:
        if direction == "cpu-to-dsp":
            self.data_words_sent += 1
        else:
            self.data_words_received += 1
        if self.trace_data_lanes and len(self.data_lane_events) < self.data_lane_limit:
            self.data_lane_events.append({"direction": direction, "bank": bank,
                                         "word": word, "cycles": self.cycles})

    # -- CPU side ---------------------------------------------------------
    def _lanes_live(self) -> bool:
        return (self.core is not None and not self._in_reset
                and not self._boot_pending and self._completion)

    def read(self, port: int, size: int) -> int | None:
        # Six bidirectional data banks share the boot download latches, just
        # as on the analog ASIC. PA6 low bits are host-to-DSP pending; its
        # upper bits are DSP-to-host FREE. Ports 98/9a expose their inverse.
        if self._lanes_live() and size == 1:
            if port in (0x98, 0x9a):
                status = self.core.io(0x56)
                if port == 0x9a:
                    status >>= 8
                return 0xc0 | (~status & 0x3f)
            if 0xc0 <= port <= 0xd6 and port % 4 in (0, 2):
                bank = (port - 0xc0) // 4
                word = self.core.io_output(0x58 + bank)
                if not port & 2 and not self.core.io(0x56) & (0x100 << bank):
                    self._record_data_lane("dsp-to-cpu", bank, word)
                return (word >> (8 if port & 2 else 0)) & 0xff
        # Runtime reads see DSP reply latches, independent of CPU writes.
        if port in (0xD8, 0xDA, 0xDC, 0xDE) and not self._in_reset:
            word = self._reply.get(0x5E if port < 0xDC else 0x5F, 0)
            return (word >> (8 if port & 2 else 0)) & 0xFF
        if port == 0x9C and not self._in_reset:
            return self._cpu_status
        if port == RUNTIME_STATUS_PORT and not self._in_reset and self.runtime_active:
            # The overlay loader first waits for bit 2 after writing 4, then
            # waits for bit 1 after every four-word burst.  Keep bit 2 raised
            # as the link-present indication while the burst acknowledgement
            # follows the resident's actual 0x57 write.
            return (0x04 | (0x00 if self._runtime_waiting else 0x02)
                    if self._overlay_ready else 0)
        if port == STATUS_PORT:
            if self._in_reset:
                # 0xcec72 writes 0xffff to 0x98/0x9a and 0x9c/0x9e and polls
                # both pairs back; the all-ones signature is the presence check.
                return 0xFF
            return self._ready_bits()
        if port in STATUS_PORTS and self._in_reset:
            return 0xFF
        if port in (0x9A, 0x9E):
            return 0
        return None

    def write(self, port: int, size: int, value: int) -> bool:
        if (self._lanes_live() and size == 1 and port in (0x98, 0x9a)
                and not (port == 0x98 and value & 0xff == 0xff)):
            bits = value & 0x3f
            if port == 0x98:
                for bank in range(6):
                    if bits & (1 << bank):
                        word = self.lanes.get(0xc0 + 4 * bank, 0)
                        self.core.set_io(0x58 + bank, word)
                        self._record_data_lane("cpu-to-dsp", bank, word)
            else:
                bits <<= 8
            self.core.set_io(0x56, self.core.io(0x56) | bits)
            return False
        if port in LANE_PORTS:
            self.lanes[port] = (self.lanes.get(port, 0) & 0xFF00) | (value & 0xFF)
            return False
        if port - 2 in LANE_PORTS:
            base = port - 2
            self.lanes[base] = (self.lanes.get(base, 0) & 0x00FF) | ((value & 0xFF) << 8)
            return False
        if port == STATUS_PORT:
            self._strobe(value & 0xFF)
            return False
        if port == 0x9C and not self._in_reset and self.core is not None:
            # QF cfe92 hands off a command with bit 0 and releases the reply
            # slot with bit 1. The DSP acknowledges these at 86b9 / 8704.
            value &= 3
            if value & 1 and self._cpu_status & 1:
                self.core.set_io(0x5E, self.lanes.get(0xD8, 0))
                self.core.set_io(0x5F, self.lanes.get(0xDC, 0))
                if self.lanes.get(0xD8, 0) == 2:
                    # The CPU must wait for the DSP's download-arm ack before
                    # exposing the first burst, not just for a present link.
                    self._overlay_ready = False
                self.commands_sent += 1
                if len(self.exchanges) < 256:
                    self.exchanges.append({"direction": "cpu-to-dsp", "steps": self.steps,
                        "command": self.lanes.get(0xD8, 0), "argument": self.lanes.get(0xDC, 0)})
            if value & 2 and self._cpu_status & 2:
                self.replies_acked += 1
            self._cpu_status &= ~value
            self.core.set_io(0x57, self.core.io(0x57) | value)
            return False
        if port == RUNTIME_STATUS_PORT and not self._in_reset:
            self._runtime_strobe(value & 0xFF)
            return False
        return False

    def _runtime_strobe(self, value: int) -> None:
        """Handle the overlay stream emitted by the CPU routine at 0xcee5f."""
        if value == 4:
            # ceede starts the transaction BEFORE queuing command 2. An arm
            # acknowledgement from an earlier reset/overlay is not readiness
            # for this transfer; wait for its new 0700 DSP acknowledgement.
            self.runtime_active = True
            self._overlay_ready = False
            self._runtime_waiting = False
            return
        if value != 2 or not self.runtime_active or self.core is None:
            return
        # Runtime overlays always use the first four lanes.  The CPU does not
        # issue the 0x98 boot-loader group strobe for these words.
        self.runtime_bursts += 1
        self.bursts += 1
        self.window = tuple(
            self.lanes.pop(LANE_BASE + LANE_STRIDE * index, 0)
            for index in range(4)
        )
        self.window_group = LANE_BASE
        self._runtime_waiting = True
        self._window_read_mask = 0
        self.core.set_io(DSP_STATUS_MMR, self.core.io(DSP_STATUS_MMR) | 0x0200)

    def _strobe(self, value: int) -> None:
        if value == 0xFF:
            self.resets += 1
            self._in_reset = True
            self._completion = False
            self.lanes.clear()
            self.window = None
            self.window_group = None
            # 0xcec38 and 0xcec12 both reset the part before the stream, and the
            # CPU repeats the whole load each time. On the board that reset puts
            # the C51 back in its boot ROM, so the loader is there to receive the
            # image again. Keeping one running core across resets left every
            # load after the first with nothing to receive it: the resident is
            # past its boot-time pulls by then and goes quiescent, which is
            # exactly the silence the CPU was timing out on.
            if self.core is not None:
                self.core.close()
                self.core = None
                self.started = False
                self.reboots += 1
            self.program = []
            self._boot_pending = False
            self._pcm_active = False
            self._tx_cursor = 0
            self._event_cursor = 0
            self._xf_cursor = 0
            self.irq_pending = False
            self._cpu_status = 0
            self._reply.clear()
            self.runtime_active = False
            self._runtime_waiting = False
            self._overlay_ready = False
            self._window_read_mask = 0
            return
        self._in_reset = False
        if value == 4:
            # The completion strobe is answered on bit 2 at 0xcee12 in both
            # phases; letting it fall through to the collector, which only
            # knows the two group strobes, times every load out.
            self._completion = True
            return
        if self.core is None:
            # Phase one: the C51's own boot loader pulls the resident in before
            # any of its code is running. That boot path is not modelled, so the
            # stream is taken at wire speed and the burst acked immediately. The
            # image still comes from the CPU - nothing here supplies it.
            self._collect(value)
            return
        group = LANE_BASE if value & 1 else (LANE_BASE + 0x10 if value & 2 else None)
        if group is None:
            return
        self.bursts += 1
        self.window = tuple(self.lanes.pop(group + LANE_STRIDE * i, 0) for i in range(4))
        self.window_group = group
        self._window_read_mask = 0

    def _collect(self, value: int) -> None:
        group = LANE_BASE if value & 1 else (LANE_BASE + 0x10 if value & 2 else None)
        if group is None:
            return
        self.bursts += 1
        for index in range(4):
            self.program.append(self.lanes.pop(group + LANE_STRIDE * index, 0))
        # 0xcec3f primes all eight lanes with 0x0083, but 0xcec12's second call
        # to the reset routine lands between that and the stream, so what
        # accumulates after the last reset is the image alone. Counting the init
        # words in shifts the image and the DSP executes from the wrong place.
        if len(self.program) >= RESIDENT_WORDS and not self.started:
            self._start_core()

    def _start_core(self) -> None:
        """Boot the DSP the way bridge.py already boots it on the 302/403.

        Same part - board-parts.md records it as a 'C51, measured rather than
        read off a marking (superseded 2026-09-13; the earlier TMS320C50/LC50
        identification here was wrong) - so the boot path is the same one that
        works there: the recovered mask ROM, MP/MC low, a *zeroed* program
        space, and the loader fed its destination, length and words. The
        loader writes the resident; nothing here pre-loads a copy for it to
        execute, which is the mistake bridge.py's own comment warns about and
        the one this endpoint was making.
        """
        from hashlib import sha256
        from pathlib import Path

        from .dsp import NativeC5x

        rom = (Path(__file__).resolve().parent.parent /
               "dumps/dsp-onchip-rom-20mhz-8k/c5x-onchip-rom-8k.bin").read_bytes()
        if sha256(rom).hexdigest() != ROM_SHA256:
            raise ValueError("recovered DSP boot ROM checksum mismatch")
        words = self.program[:RESIDENT_WORDS]
        core = NativeC5x.from_program(RESIDENT_ORIGIN, bytes(RESIDENT_WORDS * 2))
        core.configure_host_mailbox()
        if self.trace_data_lanes:
            # Keep a bounded trace of the V.42 accumulator and control cells;
            # these are reads as well as writes, so the native fixed watch set
            # is used rather than a write-only address filter.
            core.trace_data_writes(True)
            core.set_data_event_limit(200_000)
        core.set_io(0x57, 0)
        core.load_rom(rom)
        core.set_mpmc_pin(0)
        # The boot strap the ROM reads to pick its mode. Not codec-specific -
        # without it the ROM takes another path and runs into an invalid opcode
        # at program 0x3f.
        core.host_write(0xFFFF, 4)
        core.set_pc(0)
        # Use mailbox acknowledgements without enabling the analog AC01 clock.
        # Treating writes to 0x57 as ordinary storage fabricated overlay bit 9
        # during resident initialization and consumed nonexistent boot words.
        # DRR still carries the ROM download, with XRDY following XRST, until
        # the separate digital timeslot is activated after handoff.
        core.queue_codec_rx([RESIDENT_ORIGIN, len(words), *words, 0])
        self.core = core
        # DRR first carries the ROM's 16-bit download, not DS0 octets. Frame
        # interrupts during this phase can run before resident vectors exist.
        self._boot_pending = True
        self._pcm_active = False
        self._event_cursor = 0
        self.started = True
        self.program = []

    def connect_digital_call(self, *, law: str = "mu") -> None:
        """Attach one clear 64 kbit/s DS0 to this datapump.

        G.711 bytes remain opaque on the wire. ``law`` only chooses the idle
        codeword used when the receive side has no queued traffic.
        """
        if law not in ("mu", "a"):
            raise ValueError("G.711 law must be 'mu' or 'a'")
        self.digital_call = True
        self.g711_idle = 0xff if law == "mu" else 0xd5
        if self.core is not None and not self._boot_pending:
            self._activate_pcm()

    def _activate_pcm(self) -> None:
        if self.digital_call and not self._pcm_active:
            if self.media_peer is not None and not self._media_started:
                self.media_peer.start()
                self._media_started = True
            if self.media_peer is not None:
                # A framed synchronous peer exchanges complete wire blocks.
                # The physical highway is idle during its initial transit
                # reserve, not an empty receive FIFO.
                self._g711_rx.extend(bytes((self.g711_idle,)) *
                                     getattr(self.media_peer, "frame_octets", 800))
            self.core.configure_digital_pcm(
                idle_codeword=self.g711_idle, clock_hz=ASIC_DSP_CLOCK_HZ)
            self.core.configure_line_frame_interrupt(ROM_FRAME_IRQ, 0xFFFF)
            self._pcm_active = True
            if self._g711_rx:
                self.core.queue_g711_rx(bytes(self._g711_rx))
                self._g711_rx.clear()

    def receive_g711(self, codewords: bytes) -> None:
        """Deliver 8-bit G.711 codewords to the DSP receive timeslot."""
        if not self.digital_call:
            raise RuntimeError("no digital call is connected")
        if self.core is None or not self._pcm_active:
            self._g711_rx.extend(codewords)
        else:
            self.core.queue_g711_rx(codewords)

    def transmit_g711(self, start: int = 0) -> bytes:
        """Return codewords clocked from the DSP transmit register."""
        return b"" if self.core is None else self.core.g711_tx(start)

    def _ready_bits(self) -> int:
        if self.core is None:
            # Phase one still has to answer the completion strobe on bit 2, or
            # the wait at 0xcee34 times out and the load is retried for ever.
            return 0x01 | 0x02 | (0x04 if self._completion else 0)
        # The strobed group's bit is raised only once the DSP has acknowledged
        # the window by writing 0x57, which is what it does at 0x8313 after
        # reading all five words.
        if self.window is not None:
            return 0
        return 0x01 | 0x02 | (0x04 if self._completion else 0)

    # -- DSP side ---------------------------------------------------------
    def service(self, cpu_instructions: int) -> None:
        """Advance the C5x by its share of `cpu_instructions`."""
        if self.core is None:
            return
        self._debt += cpu_instructions * DSP_CYCLES_PER_X86
        while self._debt >= 1:
            # All four words are present at once, so the stub's consecutive
            # reads see a coherent window and the core need not be single
            # stepped for it.
            if self.window is not None:
                for port, word in zip(DSP_WINDOW, self.window, strict=True):
                    self.core.set_io(port, word)
            # Charge actual C51 cycles, including multi-cycle instructions
            # and delay slots, as on the analogue and I-modem endpoints.
            # Keep boot/download window pacing unchanged. Larger optional
            # runtime slices reduce Python/native crossings; advance_imodem
            # still yields at every PCM sample before another can be consumed.
            budget = 64 if self._boot_pending or self.window is not None else self.service_slice_cycles
            slice_size = min(int(self._debt), budget)
            octets = b""
            if self._pcm_active and self.media_peer is not None:
                # Reuse the I-modem's yield-on-frame primitive. Refill before
                # another serial frame, not after an entire CPU service batch.
                ran, elapsed, _, _, _, _, octets = self.core.advance_imodem(
                    slice_size, self._tx_cursor)
            else:
                ran, elapsed = self.core.step_cycles(slice_size)
            self._debt -= elapsed
            self.steps += ran
            self.cycles += elapsed
            if (self._boot_pending
                    and self.core.codec_state()["codec_rx_size"] == 0
                    and self.core.state()["pc"] >= RESIDENT_ORIGIN):
                self._boot_pending = False
                self._cpu_status = 1
                self.core.set_io(0x57, self.core.io(0x57) | 2)
                self._activate_pcm()
            self._drain_pulls()
            edges = self.core.xf_falling_edges()
            if edges > self._xf_cursor:
                self.irq_pending = True
            self._xf_cursor = edges
            if octets:
                self._tx_cursor += len(octets)
                incoming = self.media_peer.exchange(octets)
                if incoming:
                    self.receive_g711(incoming)

    def _drain_pulls(self) -> None:
        library = self.core.library
        handle = self.core.handle
        count = int(library.courier_c5x_get_io_event_count(handle))
        total = self.core.io_event_total()
        if total < self._event_cursor:
            # A native reset restarts the sequence, unlike ring eviction.
            self._event_cursor = 0
            self.resets_seen += 1
        available = total - self._event_cursor
        if available > count:
            raise RuntimeError(f"Quad DSP I/O drain overrun; handshake history lost "
                               f"({available} new events, {count} retained, "
                               f"DSP pc={self.core.state()['pc']:04x})")
        import ctypes as _ctypes
        values = (_ctypes.c_uint64 * 5)()
        for index in range(count - available, count):
            library.courier_c5x_get_io_event(handle, index, values, 5)
            write, port = int(values[0]), int(values[1])
            value = int(values[2])
            if write and port in (0x5E, 0x5F):
                self._reply[port] = value
            if write and port == DSP_STATUS_MMR and not self._boot_pending:
                if value == 1:
                    self.commands_acked += 1
                    self._cpu_status |= 1
                elif value == 2:
                    self.replies_posted += 1
                    self._cpu_status |= 2
                    if len(self.exchanges) < 256:
                        self.exchanges.append({"direction": "dsp-to-cpu", "steps": self.steps,
                            "command": self._reply.get(0x5E, 0), "argument": self._reply.get(0x5F, 0)})
            if not write and self.window is not None and port in DSP_WINDOW:
                self._window_read_mask |= 1 << DSP_WINDOW.index(port)
            if (write and port == DSP_STATUS_MMR and value != 0xffff
                    and value & 0x0400):
                self._overlay_ready = True
            if not write and port == DSP_FETCH_MMR:
                self.pulls += 1
            elif (write and port == DSP_STATUS_MMR and value != 0xffff
                  and value & 0x0200 and self.window is not None
                  and self._window_read_mask == 0xf):
                # 0x8313's write is the acknowledge: the window has been taken.
                self.program.extend(self.window)
                self.window = None
                self.window_group = None
                self.acks += 1
                if self._runtime_waiting:
                    self._runtime_waiting = False
                    self.runtime_acks += 1
        self._event_cursor = total

    def status(self) -> dict[str, object]:
        return {
            "steps": self.steps, "cycles": self.cycles,
            "pulls": self.pulls, "bursts": self.bursts,
            "resets": self.resets, "acks": self.acks,
            "core_log_resets": self.resets_seen, "reboots": self.reboots,
            "window_open": self.window is not None,
            "program_words": len(self.program), "completion": self._completion,
            "digital_call": self.digital_call,
            "boot_pending": self._boot_pending, "pcm_active": self._pcm_active,
            "g711_tx": 0 if self.core is None else len(self.core.g711_tx()),
            "runtime_active": self.runtime_active,
            "overlay_ready": self._overlay_ready,
            "window_read_mask": self._window_read_mask,
            "data_words_sent": self.data_words_sent,
            "data_words_received": self.data_words_received,
            "runtime_bursts": self.runtime_bursts,
            "runtime_acks": self.runtime_acks,
            "commands_sent": self.commands_sent, "commands_acked": self.commands_acked,
            "replies_posted": self.replies_posted, "replies_acked": self.replies_acked,
            "xf_edges": self._xf_cursor,
            "media_peer": self.media_peer.status() if self.media_peer is not None else None,
            "service_slice_cycles": self.service_slice_cycles,
            "pcm_rx_underruns": self.core.g711_rx_underruns() if self._pcm_active else 0,
            "exchanges": list(self.exchanges),
        }
