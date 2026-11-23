# Apple physical-line bring-up

Initial evidence from the attached A1082 on this macOS host. No number was dialed.
The later [optimized 403 run](../apple-line-optimized/README.md) sustains off-hook
PCM successfully; the failures below are retained for comparison, not the current
403 result. See [backend usage and limits](../../docs/apple-usb-line.md).

## Passing hardware transport (final build)

- `rate-ladder-onhook.json` / `.log`: hardware 10286 Hz; Courier grids 7200,
  7578.947368, 8000, 9600 and 10266.666667 Hz. Each stage carries approximately
  one second; no active output gaps or input overflow. No off-hook transition.
- `native-7200-offhook.json` / `.log`: exact native 7200 Hz, 14,400 received codec
  samples over the two-second off-hook stage, no active gaps/overflow.
- `rate-ladder-offhook.json` / `.log`: four consecutive one-second stages at
  7200, 7578.947368, 8000 and 9600 Hz over fixed 10286 Hz hardware. No active gaps
  or overflow. Hook/current/sense readbacks confirm a powered line, and shutdown
  confirms on-hook. The raw capture statistics show near-rail samples: this is
  transport evidence, not a calibrated clean telephone channel.
- `final-line-status.json` / `.log`: independent post-run hook/status readback.

Probes transmit silence. They establish the full-duplex hardware transport and
rate handling, **not** the output amplitude, modulation quality or a far-end
modem's ability to receive Courier firmware samples.

## Original firmware, final transport build

- `firmware-onhook-final.json` / `.log`: assembled captured B/C 2.2.09 with erased
  settings, `ATI3`, DSP tick source, 50 hardware exchanges. Original firmware
  returns `USRobotics Courier V.Everything EXT` and `OK`. Both CPU and bridge
  report no error, and physical shutdown verifies on-hook.
- `firmware-offhook-final.json` / `.log`: same image, `ATH1`, 150-exchange ceiling.
  This run **fails**: the supervisor/DSP execution does not replenish hardware
  output in time. The helper releases the line, the worker stops early and
  returns exit 1. No successful connection or payload is claimed.

The firmware image used locally at `tmp/apple-test-flash.bin` was assembled with
`courier_emu.flash_image.assemble_flash` from:

- `dumps/3453bc-4MBRYA8G1514-bootmodem-read-20261014/bootmodem.bin`
- `dumps/3453bc-firmware-read-2.2.09/firmware.bin`
- 16 KiB of erased (`ff`) settings

Normal firmware runs use 10,000,000 instructions as the ceiling, `--apple-modem`,
`--tick-source dsp`, and `--at ATI3` or `--at ATH1`. JSON was captured directly
from `courier_emu.worker` so helper stderr and failure reports are retained.

## Earlier debugging captures

Other files here are intermediate runs, not the acceptance evidence above.
They include an initially insufficient output cushion, on-hook stale-FIFO
handling, and earlier firmware runs that did not stop promptly after a backend
failure. The final helper discovers HAL block size, primes two callbacks,
retains ordinary input bursts, fails closed on active sample loss, and the
worker reports a nonzero exit instead of continuing with a dead line.

The captured 403 ROM's on-hook stream also exercised clock changes, but its test
AT command remained queued. The older `3453Bv2.1.1.xmf` trial stopped with a native
lane-map KeyError; it is not a passing firmware configuration.

No CONNECT, Bell-103 data transfer, ring auto-answer, long-duration clock-drift,
or V.90/V.92 interoperability result is established by this directory.
