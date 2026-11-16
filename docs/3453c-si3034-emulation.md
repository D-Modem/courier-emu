# 3453C Si3034 serial codec

The recovered-ROM path of the 3453C now selects a native Si3034 codec. Before
this change, its serial words went through the legacy TDM/AC01 behavior. The
supervisor still loads the original DSP resident and overlays through the
recovered loader. That DSP firmware does the codec setup.

The Si3034 datasheet, revision 2.02, sections 5.21 and 5.22 and registers
1–19, describes a protocol that is different from the AC01:

- In the reset 15-bit mode, bit 0 of the primary word requests a secondary
  frame. Bit 1 stays audio. Secondary controls use bit 13 for read/write,
  bits 12:8 for the address and bits 7:0 for the data.
- PLL fields store their multiplier/divisor minus one. PLL2 writes latch
  the clock configuration. CGM applies the 16/25 ratio when PLL2 is not
  bypassed. With a 2.88 MHz MCLK, the 0704, 083F, 0911 controls of the guest
  give 7,200 Hz. They are not an AC01 A/B divider configuration.
- Register 6 controls the line-side power. Registers 2, 13 and 15 control
  receive enable, gains and mutes. Power-down mutes PCM while the serial
  frames continue. The external modeled line supplies the hook, ring and
  loop-current status for register reads.
- Country controls 16–18 keep the values that the guest writes. The model
  keeps the observed proprietary register 20, but it does not give it
  undocumented effects.

The native serial clock sends primary PCM and secondary readback to DRR. It
holds the DAC output until a new value replaces it. It raises the serial
receive/transmit events. This profile does not apply the separate INT3 frame
wiring of the 403 board. When the serial codec is enabled, the host mailbox
input and output latches stay separate. This is necessary to keep the DSP
overlay requests. DSP and codec resets restore the Si3034 register defaults,
and keep the configured board MCLK. The AC01 selection stays separate.

Source: [Si3034 datasheet](SI3034.PDF), mainly Figures 24–27 and Table 19.
The 2.88 MHz MCLK is the existing model clock. It agrees with the PLL settings
of the firmware. It is not a new measurement. Serial revision register 13 uses
the board-profile inference of an international revision-C line side. The
recorded DAA identity is not a direct serial-register read.

## Execution evidence

Now the guest writes its native codec registers, programs 7,200 Hz and clears
PDL. An independent ATI0 control still returns 5608A. The pair retest executes
150 million 3453C instructions and 400 million I-modem instructions. The codec
clocks 244,305 primary frames, with 36 register writes. It consumes the
received PCM, and does not leave all of the input queue untouched.

The pair still does not connect. The complete AT dial command is consumed and
the relay goes off hook, but the 3453C stays in dialing. No incoming call gets
to the I-modem, and the transmitted PCM is zero. That result is a remaining
call-control/ASIC gap. It is not a successful interoperability test.
The run and the raw captures are in
[the evidence bundle](../artifacts/3453c-si3034-20261003/).

The [codec/hook audit](../artifacts/3453c-codec-call-audit-20261003/README.md)
after this found an earlier call-control abort: INT0 trips the supervisor
watchdog, because the board tick does not reset its counter.
Then the abort path stalled on a missing UART TX-empty status bit. That
status read is now correct. Thus the hook releases and the cleanup completes.
The pair still does not connect. The
[watchdog fix](../artifacts/3453c-watchdog-20261003/README.md) after this
selects the 80C186EB interrupt masks and recognizes the return of the 2.3.x
mailbox ISR. This restores the external tick at vector 0F. The internal CPU
timer interrupts are not the missing source of the watchdog reset. The earlier
timer-delivery experiments are not enabled by default.

The audit also recovers the host tags 7D/82/83 as Si3034 registers 16/17/18,
which include termination, calibration and dialing controls. Now the bridge
lets the C52 execute them and reply. It does not interpret the 3453C tag 82
as the call-engine start/hold control of the older ASIC.

## Serial readback timing

The active Si3034 port now moves DXR into its transmit shifter at FSYNC and
raises XINT at that time. It sends the received word to DRR and raises RINT 16
SCLKs later. Section 5.22 specifies SCLK = 256 × Fs. Thus this interval is
one sixteenth of a primary period. The secondary exchange occurs halfway
through that period and returns its addressed register in the same exchange.
Thus the next primary XINT handler can read the completed secondary reply
before the new primary receive word replaces it.

The request `7C:0000` of the unchanged resident sends `2CFF`. For a connected
off-hook line, it receives `0044` and builds the pending reply `0244` in data
cell `012F`. With no modeled loop current, it receives `0040`. Guest-execution
tests cover these results, together with a serial word-completion test.
The timing applies to the active clocked port. Synchronous control probes
with the transmitter in reset keep their direct-control API.

The pair retest after this completes without CPU/DSP or overlay errors. Now
it exchanges nonzero audio. The I-modem reports RING and answers the bearer,
but the training stops with NO CARRIER, and no payload arrives. The detailed
[readback retest](../artifacts/3453c-watchdog-20261003/README.md) also records
the corrected overlay verifier. The resident restores BMAR from its saved
pointer before the transfer. Thus the verification uses its completed `7F62`
marker, not the earlier BMAR value of the foreground.

## Remaining model limits

This implements the serial mode 0/1 setup and the usual PCM path of the guest.
These items are not fully modeled: hardware FC requests in 16-bit mode,
daisy-chain/slave mode, physical PLL lock transients, analog/digital loopback
modes, persistent latching of the ring detector, and electrical/filter
calibration. The ring status follows the existing coarse cadence of the line
source. The historical AC'97-style `CodecBringUp` report stays separate from
the native Si3034 registers. Its `complete` flag does not show datapump
operation.
