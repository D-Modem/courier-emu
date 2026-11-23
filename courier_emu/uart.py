"""The 80C186EB serial port, as the board ROM drives it.

The update payload reaches its DTE through hand-modelled I/O ports; a ROM
boots from its reset vector and programs the integrated serial unit in the
relocated peripheral control block instead, so a ROM run needs the part:

    ff60  B0CMP   baud compare, written 0x8015 - enable plus divisor
    ff62  B0CNT   baud counter
    ff64  S0CON   control, written 0x21 - mode 1 with receive enabled
    ff66  S0STS   status, cleared by the read
    ff68  S0RBUF  receive buffer
    ff6a  S0TBUF  transmit buffer

Both directions are interrupt driven, and the live board's own vector table
says on which types: 0x14 enters `cld; pushaw; mov ax, [0xff68]; call [0x26a]`
at 0x80f23, and 0x15 enters the transmit side at 0x80f1c. Those are the
part's fixed serial types, so they are not configuration this has to recover.

Transmit is a plain store - `mov word ptr [0xff6a], ax` at 33 sites. A byte
is captured when the firmware writes it. With internal-clock asynchronous mode 1,
the ROM harness times the double-buffered transmitter from B0CMP: TI is latched
at the stop bit, and TXE waits for both slots to empty. Other clocking/modes
retain the legacy synchronous completion; this is not a complete wire encoder.

The format on the wire is the firmware's choice, not this module's. `S0CON`
is written `0x21` - mode 1, eight bits on the wire - and the firmware composes
each character to the DTE format its settings EEPROM holds:

* **With the 403's own EEPROM** (`--nvram-fixture idsdl403`, a captured part)
  the profile is `&B1`, `BAUD=115200 PARITY=N WORDLEN=8`: eight data bits, no
  parity. `&B1` locks the DTE rate, so nothing is autobauded. An `ATI4` from it
  carries no byte with bit 7 set, and matches both physical units' `ATI4`
  (`artifacts/leased-pair/`) in every setting that bears on framing.
* **With an erased or rejected EEPROM** the firmware falls back to
  `BAUD=9600 PARITY=E WORDLEN=7` (`artifacts/rom-at-smoke-20260906/403.txt`):
  seven bits of ASCII plus an even parity bit in bit 7. The 2806 capture booted
  that way - all 430 bytes of its `ATI7` match even parity - and output read
  raw then looks like high-bit garbage until masked to seven bits.

Raw-pin autobaud timing is still a gap. The byte-oriented console/pty attention
adapter now defaults to 8N1 and publishes that format to the identified active
firmware setting when it accepts AT, after profile loading. --dte-framing stored
leaves the firmware's format untouched; batch runs retain that default. This is
format completion at the existing byte adapter, not a silicon timing model.
The separate raw path feeds the first character bit by bit through the ROM's
sampling loop (`machine.py`, the `0x9EDF9`/`0x9EE35` special case) but models
nothing of the timing side. On the board the received data also reaches the
CPU inverted through a 74AHC04 into `T1IN`, CPU pin 78, which is how the
firmware measures a bit cell (see `docs/asic-pinout.md`).

Receive and transmit completion set RI and TI independently of the interrupt
request latches. Reading status clears those flags and OE; reading S0RBUF
consumes the data without clearing RI. An unread byte replaced by a later
reception sets OE and retains the newer byte. CTS and TXE survive status reads.
Framing, parity and BREAK errors still require a richer wire receiver.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from math import ceil
from typing import Any

B0CMP = 0xFF60
B0CNT = 0xFF62
S0CON = 0xFF64
S0STS = 0xFF66
S0RBUF = 0xFF68
S0TBUF = 0xFF6A

REGISTERS = (B0CMP, B0CNT, S0CON, S0STS, S0RBUF, S0TBUF)

# S0CON bit 5 enables the receiver. The ROM writes 0x21 - mode 1 plus this.
CONTROL_RECEIVE_ENABLE = 0x20

# S0STS bit assignments, from Figure 10-14 of the 80C186EB user's manual
# (270830-003, page 10-16). The figure's fields sit above a reserved bit 0, so
# every name is one place higher than a plain reading of the field list gives:
# CTS 1, OE 2, TXE 3, FE 4, TI 5, RI 6, RB8/PE 7, DBRK0 8, DBRK1 9.
#
# Four firmware uses corroborate that offset, and none of them parses under the
# unshifted reading: the pre-transmit spin at 0x81603 waits on mask 8 (TXE, not
# FE); 0x9f03e skips a receive when mask 0x10 is set (FE, not TI); 0x8181e and
# 0x81892 test mask 0x300 (DBRK0/DBRK1, i.e. BREAK from the DTE); and the
# transmit ISR's second-byte write at 0x819f1 gates on mask 2.
#
# CTS is the complement of the CTS pin, which the DTE drives with RTS. It is
# not cleared by reading the register.
CLEAR_TO_SEND = 0x02
# TXE, set when SxTBUF and the shift register are both empty. The transmit
# routine at 0x81613 spins on it before every byte it writes to S0TBUF, and
# the ISR uses it to decide whether a second byte can follow immediately.
# The timed transmitter is ready only once both slots are empty. The legacy
# synchronous path is always ready. Accessing S0STS does not clear TXE.
TRANSMIT_READY = 0x08
# RI, set when a character has been placed in S0RBUF. This board's receive is
# interrupt driven off the vector below and no firmware path polls RI, which
# is why an earlier revision of this module could label bit 1 as receive-ready
# without a run detecting the error.
RECEIVE_READY = 0x40
TRANSMIT_COMPLETE = 0x20
OVERRUN_ERROR = 0x04

# The part's fixed serial interrupt types, confirmed against the live board's
# vector table rather than assumed.

RECEIVE_VECTOR = 0x14
TRANSMIT_VECTOR = 0x15


@dataclass
class EbSerial:
    """Serial port 0 of the 80C186EB, driven from the control block."""

    control: int = 0
    baud_compare: int = 0
    baud_count: int = 0
    receive_holding: int = 0
    transmitted: int = 0
    received: int = 0
    pending: deque[int] = field(default_factory=deque)
    # A character on the wire, not yet handed to the firmware.
    holding: bool = False
    receive_ready: bool = False
    receive_unread: bool = False
    transmit_complete: bool = False
    overrun: bool = False
    overruns: int = 0
    # The CTS pin's asserted state, which a real DTE drives with RTS.
    #
    # Nothing here models the host side of the Plug and Play handshake, so
    # this is raised when a character is delivered. That keeps the [0x31f]
    # chain advancing, but it is a stand-in: the real sequence is the DTE
    # dropping DTR on port 0x14
    # bit 0 and asserting RTS 30 to 50 ticks later, and until the terminal
    # model drives those two lines the chain is reached by the right bit for
    # the wrong reason. On the part, reading the register does not clear CTS.
    clear_to_send: bool = False
    timed_transmit: bool = False
    transmit_overruns: int = 0
    _now: int = 0
    _cycles_per_instruction: float = 1.0
    _tx_stop: int | None = None
    _tx_end: int | None = None
    _tx_buffer: int | None = None

    @property
    def transmit_busy(self) -> bool:
        return self._tx_end is not None

    def transmit_quiet_until(self, instructions: int) -> int | None:
        """Next TX state change; never elide a pending request or a due event."""
        deadline = self._tx_stop if self._tx_stop is not None else self._tx_end
        if self.pending or deadline is None or instructions >= deadline:
            return None
        return deadline

    def _start_transmit(self, instructions: int) -> None:
        # Intel 270830-003 §§10.1.1.2, 10.2.1: asynchronous baud clock
        # is CPU / (8 * (BxCMP + 1)); TI asserts at the start of stop.
        bit_cycles = 8 * ((self.baud_compare & 0x7fff) + 1)
        self._tx_stop = instructions + ceil(9 * bit_cycles / self._cycles_per_instruction)
        self._tx_end = instructions + ceil(10 * bit_cycles / self._cycles_per_instruction)

    def advance(self, instructions: int, cycles_per_instruction: float) -> None:
        self._now = instructions
        self._cycles_per_instruction = cycles_per_instruction
        while self._tx_end is not None:
            if self._tx_stop is not None and instructions >= self._tx_stop:
                self.transmit_complete = True
                self._request(TRANSMIT_VECTOR)
                self._tx_stop = None
            if instructions < self._tx_end:
                break
            end = self._tx_end
            self._tx_end = None
            if self._tx_buffer is not None:
                self._tx_buffer = None
                self._start_transmit(end)

    @property
    def receive_available(self) -> bool:
        """Room for the harness DTE's next byte, independent of TX requests."""
        return not self.receive_unread and RECEIVE_VECTOR not in self.pending

    @property
    def receive_enabled(self) -> bool:
        return bool(self.control & CONTROL_RECEIVE_ENABLE)

    def read(self, address: int, size: int) -> int | None:
        """The value a read of `address` should find, or None if not ours."""
        if address == S0STS:
            # The callback chain at [0x31f] is the Plug and Play external COM
            # device enumeration: it wants DTR dropped and then CTS asserted,
            # and posts event 0x0e, which emits the PnP identifier string. An
            # earlier revision reached the same node by treating bit 1 as
            # receive-data-available, because asserting it does advance the
            # chain - as CTS, not as data. Bit 1 is driven from the modelled
            # DTE adapter's handshake instead. Reading status must not
            # deassert this level-sensitive input.
            status = ((0 if self.transmit_busy else TRANSMIT_READY)
                      | (CLEAR_TO_SEND if self.clear_to_send else 0)
                      | (RECEIVE_READY if self.receive_ready else 0)
                      | (TRANSMIT_COMPLETE if self.transmit_complete else 0)
                      | (OVERRUN_ERROR if self.overrun else 0))
            # RI and TI are read to clear, which is why the firmware reads the
            # register at sites that discard the value: those reads are the
            # acknowledge. Taking the byte out of S0RBUF does not clear it.
            # CTS and TXE are not cleared by the read.
            self.receive_ready = False
            self.transmit_complete = False
            self.overrun = False
            return status
        if address == S0RBUF:
            self.receive_unread = False
            return self.receive_holding
        if address == S0CON:
            return self.control
        if address == B0CMP:
            return self.baud_compare
        if address == B0CNT:
            return self.baud_count
        return None

    def write(self, address: int, size: int, value: int) -> int | None:
        """Apply a write. Returns a byte the firmware transmitted, or None."""
        if address == S0CON:
            self.control = value
        elif address == B0CMP:
            self.baud_compare = value
        elif address == B0CNT:
            self.baud_count = value
        elif address == S0TBUF:
            self.transmitted += 1
            if (self.timed_transmit and self.baud_compare & 0x8000
                    and self.control & 7 == 1):
                if not self.transmit_busy:
                    self._start_transmit(self._now)
                else:
                    if self._tx_buffer is not None:
                        self.transmit_overruns += 1
                    self._tx_buffer = value & 0xff
            else:
                self.transmit_complete = True
                self._request(TRANSMIT_VECTOR)
            return value & 0xFF
        return None

    def take_interrupt(self) -> int:
        """RX has higher relative priority than TX (Intel 270830-003 §8.1.1.2)."""
        if RECEIVE_VECTOR in self.pending:
            self.pending.remove(RECEIVE_VECTOR)
            return RECEIVE_VECTOR
        return self.pending.popleft()

    def _request(self, vector: int) -> None:
        """Latch an interrupt request, once.

        Each direction has one request latch on the part, not a queue. Letting
        them stack put the banner's sixty-one transmit interrupts in front of
        everything else, and the run loop dispatches one source per iteration:
        the receive line's edge waited about sixty thousand instructions
        behind them, by which time the rate measurement it carries is meanin-
        gless.
        """
        if vector not in self.pending:
            self.pending.append(vector)

    def line_idle(self) -> bool:
        """Whether the DTE handshake line is still at its unasserted level.

        Bit 0 of port 0x14 is not the receive data line - the callback chain
        at [0x31f] samples it about every 133,000 instructions, far too
        slowly to catch a start bit. It is a level: 0x82b0f waits for it
        unasserted, 0x82b2d for it asserted, and only then does the chain set
        the debounce counter at [0x321] that ends in the startup banner.
        0x826e7 busy-waits on the same pin.

        The chain has to observe the unasserted level before the asserted
        one, so the harness's terminal raises its handshake a fixed way into
        the run rather than at reset - a terminal switched on after the modem
        came up, which is the order the chain is written for. The machine
        owns that timing; this only reports whether a character is waiting.
        """
        return self.received == 0 and not self.holding



    def deliver(self, byte: int) -> None:
        """Place a byte in the receive buffer and request its interrupt."""
        if self.receive_unread:
            self.overrun = True
            self.overruns += 1
        self.receive_holding = byte & 0xFF
        self.receive_unread = True
        self.receive_ready = True
        # Stand-in for the DTE's RTS; see the field's comment.
        self.clear_to_send = True
        self.received += 1
        self._request(RECEIVE_VECTOR)

    def status(self) -> dict[str, Any]:
        return {
            "control": f"{self.control:#06x}",
            "baud_compare": f"{self.baud_compare:#06x}",
            "receive_enabled": self.receive_enabled,
            "clear_to_send": self.clear_to_send,
            "receive_ready": self.receive_ready,
            "receive_unread": self.receive_unread,
            "transmit_complete": self.transmit_complete,
            "overruns": self.overruns,
            "received": self.received,
            "transmitted": self.transmitted,
            "timed_transmit": self.timed_transmit,
            "transmit_busy": self.transmit_busy,
            "transmit_overruns": self.transmit_overruns,
        }


class DteInputTiming:
    """Bounded passive timing of online UART deliveries, separate from boot logs."""

    def __init__(self):
        self.count = 0
        self.first = []
        self.recent = deque(maxlen=16)
        self.largest_gaps = []
        self.previous = None
        self.blocked_counts = {}
        self.blocked_examples = {}

    def blocked(self, reason, *, instructions, line_frame, pending, wire_started):
        self.blocked_counts[reason] = self.blocked_counts.get(reason, 0) + 1
        event = {'instructions': instructions, 'line_frame': line_frame,
                 'pending': list(pending),
                 'wire_elapsed_instructions': instructions - wire_started}
        if (reason not in self.blocked_examples or event['wire_elapsed_instructions']
                > self.blocked_examples[reason]['wire_elapsed_instructions']):
            self.blocked_examples[reason] = event

    def observe(self, *, instructions, line_frame, byte, queued, wire_started):
        event = {'index': self.count, 'instructions': instructions,
                 'line_frame': line_frame, 'byte': byte, 'queued': queued,
                 'wire_elapsed_instructions': instructions - wire_started}
        if self.previous is not None:
            gap = instructions - self.previous['instructions']
            event['gap_instructions'] = gap
            self.largest_gaps.append(dict(event))
            self.largest_gaps.sort(key=lambda item: (-item['gap_instructions'], item['index']))
            del self.largest_gaps[8:]
        if len(self.first) < 16:
            self.first.append(dict(event))
        self.recent.append(dict(event))
        self.previous = event
        self.count += 1

    def status(self):
        return {'deliveries': self.count, 'first': list(self.first),
                'recent': list(self.recent), 'largest_gaps': list(self.largest_gaps),
                'blocked_counts': dict(self.blocked_counts),
                'blocked_examples': dict(self.blocked_examples)}


class DteTransmitLine:
    """The DTE's transmit wire, as the modem's receive pin samples it.

    The pin is a wire, not a value produced where the firmware happens to
    read it. A character occupies real time here - one space start bit,
    eight data bits least significant first, then mark - so the level any
    sampler sees depends only on when it looks. Both this board's firmware
    revisions autobaud by sampling this pin through a timer, at routines
    that sit 0x300 apart between the two images; driving the wire instead of
    the code path serves either one without the harness knowing where those
    routines are.

    The frame is 8N1 against the queued byte. The ROM discovers the rate
    from the start bit itself, which is the point of autobaud, so the bit
    period here is the terminal's and not something the firmware is told.
    """

    #: Start bit, eight data bits, stop bit.
    FRAME_BITS = 10

    def __init__(self, bit_instructions: int) -> None:
        self.bit_instructions = bit_instructions
        self.byte: int | None = None
        self.started = 0
        #: The mark-to-space transition that opens a frame. The ROM arms an
        #: external interrupt and a stopwatch and waits for exactly this; it
        #: is the only thing on the wire that says a character has begun.
        self._edge = False

    @property
    def busy(self) -> bool:
        return self.byte is not None

    def begin(self, byte: int, instructions: int) -> None:
        self.byte = byte & 0xFF
        self.started = instructions
        self._edge = True

    def take_edge(self) -> bool:
        """Consume the start edge, if one is waiting. One frame, one edge."""
        edge, self._edge = self._edge, False
        return edge

    def bit_index(self, instructions: int) -> int:
        if self.byte is None:
            return self.FRAME_BITS
        return (instructions - self.started) // self.bit_instructions

    def level(self, instructions: int) -> int:
        """1 for mark, 0 for space. Idle is mark, which is what a terminal
        that is not sending holds the line at - and what the ROM's samplers
        shift in while they wait."""
        index = self.bit_index(instructions)
        if self.byte is None or index >= self.FRAME_BITS - 1:
            return 1
        if index == 0:
            return 0
        return (self.byte >> (index - 1)) & 1

    def complete(self, instructions: int) -> bool:
        """Whether the stop bit has been on the wire long enough to end the
        frame. The receiver latches the character here."""
        return self.byte is not None and self.bit_index(instructions) >= self.FRAME_BITS

    def idle(self) -> None:
        self.byte = None
        self._edge = False
