#!/usr/bin/env python3
"""Run two I-modem firmware instances back to back over a PCMU B channel."""

from __future__ import annotations

import argparse
from contextlib import ExitStack
from collections import deque
import hashlib
import json
from pathlib import Path
import re
import socket
import struct
import subprocess
import sys
import tempfile
import time
from typing import Any

from courier_emu.bri import BriNetwork, CAPABILITY_AUDIO_31KHZ, audio_bearer
from courier_emu.isdn import IsdnMachine
from courier_emu.isdn_console import _on_the_wire, scripted_pump
from courier_emu.nac import NacImage
from courier_emu.line import LINE_FRAME_SAMPLES


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.imodem_traffic import Traffic, check_traffic
from tools.x2_source_impairment import BearerLog, SourceImpairment
_IMPAIRMENT = SourceImpairment.from_environment()
_WIRELOG = BearerLog.from_environment()
DEFAULT_IMAGE = ROOT / "Ie030002.nac"
FRAME_OCTETS = LINE_FRAME_SAMPLES
HEADER = struct.Struct("<H")
SOCKET_TIMEOUT = 180


class G711Peer:
    """A synchronous, byte-exact B-channel socket (100 ms frames by default)."""

    # A completed block must reach the peer before the next MUX RX clock.
    # Deferring it to the next supervisor poll can insert an idle sample at
    # a block boundary even though the peer supplied a continuous stream.
    requires_frame_service = True

    def __init__(self, path: str, *, listen: bool) -> None:
        self.path = path
        self.frame_octets = FRAME_OCTETS
        self.listen = listen
        self.handle: socket.socket | None = None
        self.server: socket.socket | None = None
        self.pending = bytearray()
        self.frames = 0
        self.sent = 0
        self.received = 0
        self.sent_non_ff = 0
        self.received_non_ff = 0
        self.error: str | None = None

    def start(self) -> None:
        if self.handle is not None or self.error is not None:
            return
        if self.listen:
            self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.server.bind(self.path)
            self.server.listen(1)
            self.server.settimeout(SOCKET_TIMEOUT)
            self.handle, _ = self.server.accept()
        else:
            deadline = time.monotonic() + SOCKET_TIMEOUT
            while True:
                candidate = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                try:
                    candidate.connect(self.path)
                    self.handle = candidate
                    break
                except (FileNotFoundError, ConnectionRefusedError):
                    candidate.close()
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.01)
        self.handle.settimeout(SOCKET_TIMEOUT)

    def _read(self, count: int) -> bytes:
        assert self.handle is not None
        result = bytearray()
        while len(result) < count:
            chunk = self.handle.recv(count - len(result))
            if not chunk:
                raise ConnectionError("the far I-modem closed the B channel")
            result.extend(chunk)
        return bytes(result)

    def exchange(self, octets: bytes) -> bytes:
        # Once the far emulator reaches its instruction limit the bearer is
        # permanently closed. BriNetwork continues polling until this side
        # reaches its own limit, so retain the terminal error instead of
        # trying to reopen (and, for the listener, re-bind) the same socket.
        if self.error is not None or self.handle is None:
            return b""
        self.pending.extend(octets)
        reply = bytearray()
        while len(self.pending) >= self.frame_octets:
            frame = bytes(self.pending[:self.frame_octets])
            del self.pending[:self.frame_octets]
            try:
                assert self.handle is not None
                self.handle.sendall(HEADER.pack(len(frame)) + frame)
                size, = HEADER.unpack(self._read(HEADER.size))
                incoming = self._read(size)
            except (OSError, ConnectionError) as exc:
                self.error = str(exc)
                self.stop()
                break
            if _WIRELOG is not None:
                _WIRELOG.write(incoming)
            if _IMPAIRMENT is not None:
                incoming = _IMPAIRMENT.filter(incoming)
            reply.extend(incoming)
            self.frames += 1
            self.sent += len(frame)
            self.received += len(incoming)
            self.sent_non_ff += sum(value != 0xFF for value in frame)
            self.received_non_ff += sum(value != 0xFF for value in incoming)
        return bytes(reply)

    def stop(self) -> None:
        for handle in (self.handle, self.server):
            if handle is not None:
                try:
                    handle.close()
                except OSError:
                    pass
        self.handle = self.server = None

    def status(self) -> dict[str, Any]:
        return {
            "listen": self.listen,
            "frame_octets": self.frame_octets,
            "frames": self.frames,
            "octets_sent": self.sent,
            "octets_received": self.received,
            "sent_non_ff": self.sent_non_ff,
            "received_non_ff": self.received_non_ff,
            "pending": len(self.pending),
            "error": self.error,
        }


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, default=DEFAULT_IMAGE)
    parser.add_argument("--instructions", type=int, default=150_000_000)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--protocol", choices=("default", "x2"), default="default",
                        help="use default negotiation or disable V.90 for an x2 symmetric call")
    parser.add_argument("--check-connect", action="store_true",
                        help="fail unless both firmware instances return a modem CONNECT result")
    parser.add_argument("--check-x2", action="store_true",
                        help="fail unless both CONNECT results identify x2 modulation")
    parser.add_argument("--link-diagnostics", action="store_true",
                        help="escape after CONNECT, query ATI6, then resume with ATO")
    parser.add_argument("--post-call-diagnostics", action="store_true",
                        help="query ATI6 after a connected call returns NO CARRIER")
    parser.add_argument("--originate-send", default="", help="caller payload after CONNECT")
    parser.add_argument("--answer-send", default="", help="answerer payload after CONNECT")
    parser.add_argument("--send-delay-frames", type=int, default=0,
                        help="wait this many media frames (100 ms by default) after CONNECT before marker sends")
    parser.add_argument("--settings", default="",
                        help="additional AT settings on both ends before dial/answer")
    parser.add_argument("--snapshot-frame", type=int, action="append", default=[], help=argparse.SUPPRESS)
    parser.add_argument("--snapshot-read-range", help=argparse.SUPPRESS)
    parser.add_argument("--trace-data-lanes", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--trace-negotiation", action="store_true",
                        help="capture x2 eligibility fields when DSP parameters are sent")
    parser.add_argument("--trace-digital-path", action="store_true",
                        help="trace Ie030002 digital modes and TX scrambler input snapshots")
    parser.add_argument("--product-type", choices=("external", "internal"), default="external",
                        help="select the external DTE or the internal card's host UART")
    parser.add_argument("--internal-baud", choices=(57600, 115200), type=int, default=57600,
                        help="host UART speed for the internal card")
    parser.add_argument("--nvram", type=Path,
                        help="boot both instances from a saved configuration without modifying it")
    parser.add_argument("--establish", choices=("terminal", "network"), default="terminal",
                        help="which end initiates the ISDN data link")
    parser.add_argument("--prime-originate", action="store_true",
                        help="offer an initial ring, then hang up before dialing to establish the caller's data link")
    parser.add_argument("--check-keepalive", action="store_true",
                        help="fail unless both calls survive the V.8 overlay handoff and old clearing window")
    parser.add_argument("--traffic-seconds", type=float, default=0,
                        help="verify sustained bidirectional traffic for this many bearer seconds after CONNECT")
    parser.add_argument("--traffic-window-stop", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--traffic-size", type=int, default=512,
                        help="ASCII payload characters per numbered traffic record (1..4096)")
    parser.add_argument("--worker", choices=("originate", "answer"),
                        help=argparse.SUPPRESS)
    parser.add_argument("--socket", help=argparse.SUPPRESS)
    parser.add_argument("--result", type=Path, help=argparse.SUPPRESS)
    return parser.parse_args()


def dte_receive_state(current) -> dict[str, int]:
    """Read the original Ie030002 DTE receive handoff; never change it."""
    return {name: int.from_bytes(current.machine.mem_read(0x26000 + address, size), "little")
            for name, address, size in (("receiver", 0xe834, 2), ("callback", 0xc922, 2),
                                        ("mode", 0xd1ea, 1))}


def dte_data_ready(state: dict[str, int]) -> bool:
    # 46ba/46cc put DTE characters into the original ca94 data queue.
    # f050 is the direct FIFO-to-data-queue receiver for 8N1 framing.
    # A CONNECT line alone is insufficient: e0e still aborts on a keypress.
    return state["callback"] in (0x46ba, 0x46cc) or state["receiver"] == 0xf050


def run_side(args: argparse.Namespace) -> int:
    if args.traffic_seconds and FRAME_OCTETS != 800:
        raise ValueError("traffic currently requires 100-ms media frames")
    if args.trace_digital_path and hashlib.sha256(args.image.read_bytes()).hexdigest() != (
            "3f9a7aa8033323c28eebfee950b53267a67b7ad9141ebf30271918d0babbe358"):
        raise ValueError("digital-path trace addresses require the verified Ie030002.nac build")
    originate = args.worker == "originate"
    peer = G711Peer(args.socket, listen=originate)
    bri = BriNetwork(
        establish=args.establish,
        call_at=None if originate and not args.prime_originate else 20_000_000,
        call_to="7349195",
        bearer=audio_bearer(CAPABILITY_AUDIO_31KHZ),
        media_peer=peer,
    )
    commands = ["AT*V2=3", "ATD7349195"] if originate else ["ATA"]
    if args.protocol == "x2":
        # S58 bits disable x2 (1), server (2), symmetric (8), and V.90
        # (32). Keep both x2 roles enabled across the digital bearer.
        commands = ["AT*V2=3S58=32&A3&B0", "ATD7349195" if originate else "ATA"]
    if args.settings:
        commands.insert(-1, "AT" + args.settings)
    if originate and args.prime_originate:
        commands.insert(-1, "ATH")
    transcript: list[tuple[int, str, str]] = []
    command_pump = scripted_pump(commands, after=30_000_000, every=0,
                                 transcript=transcript)
    payload = args.originate_send if originate else args.answer_send
    traffic = Traffic("O" if originate else "A", args.traffic_seconds,
                      args.traffic_size) if args.traffic_seconds else None
    traffic_snapshot = None
    traffic_next_poll = 0
    traffic_progress_frame = 0
    traffic_history = deque(maxlen=32)
    from tools.dsp_snapshots import DspSnapshots
    snapshots = DspSnapshots(args.result.with_name("imodem-dsp-snapshots"), args.snapshot_frame,
                             tuple(int(a, 16) for a in args.snapshot_read_range.split(":"))
                             if args.snapshot_read_range else None)
    lane_core = None
    lane_cursor = 0
    data_lanes = []
    stage = "connecting"
    connected_at = 0
    payload_due_frame = None
    post_call_due = None
    disconnect_text = ""
    received_text = ""
    cursor = 0
    host_rate_set = False
    terminal_handoff = {"connect": None, "data_ready": None}
    digital_trace = {"firmware": "Ie030002", "mode_events": [], "samples": [],
                     "capture_pcs": {"width_reset": "e908", "transmit": "e984"}, "capture_addresses": [
                         "0380", "0381", "0382", "03d8", "03d9", "03e0",
                         "031e", "031f", "ffd9", "039a", "039b", "088c", "088d"]}
    traced_core = None
    next_trace = 0
    capture_phase = "width_reset"

    def trace_path(current):
        nonlocal traced_core, next_trace
        core = current.mailbox.core
        if core is None:
            return
        if core is not traced_core:
            core.set_data_trace_filter(0x03e0)
            core.trace_data_writes()
            core.set_pc_capture(0xe908, [int(a, 16) for a in digital_trace["capture_addresses"]])
            traced_core = core
        if current.instructions < next_trace:
            return
        next_trace = current.instructions + 1_000_000
        digital_trace["mode_events"].extend(core.data_events())
        core.trace_data_writes(clear=True)
        captures = core.pc_captures()
        core.clear_pc_captures()
        digital_trace["samples"].append({
            "cpu_instructions": current.instructions,
            "phase": capture_phase,
            "cells": {a: core.data(int(a, 16)) for a in digital_trace["capture_addresses"]},
            "captures": captures,
        })

    def send(current: IsdnMachine, value: str, direction: str = "sent") -> None:
        current.send_serial(_on_the_wire(value, current.dte_framing()))
        transcript.append((current.instructions, direction, value))

    def pump(current: IsdnMachine) -> None:
        nonlocal stage, connected_at, received_text, cursor, host_rate_set, capture_phase, next_trace, payload_due_frame
        nonlocal post_call_due, disconnect_text, traffic_snapshot, traffic_next_poll, traffic_progress_frame
        nonlocal lane_core, lane_cursor
        if snapshots.targets:
            snapshots.poll(current.mailbox.core, peer.frames, current.instructions)
        if args.trace_data_lanes and connected_at and current.mailbox.core:
            core = current.mailbox.core
            total = core.io_event_total()
            if core is not lane_core:
                lane_core, lane_cursor = core, total
            delta = total - lane_cursor
            if not 0 <= delta <= 8192:
                raise RuntimeError("I-modem data-lane trace lost unobserved I/O history")
            for event in core.io_events(limit=delta):
                if event["write"] and 0x58 <= event["port"] <= 0x5d and len(data_lanes) < 131_072:
                    data_lanes.append({"direction": "dsp-to-cpu", "bank": event["port"] - 0x58,
                                       "word": event["value"], "pc": event["pc"],
                                       "instruction": event["instruction"], "frame": peer.frames})
            lane_cursor = total
        traffic_next_poll = current.instructions + 10_000
        if traffic_snapshot is not None and args.traffic_window_stop:
            command_pump(current)
            incoming = "".join(value for _, direction, value in transcript[cursor:]
                               if direction == "received")
            cursor = len(transcript)
            if not peer.error:
                traffic.receive(incoming, peer.frames)
            if peer.error or peer.frames >= traffic.start_frame + traffic.target_frames + 20:
                current.uc.emu_stop()
            return
        if args.trace_digital_path:
            trace_path(current)
        command_pump(current)
        if (args.product_type == "internal" and not host_rate_set
                and any(direction == "sent" for _, direction, _ in transcript)):
            # send_serial opens the host UART before queueing the first AT.
            # Set the requested driver speed before those staged bytes clock
            # into the guest; its attention receiver reads the actual divisor.
            current.channels[current.command_base].host_open(115200 // args.internal_baud, 3)
            host_rate_set = True
        incoming = "".join(value for _, direction, value in transcript[cursor:]
                           if direction == "received")
        received_text += incoming
        if args.post_call_diagnostics and connected_at and stage == "done":
            disconnect_text = (disconnect_text + incoming)[-256:]
            if "\r\nNO CARRIER\r\n" in disconnect_text:
                post_call_due = current.instructions + 1_000_000
                stage = "post_call_wait"
        if post_call_due is not None and current.instructions >= post_call_due:
            send(current, "ATI6\r")
            post_call_due = None
            stage = "post_call_diagnostics"
        if traffic is not None and traffic.start_frame is not None:
            traffic.receive(incoming, peer.frames)
        cursor = len(transcript)
        if stage == "connecting" and connect_result(received_text) is not None:
            connected_at = current.instructions
            terminal_handoff["connect"] = {"instructions": current.instructions,
                                           "frame": peer.frames, **dte_receive_state(current)}
            if args.trace_digital_path:
                next_trace = 0
                trace_path(current)
                current.mailbox.core.set_pc_capture(
                    0xe984, [int(a, 16) for a in digital_trace["capture_addresses"]])
                capture_phase = "transmit"
            if traffic is not None:
                traffic.start(peer.frames)
                match = re.search(r"(?:^|[\r\n])CONNECT[^\r\n]*\r\n", received_text)
                traffic.receive(received_text[match.end():], peer.frames)
            if payload:
                payload_due_frame = peer.frames + args.send_delay_frames
            stage = "guard" if args.link_diagnostics else "done"
            received_text = ""
        elif stage == "guard" and current.instructions >= connected_at + 20_000_000:
            send(current, "+++")
            stage, received_text = "escaping", ""
        elif stage == "escaping" and "\r\nOK\r\n" in received_text:
            send(current, "ATI6\r")
            stage, received_text = "diagnostics", ""
        elif stage == "diagnostics" and "\r\nOK\r\n" in received_text:
            send(current, "ATO\r")
            stage = "done"
        ready = False
        if payload_due_frame is not None or (traffic is not None and traffic.start_frame is not None):
            state = dte_receive_state(current)
            ready = dte_data_ready(state)
            if ready and terminal_handoff["data_ready"] is None:
                terminal_handoff["data_ready"] = {"instructions": current.instructions,
                                                  "frame": peer.frames, **state}
        if ready and payload_due_frame is not None and peer.frames >= payload_due_frame:
            send(current, payload, "sent_data")
            payload_due_frame = None
        if traffic is not None and ready:
            value = traffic.next_record(peer.frames)
            if value is not None:
                send(current, value, "sent_data")
        if (traffic is not None and traffic.start_frame is not None and args.traffic_window_stop
                and (peer.frames >= traffic_progress_frame or peer.error)):
            traffic_progress_frame = peer.frames + 20
            traffic_history.append({"frame": peer.frames, "instructions": current.instructions,
                                    "traffic": traffic.status(peer.frames),
                                    "dte": dte_receive_state(current),
                                    "bearer_underruns": sum(current.dsc.bearer_underruns.values()),
                                    "uart": current.channels[current.command_base].status()})
            args.result.with_name("imodem-traffic-progress.json").write_text(
                json.dumps(list(traffic_history), indent=2) + "\n")
        if (traffic is not None and traffic.start_frame is not None
                and args.traffic_window_stop
                and (peer.error or peer.frames >= traffic.start_frame + traffic.target_frames)):
            traffic_snapshot = {
                "frame": peer.frames, "instructions": current.instructions,
                "traffic": traffic.status(peer.frames),
                "carrier": (dte_data_ready(dte_receive_state(current))
                            and "NO CARRIER" not in incoming),
                "call_state": current.bri.call_state,
                "dsp_error": current.mailbox.error,
                "pcm_underruns": current.mailbox.status()["pcm"]["rx_empty_frames"],
                "bearer_underruns": sum(current.dsc.bearer_underruns.values()),
                "serial": {str(base): channel.status() for base, channel in current.channels.items()},
                "peer_error": peer.error,
            }
        if stage == "done":
            received_text = ""  # Traffic verification keeps only a partial record.
        if (traffic is not None and len(transcript) >= 2
                and transcript[-1][1] == transcript[-2][1] == "received"
                and len(transcript[-1][2]) + len(transcript[-2][2]) <= 4096):
            count, direction, text = transcript.pop()
            transcript[-1] = (count, direction, transcript[-1][2] + text)
            cursor = len(transcript)  # Compact logs only after consuming the new bytes.

    def next_due(current: IsdnMachine) -> int | None:
        deadlines = []
        due = command_pump.next_due(current)
        if due is not None:
            deadlines.append(due)
        if stage == "guard":
            deadlines.append(connected_at + 20_000_000)
        if args.trace_digital_path:
            deadlines.append(next_trace)
        if post_call_due is not None:
            deadlines.append(post_call_due)
        if args.traffic_window_stop and traffic is not None and traffic.start_frame is not None:
            deadlines.append(traffic_next_poll)
        return min(deadlines) if deadlines else None

    pump.next_due = next_due

    machine = IsdnMachine(
        NacImage.load(args.image),
        with_dsp=True,
        profile=args.profile,
        bri=bri,
        flash_nvram=args.nvram.read_bytes() if args.nvram else None,
        serial_pump=pump,
        product_type=args.product_type,
    )
    negotiation = []
    if args.trace_negotiation:
        original_command = machine.mailbox.on_command

        def observe_command(tag: int, value: int) -> None:
            if tag in (0x42, 0x49, 0x53, 0x70, 0x71, 0x72, 0x04):
                negotiation.append({
                    "instructions": machine.instructions,
                    "tag": f"{tag:04x}", "value": f"{value:04x}",
                    "cpu_fields": {f"{offset:04x}": machine.uc.mem_read(0x26000 + offset, 1)[0]
                                   for offset in (0xD1EA, 0xD1B5, 0xD1D7, 0xD1DB, 0xE496)},
                })
            if original_command is not None:
                original_command(tag, value)

        machine.mailbox.on_command = observe_command
    try:
        result = machine.run(args.instructions).to_dict()
        if args.trace_digital_path:
            result["digital_path_trace"] = digital_trace
        if args.trace_negotiation:
            result["negotiation_trace"] = negotiation
        # The live S-register file, rather than ATSn?'s saved-profile view.
        result["working_s_registers"] = {
            str(number): machine.uc.mem_read(0x26000 + 0xD17B + number, 1)[0]
            for number in (54, 56, 58)
        }
    finally:
        peer.stop()
        machine.mailbox.close()
    result["serial_session"] = [
        {"instructions": count, "direction": direction, "text": text}
        for count, direction, text in transcript
    ]
    result["g711_peer"] = peer.status()
    terminal_handoff["final"] = dte_receive_state(machine)
    result["terminal_handoff"] = terminal_handoff
    if args.traffic_window_stop:
        result["traffic_snapshot"] = traffic_snapshot
        if traffic is not None:
            result["traffic_drain"] = {"received_records": traffic.received,
                                       "pending_bytes": len(traffic.pending),
                                       "errors": list(traffic.errors), "source": "streamed UART drain"}
    if args.trace_data_lanes:
        args.result.with_name("imodem-data-lanes.json").write_text(json.dumps(data_lanes) + "\n")
    if traffic is not None:
        result["traffic"] = traffic.status(peer.frames)
    args.result.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


def serial_text(result: dict[str, Any]) -> str:
    return "".join(
        event["text"] for event in result["serial_session"]
        if event["direction"] == "received"
    )


def connect_result(serial: str) -> str | None:
    match = re.search(r"(?:^|[\r\n])(CONNECT[^\r\n]*)\r\n", serial)
    return match.group(1) if match else None


def check_keepalive(result: dict[str, Any]) -> None:
    """Assert call survival, independently of eventual modem carrier training.

    The connect-fix control cleared after 220 media frames, following the
    two-second image-6 loader timeout. Require at least 250 exchanged frames
    and a completed overlay handshake so a short/idle run cannot pass.
    Socket errors at worker shutdown are deliberately checked through call
    state and guest events, since one worker necessarily finishes first.
    """
    assert result["error"] is None, result["error"]
    assert result["bri"]["call_state"] == "active", "ISDN call cleared"
    assert result["bri"]["media"]["channel"] == 1, "B1 disconnected"
    peer = result["g711_peer"]
    assert peer["frames"] * peer.get("frame_octets", 800) >= 250 * 800, (
        "run did not cross the old clearing window")
    assert "NO CARRIER" not in serial_text(result), "supervisor lost carrier"
    assert not any("DISCONNECT call reference 1" in event["event"]
                   for event in result["bri"]["events"]), "guest requested clearing"
    mailbox = result["mailbox"]
    assert mailbox["error"] is None, mailbox["error"]
    assert mailbox["pcm"]["rx_empty_frames"] == 0, "PCM receive underrun"
    assert any("cmd 0002:a000" in event for event in mailbox["timeline"]), "no V.8 handoff"
    assert not any("cmd 0083:0083" in event for event in mailbox["timeline"]), "DSP loader timed out"
    assert mailbox["overlay_writes"]["4"] >= 3, "call overlay never finished"
    # The final completion strobe may remain set while the datapump owns
    # foreground execution; clearing it here would hide the native signal.
    assert mailbox["dsp_status"] & 1 == 0, "overlay command still pending"


def stop_worker(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def main() -> int:
    args = arguments()
    if args.send_delay_frames < 0 or (args.send_delay_frames and args.link_diagnostics):
        raise ValueError("send delay must be nonnegative and cannot be mixed with escaped diagnostics")
    if args.traffic_seconds < 0 or not 1 <= args.traffic_size <= 4096:
        raise ValueError("traffic duration must be nonnegative; size must be 1..4096")
    if args.traffic_seconds and (args.link_diagnostics or args.post_call_diagnostics
                                or args.originate_send or args.answer_send):
        raise ValueError("traffic mode cannot be mixed with markers or escaped diagnostics")
    if args.worker:
        return run_side(args)

    output = (args.output or ROOT / "artifacts/imodem-pair").resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="courier-imodem-pair-") as temporary, ExitStack() as cleanup:
        path = str(Path(temporary) / "bearer.sock")
        processes = []
        for role in ("originate", "answer"):
            command = [
                sys.executable, str(Path(__file__).resolve()),
                "--worker", role, "--socket", path,
                "--image", str(args.image.resolve()),
                "--instructions", str(args.instructions),
                "--protocol", args.protocol,
                "--traffic-seconds", str(args.traffic_seconds),
                "--traffic-size", str(args.traffic_size),
                "--send-delay-frames", str(args.send_delay_frames),
                *(["--post-call-diagnostics"] if args.post_call_diagnostics else []),
                "--result", str(output / f"{role}.json"),
            ]
            if args.profile:
                command.append("--profile")
            if args.link_diagnostics:
                command.append("--link-diagnostics")
            if args.trace_negotiation:
                command.append("--trace-negotiation")
            if args.trace_digital_path:
                command.append("--trace-digital-path")
            if args.nvram:
                command.extend(["--nvram", str(args.nvram.resolve())])
            if args.prime_originate:
                command.append("--prime-originate")
            command.extend(["--originate-send", args.originate_send,
                            "--answer-send", args.answer_send,
                            "--settings", args.settings,
                            "--product-type", args.product_type,
                            "--internal-baud", str(args.internal_baud),
                            "--establish", args.establish])
            process = subprocess.Popen(command, cwd=ROOT)
            cleanup.callback(stop_worker, process)
            processes.append((role, process))
        failures = []
        for role, process in processes:
            code = process.wait()
            if code:
                failures.append(f"{role} exited {code}")
        if failures:
            raise RuntimeError(", ".join(failures))

    originate = json.loads((output / "originate.json").read_text())
    answer = json.loads((output / "answer.json").read_text())
    summary = {
        "image_sha256": hashlib.sha256(args.image.read_bytes()).hexdigest(),
        "traffic_seconds_requested": args.traffic_seconds,
        "protocol": args.protocol,
        "settings": args.settings,
        "product_type": args.product_type,
        "internal_baud": args.internal_baud if args.product_type == "internal" else None,
        "nvram": str(args.nvram.resolve()) if args.nvram else None,
        "establish": args.establish,
        "prime_originate": args.prime_originate,
        "originate": {
            "serial": serial_text(originate),
            "modem_connected": connect_result(serial_text(originate)) is not None,
            "connect_result": connect_result(serial_text(originate)),
            "working_s_registers": originate["working_s_registers"],
            "bri": originate.get("bri"),
            "g711_peer": originate["g711_peer"],
        },
        "answer": {
            "serial": serial_text(answer),
            "modem_connected": connect_result(serial_text(answer)) is not None,
            "connect_result": connect_result(serial_text(answer)),
            "working_s_registers": answer["working_s_registers"],
            "bri": answer.get("bri"),
            "g711_peer": answer["g711_peer"],
        },
    }
    summary["data_delivery"] = {
        "originate_to_answer": bool(args.originate_send and args.originate_send in serial_text(answer)),
        "answer_to_originate": bool(args.answer_send and args.answer_send in serial_text(originate)),
    }
    for role, result in (("originate", originate), ("answer", answer)):
        if "traffic" in result:
            summary[role]["traffic"] = result["traffic"]
    if args.traffic_seconds:
        summary["data_delivery"] = {
            "originate_to_answer": bool(answer["traffic"]["received_records"]
                                        and not answer["traffic"]["errors"]),
            "answer_to_originate": bool(originate["traffic"]["received_records"]
                                        and not originate["traffic"]["errors"]),
        }
    for role in ("originate", "answer"):
        summary[role]["x2_connected"] = bool(
            re.search(r"/x2(?:/|$)", summary[role]["connect_result"] or "", re.IGNORECASE)
        )
    traffic_failure = None
    if args.traffic_seconds:
        try:
            check_traffic({"originate": originate, "answer": answer})
            for result in (originate, answer):
                if "NO CARRIER" in serial_text(result):
                    raise AssertionError("supervisor lost carrier during traffic run")
        except AssertionError as exc:
            traffic_failure = str(exc)
        summary["traffic_verified"] = traffic_failure is None
        summary["traffic_failure"] = traffic_failure
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    if traffic_failure is not None:
        raise AssertionError(traffic_failure)
    if args.check_keepalive:
        for result in (originate, answer):
            check_keepalive(result)
    if args.check_connect:
        for role in ("originate", "answer"):
            if not summary[role]["modem_connected"]:
                raise RuntimeError(f"{role} did not establish modem carrier")
    if args.check_x2:
        for role in ("originate", "answer"):
            if not summary[role]["x2_connected"]:
                raise RuntimeError(f"{role} did not establish x2: {summary[role]['connect_result']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
