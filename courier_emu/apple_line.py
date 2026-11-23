"""Hardware-only Apple USB modem transport, directly on the Courier codec grid.

The helper's HAL callbacks never call Python, USB, malloc or blocking I/O.
Socket replies are paced by captured hardware samples. No 8 kHz line hop,
companding, synthetic call progress or software modem is involved. Output keeps
firmware levels by default: an extra quarter-scale loopback attenuation made
real ATA digit collection fail, despite correct DTMF in the codec-side trace.
"""
from __future__ import annotations

from pathlib import Path
import math
import os
import socket
import struct
import subprocess
import time
from collections.abc import Iterable

from .resample import BandLimitedResampler, prepare_resampling, resampling_prepared
from .timebase import ASIC_DSP_CLOCK_HZ
from .dsp import prepare_line_input

APPLE_RATES = (7200, 8000, 8229, 8400, 9000, 9600, 10286)
_REQUEST = struct.Struct("<II")
_REPLY = struct.Struct("<IIII")
_FLAG_HOOK = 1
_FLAG_RESET = 2


def hardware_rate(codec_rate: float) -> int:
    """Exact rate when available, otherwise the next higher device rate."""
    for rate in APPLE_RATES:
        if rate >= codec_rate - 0.01:
            return rate
    raise ValueError(f"Apple modem cannot cover codec rate {codec_rate:g} Hz")


def courier_codec_rates() -> tuple[float, ...]:
    """Common codec grids plus every 403 PLL/ASIC transition combination.

    The ASIC timing latch and AC01 B divider are written separately. Include
    their intermediate clocks, not just final negotiated rates. Match the
    integer C5x frame periods used by codec_recompute_rate/line clock events.
    """
    rates = set(map(float, APPLE_RATES))
    rates.update((ASIC_DSP_CLOCK_HZ / 5320, 8228.0, 57_600 / 7,
                  30_800 / 3, 10285.0, 72_000 / 7))
    for timing in (0x78, 0x82, 0x85, 0x8e, 0x90, 0x9a):
        mclk = 2_880_000 * timing // 0x78
        for b in (18, 19, 20):
            period = ASIC_DSP_CLOCK_HZ * (2 * 10 * b) // mclk
            rates.add(ASIC_DSP_CLOCK_HZ / period)
    return tuple(sorted(rates))


class AppleLine:
    audio_only = True       # disable all synthetic training/carrier machinery
    codec_direct = True
    digital = True          # the physical hybrid supplies its own echo
    peer_off_hook = False
    peer_ringing = False
    peer_call_state = 0
    peer_instructions = 0
    error: str | None = None
    closed = False
    frames = 0
    sent_samples = 0
    received_samples = 0
    output_gap_samples = 0
    input_overflow_samples = 0

    def __init__(self, helper: str, rate: int = 10286, *, tx_gain: float = 1.0,
                 transport: socket.socket | None = None,
                 codec_rates: Iterable[float] = ()) -> None:
        if rate not in APPLE_RATES:
            raise ValueError(f"unsupported Apple sample rate {rate}")
        if not 0 <= tx_gain <= 1:
            raise ValueError("Apple TX gain must be between 0 and 1")
        self.helper = str(Path(helper).resolve())
        self.rate = rate
        self.buffer_frames_requested = int(os.environ.get('APPLE_MODEM_BUFFER_FRAMES', '0') or '0')
        if self.buffer_frames_requested != 0 and not 4 <= self.buffer_frames_requested <= 4096:
            raise ValueError('Apple audio buffer must be 0 (default) or 4..4096 frames')
        self.codec_service_seconds = .005 if 0 < self.buffer_frames_requested <= 128 else .02
        self.tx_gain = tx_gain
        self._socket = transport
        self._process: subprocess.Popen | None = None
        self._tx = BandLimitedResampler()
        self._rx = BandLimitedResampler()
        self._off_hook = False
        self.native_receive = False
        self.resetting = False
        self._control_state: tuple[bool, bool] | None = None
        self.control_updates = 0
        self._off_hook_samples = 0
        self.on_error = None
        self._last_codec_rate = 0.0
        self._dc_x = self._dc_y = 0.0
        self._raw_rx_peak = self._raw_rx_near_rail = 0
        self._raw_rx_sum = self._raw_rx_count = 0
        self.rate_history: list[float] = []
        self.prepared_codec_rates: set[float] = set()
        self.preparation_ms = 0.0
        self.live_filter_misses: list[float] = []
        # Construction precedes helper startup/seizure. Do not insert dummy
        # samples into the real converters: preparation changes caches only.
        self.prepare_codec_rates(r for r in courier_codec_rates() if r <= rate + 0.01)
        self.prepare_codec_rates(codec_rates)

    def prepare_codec_rates(self, rates: Iterable[float]) -> None:
        """Extend the rate plan while on-hook, including nonstandard board clocks."""
        if self._off_hook:
            raise RuntimeError("prepare Apple codec rates before seizing the line")
        start = time.perf_counter()
        for rate in rates:
            if not math.isfinite(rate) or not 0 < rate <= self.rate + 0.01:
                raise ValueError(f"codec rate {rate:g} exceeds Apple hardware rate {self.rate}")
            prepare_resampling(rate, self.rate, retuned=True)
            prepare_resampling(self.rate, rate)
            prepare_line_input(self.rate, rate)
            self.prepared_codec_rates.add(float(rate))
        self.preparation_ms += (time.perf_counter() - start) * 1000

    @property
    def connected(self) -> bool:
        return self._socket is not None and not self.closed

    def open(self) -> None:
        if self._socket is not None:
            return
        parent, child = socket.socketpair()
        try:
            self._process = subprocess.Popen(
                [self.helper, str(child.fileno()), str(self.rate)],
                pass_fds=(child.fileno(),), stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL)
        except BaseException:
            parent.close()
            raise
        finally:
            child.close()
        parent.settimeout(5)
        self._socket = parent

    def _read_exact(self, n: int) -> bytes:
        data = bytearray()
        while len(data) < n:
            chunk = self._socket.recv(n - len(data))
            if not chunk:
                raise RuntimeError("Apple audio helper closed (see its stderr)")
            data.extend(chunk)
        return bytes(data)

    def _exchange(self, payload: list[int], off_hook: bool, resetting: bool = False) -> bytes:
        """One serialized hardware transaction; zero samples is immediate control."""
        flags = (_FLAG_HOOK if off_hook else 0) | (_FLAG_RESET if resetting else 0)
        count = len(payload)
        self._socket.sendall(_REQUEST.pack(count, flags)
                             + struct.pack(f"<{count}h", *payload))
        received, ring, gaps, overflow = _REPLY.unpack(self._read_exact(_REPLY.size))
        if received not in (0, count) or ring > 1:
            raise RuntimeError("invalid Apple audio reply")
        # A zero-count terminal reply carries callback failure counters even
        # when the helper cannot complete the requested PCM exchange.
        self.peer_ringing = bool(ring)
        self.output_gap_samples = gaps
        self.input_overflow_samples = overflow
        if overflow:
            raise RuntimeError("Apple input overflow: host cannot keep up in real time")
        if gaps:
            raise RuntimeError("Apple output underrun while off-hook: host cannot keep up in real time")
        if received != count:
            raise RuntimeError("invalid Apple audio reply")
        raw = self._read_exact(count * 2)
        self._off_hook = off_hook
        self.resetting = resetting
        self._control_state = (off_hook, resetting)
        return raw

    def _fail(self, exc: Exception) -> None:
        self.error = str(exc)
        self.close()
        if self.on_error is not None:
            self.on_error()
        raise RuntimeError(f"Apple line: {exc}") from exc

    def set_control(self, off_hook: bool, *, resetting: bool = False) -> None:
        """Control the physical DAA without a codec rate, samples or ADC wait.

        Explicit reset mode keeps HAL silence running independently of the
        guest. The helper bounds off-hook resets to five seconds and still
        fails closed on unexpected starvation outside this mode.
        """
        state = (bool(off_hook), bool(resetting))
        if not self.connected:
            raise RuntimeError("Apple line is not open")
        if self._control_state == state:
            return
        was_reset = self.resetting
        try:
            self._exchange([], *state)
            self.control_updates += 1
            if resetting and not was_reset:
                # Retired DSP output must not bleed into a new generation.
                self._tx = BandLimitedResampler()
                self._rx = BandLimitedResampler()
        except (OSError, RuntimeError) as exc:
            self._fail(exc)

    def enable_native_receive(self) -> None:
        """Keep RX on the hardware grid; the DSP ADC owns any future retunes."""
        if not self.native_receive and self.frames:
            raise RuntimeError('select the native ADC grid before exchanging PCM')
        self.native_receive = True

    def service_codec(self, samples: list[int], codec_rate: float,
                      off_hook: bool) -> list[int]:
        if not self.connected:
            raise RuntimeError("Apple line is not open")
        # Release immediately, but never seize before any needed preparation.
        if not off_hook and self._off_hook:
            self.set_control(False, resetting=self.resetting)
        if not 0 < codec_rate <= self.rate + 0.01:
            self.error = (f"codec rate {codec_rate:g} exceeds Apple hardware "
                          f"rate {self.rate}; restart with a higher --apple-rate")
            self.close()
            if self.on_error is not None:
                self.on_error()
            raise RuntimeError(self.error)
        if not (resampling_prepared(codec_rate, self.rate, retuned=True)
                and resampling_prepared(self.rate, codec_rate)):
            if self._off_hook:
                self.live_filter_misses.append(codec_rate)
                self._fail(RuntimeError(
                    f"unprepared Apple codec rate {codec_rate:g} Hz; "
                    "prepare its filters before seizing the line"))
            self.prepare_codec_rates((codec_rate,))
        if off_hook and not self._off_hook:
            self.set_control(True, resetting=self.resetting)
        if codec_rate != self._last_codec_rate:
            self.rate_history.append(codec_rate)
            self._last_codec_rate = codec_rate
        tx = self._tx.convert(samples, codec_rate, self.rate)
        if not tx:
            return []
        received: list[int] = []
        try:
            for start in range(0, len(tx), 2048):
                chunk = tx[start:start + 2048]
                payload = [round(s * self.tx_gain) if off_hook else 0 for s in chunk]
                # First real PCM after reset atomically resumes strict mode;
                # there is no unprimed control-only resume before this payload.
                count = len(chunk)
                raw = struct.unpack(f"<{count}h", self._exchange(payload, off_hook))
                self._raw_rx_peak = max(self._raw_rx_peak, max(map(abs, raw)))
                self._raw_rx_near_rail += sum(abs(v) >= 32760 for v in raw)
                self._raw_rx_sum += sum(raw)
                self._raw_rx_count += count
                # Remove codec/line DC, not modem-band energy. State survives
                # rate changes; pole corresponds to approximately 8 Hz.
                pole = math.exp(-2 * math.pi * 8 / self.rate)
                for value in raw:
                    y = value - self._dc_x + pole * self._dc_y
                    self._dc_x, self._dc_y = value, y
                    received.append(max(-32768, min(32767, round(y))))
                self.sent_samples += count
                self.received_samples += count
                if off_hook:
                    self._off_hook_samples += count
                self.frames += 1
            self._off_hook = off_hook
            return received if self.native_receive else self._rx.convert(received, self.rate, codec_rate)
        except (OSError, RuntimeError) as exc:
            self._fail(exc)

    def status(self) -> dict:
        return {"backend": "apple-usb-modem", "connected": self.connected,
                "sample_rate": self.rate, "codec_direct": True,
                "native_receive": self.native_receive,
                "buffer_frames_requested": self.buffer_frames_requested,
                "codec_service_ms": 1000*self.codec_service_seconds,
                "codec_rates": self.rate_history, "frames": self.frames,
                "prepared_codec_rates": sorted(self.prepared_codec_rates),
                "preparation_ms": self.preparation_ms,
                "live_filter_misses": self.live_filter_misses,
                "off_hook": self._off_hook, "ringing": self.peer_ringing,
                "resetting": self.resetting, "control_updates": self.control_updates,
                "samples_sent": self.sent_samples, "samples_received": self.received_samples,
                "off_hook_pcm_seconds": self._off_hook_samples / self.rate,
                "output_gap_samples": self.output_gap_samples,
                "input_overflow_samples": self.input_overflow_samples,
                "raw_rx_peak": self._raw_rx_peak,
                "raw_rx_near_rail_samples": self._raw_rx_near_rail,
                "raw_rx_mean": self._raw_rx_sum / max(1, self._raw_rx_count),
                "tx_gain": self.tx_gain, "error": self.error}

    def finish_stream(self) -> None:
        """Release/mute before the stopped CPU's potentially slow reporting.

        This is an explicit physical hangup, not permission to forgive an
        active underrun. Existing helper errors/counters still fail the call.
        """
        if self.connected:
            self.set_control(False, resetting=True)

    def close(self) -> None:
        self.closed = True
        if self._socket is not None:
            self._socket.close()
            self._socket = None
        if self._process is not None:
            try:
                self._process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._process.terminate()
                try:
                    self._process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    # SIGKILL cannot restore hook; leave a visible error.
                    self.error = self.error or "Apple helper did not release the line; unplug it"
                    self._process.kill()
                    self._process.wait()
            if self._process.returncode and self.error is None:
                self.error = (f"Apple helper exited with status {self._process.returncode}; "
                              "see its stderr for audio/line diagnostics")
