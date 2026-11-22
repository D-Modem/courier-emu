#!/usr/bin/env python3
"""Run a chassis-provisioned Quad answerer against an original I-modem caller."""
import argparse
from contextlib import ExitStack
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from tools.probe_imodem_pair import connect_result, serial_text, stop_worker
from tools.inspect_quad_v42 import inspect as inspect_v42
from tools.quad_traffic import check_quad_traffic, drained_records

ROOT = Path(__file__).resolve().parents[1]


def check_pair(summary, imodem, quad, *, require_data=False, require_x2=False):
    if "initialization_completed_at" in quad and quad["initialization_completed_at"] is None:
        raise RuntimeError("Quad terminal initialization did not complete before chassis setup")
    if not summary["imodem_connect"] or not summary["quad_connect"]:
        raise RuntimeError("both modems must report CONNECT")
    if imodem["error"] or imodem["mailbox"]["error"] or quad["error"]:
        raise RuntimeError("CPU/DSP error during Quad/I-modem call")
    if require_x2:
        for role in ("imodem", "quad"):
            if not re.search(r"\bx2(?:client|server|symmetric)?\b", summary[f"{role}_connect"], re.I):
                raise RuntimeError(f"{role} CONNECT does not identify x2 modulation")
    if require_data:
        if not int(quad["peek"]["8311"], 16) & 4:
            raise RuntimeError("Quad cleared the modem call")
        if not all(summary["payload_checks"].get(direction)
                   for direction in ("imodem_to_quad", "quad_to_imodem")):
            raise RuntimeError("bidirectional terminal payloads were not delivered")
        if quad["endpoint"]["pcm_rx_underruns"] or imodem["mailbox"]["pcm"]["rx_empty_frames"]:
            raise RuntimeError("PCM underrun during data exchange")
        if quad.get("host_serial", {}).get("overruns", 0) or any(
                channel.get("overruns", 0) or channel.get("output_dropped", 0)
                for channel in imodem.get("serial", {}).values()):
            raise RuntimeError("terminal bytes lost during data exchange")


def verification_results(summary, imodem, quad, *, require_connect=False,
                         require_data=False, require_x2=False):
    """Keep modulation and payload evidence independent; any requested failure is fatal."""
    result = {"verification_failure": None}
    for name, requested, options in (
            ("connect_verified", require_connect or require_data or require_x2, {}),
            ("data_verified", require_data, {"require_data": True}),
            ("x2_verified", require_x2, {"require_x2": True})):
        if not requested:
            continue
        try:
            check_pair(summary, imodem, quad, **options)
        except RuntimeError as exc:
            result[name] = False
            if result["verification_failure"] is None:
                result["verification_failure"] = str(exc)
        else:
            result[name] = True
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--quad-instructions", type=int, default=100_000_000)
    parser.add_argument("--imodem-instructions", type=int, default=500_000_000)
    parser.add_argument("--settings", default="S54=0S58=43&M5&K0")
    parser.add_argument("--quad-terminal-init", default="Q0V1")
    parser.add_argument("--quad-online-byte-interval", type=int, default=100_000)
    parser.add_argument("--quad-dsp-slice-cycles", type=int, choices=(64, 512), default=64)
    parser.add_argument("--quad-modem-mode", type=int, choices=range(6), default=2,
                        help="003f wire enum: 2 selects normal/error control (firmware mode 4)")
    parser.add_argument("--quad-parameter-0042", type=int, choices=range(3), default=1)
    parser.add_argument("--quad-feature-mask", type=lambda value: int(value, 0), choices=range(256),
                        help="provision chassis 01f2; 0x20 enables local x2 availability")
    parser.add_argument("--check-connect", action="store_true")
    parser.add_argument("--check-x2", action="store_true",
                        help="require both CONNECT results to identify x2, not V.34 fallback")
    parser.add_argument("--trace-dsp", action="store_true")
    parser.add_argument("--trace-data-lanes", action="store_true")
    parser.add_argument("--snapshot-frame", type=int, action="append", default=[])
    parser.add_argument("--snapshot-read-range", help="include data reads/writes between two hex addresses, e.g. bd0:bdf")
    parser.add_argument("--trace-negotiation", action="store_true",
                        help="record the caller's original x2 capability and rate-mask commands")
    parser.add_argument("--post-call-diagnostics", action="store_true",
                        help="ask the I-modem for ATI6 after NO CARRIER")
    parser.add_argument("--imodem-send", default="", help="caller DTE payload after CONNECT")
    parser.add_argument("--quad-send", default="", help="Quad DTE payload after CONNECT")
    parser.add_argument("--imodem-send-delay-frames", type=int, default=0,
                        help="delay caller payload by this many 100-ms frames after CONNECT")
    parser.add_argument("--traffic-seconds", type=float, default=0,
                        help="verify numbered duplex records for this many connected bearer seconds")
    parser.add_argument("--traffic-size", type=int, default=64,
                        help="payload characters per record (1..4096)")
    parser.add_argument("--check-data", action="store_true",
                        help="require both distinct payloads at the opposite terminal")
    args = parser.parse_args()
    if (not math.isfinite(args.traffic_seconds) or args.traffic_seconds < 0
            or not 1 <= args.traffic_size <= 4096):
        raise ValueError("traffic duration must be finite/nonnegative and size 1..4096")
    if args.traffic_seconds and (args.imodem_send or args.quad_send or args.check_data
                                 or args.post_call_diagnostics or args.imodem_send_delay_frames):
        raise ValueError("traffic cannot be mixed with markers, send delay or post-call diagnostics")
    if args.traffic_seconds and int(os.environ.get("COURIER_LINE_FRAME_MS", "100")) != 100:
        raise ValueError("traffic currently requires 100-ms media frames")
    if args.traffic_seconds:
        # Instruction ceilings are failure bounds; the workers stop after the
        # measured traffic window and a short drain, not at an estimated time.
        args.quad_instructions = max(args.quad_instructions, int((args.traffic_seconds + 60) * 4_000_000))
        args.imodem_instructions = max(args.imodem_instructions, int((args.traffic_seconds + 60) * 18_000_000))
    if args.quad_online_byte_interval <= 0:
        raise ValueError("online byte interval must be positive")
    if args.imodem_send_delay_frames < 0:
        raise ValueError("send delay must be nonnegative")
    if args.check_data and (not args.imodem_send or not args.quad_send
                            or args.imodem_send == args.quad_send):
        raise ValueError("data checking requires two distinct nonempty payloads")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="quad-imodem-") as temporary, ExitStack() as cleanup:
        socket_path = str(Path(temporary) / "bearer.sock")
        commands = [
            [sys.executable, str(ROOT / "tools/probe_imodem_pair.py"),
             "--worker", "originate", "--socket", socket_path,
             "--image", str(ROOT / "Ie030002.nac"),
             "--nvram", str(ROOT / "artifacts/imodem-pair-x2-full-rate-routed-20261002/nvram-230400-switch2.sav"),
             "--protocol", "x2", "--settings", args.settings,
             "--originate-send", args.imodem_send,
             "--send-delay-frames", str(args.imodem_send_delay_frames),
             "--instructions", str(args.imodem_instructions),
             "--result", str(output / "imodem.json")],
            [sys.executable, str(ROOT / "tools/probe_quad_call.py"),
             "--answer", "--enable-v8", "--socket", socket_path,
             "--terminal-init", args.quad_terminal_init, "--send", args.quad_send,
             "--online-byte-interval", str(args.quad_online_byte_interval),
             "--dsp-slice-cycles", str(args.quad_dsp_slice_cycles),
             "--modem-mode", str(args.quad_modem_mode),
             "--parameter-0042", str(args.quad_parameter_0042),
             "--instructions", str(args.quad_instructions), "--output", str(output / "quad")],
        ]
        if args.traffic_seconds:
            for command in commands:
                command.extend(("--traffic-seconds", str(args.traffic_seconds),
                                "--traffic-size", str(args.traffic_size)))
            commands[0].append("--traffic-window-stop")
        if args.trace_dsp:
            commands[1].append("--trace-dsp")
        if args.trace_data_lanes:
            for command in commands:
                command.append("--trace-data-lanes")
        if args.snapshot_read_range:
            for command in commands:
                command.extend(("--snapshot-read-range", args.snapshot_read_range))
        for frame in args.snapshot_frame:
            for command in commands:
                command.extend(("--snapshot-frame", str(frame)))
        if args.quad_feature_mask is not None:
            commands[1].extend(("--feature-mask", str(args.quad_feature_mask)))
        if args.post_call_diagnostics:
            commands[0].append("--post-call-diagnostics")
        if args.trace_negotiation:
            for command in commands:
                command.append("--trace-negotiation")
        workers = []
        for role, command in zip(("imodem", "quad"), commands):
            log = cleanup.enter_context((output / f"{role}.log").open("w"))
            process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
            cleanup.callback(stop_worker, process)
            workers.append((role, process))
        failures = []
        for role, worker in workers:
            code = worker.wait()
            if code:
                failures.append(f"{role} exited {code}")
        if failures:
            raise RuntimeError(", ".join(failures))
    imodem = json.loads((output / "imodem.json").read_text())
    quad = json.loads((output / "quad/results.json").read_text())
    summary = {"settings": args.settings,
               "quad_modem_mode_wire": args.quad_modem_mode,
               "quad_terminal_init": args.quad_terminal_init,
               "quad_feature_mask_input": args.quad_feature_mask,
               "quad_working_modem_mode": int(quad["peek"]["a895"], 16),
               "imodem_send_delay_frames": args.imodem_send_delay_frames,
               "imodem_connect": connect_result(serial_text(imodem)),
               "imodem_error": imodem["error"],
               "imodem_serial": serial_text(imodem),
               "imodem_peer": imodem["g711_peer"],
               "quad_counts": quad["counts"], "quad_peek": quad["peek"],
               "quad_endpoint": quad["endpoint"], "quad_error": quad["error"],
               "quad_terminal": quad["terminal"],
               "quad_connect": connect_result(quad["terminal"]),
               "payload_checks": {
                   "imodem_to_quad": bool(args.imodem_send and args.imodem_send in quad["terminal"]),
                   "quad_to_imodem": bool(args.quad_send and args.quad_send in serial_text(imodem))}}
    if args.trace_dsp and (output / "quad/data-lanes.json").exists():
        summary["quad_v42_inspection"] = inspect_v42(
            json.loads((output / "quad/data-lanes.json").read_text()))
    summary.update(verification_results(summary, imodem, quad,
                                       require_connect=args.check_connect,
                                       require_data=args.check_data, require_x2=args.check_x2))
    if args.traffic_seconds:
        summary["traffic_seconds_requested"] = args.traffic_seconds
        summary["traffic_snapshots"] = {"imodem": imodem.get("traffic_snapshot"),
                                        "quad": quad.get("traffic_snapshot")}
        try:
            check_pair(summary, imodem, quad)
            check_quad_traffic(imodem, quad)
            summary["traffic_drain"] = {
                "imodem": drained_records(imodem, "O", imodem["traffic_snapshot"]["traffic"]),
                "quad": drained_records(quad, "A", quad["traffic_snapshot"]["traffic"])}
        except (AssertionError, RuntimeError) as exc:
            summary["traffic_verified"] = False
            summary["traffic_failure"] = str(exc)
            summary["verification_failure"] = summary["verification_failure"] or str(exc)
        else:
            summary["traffic_verified"] = True
            summary["traffic_failure"] = None
    failure = summary["verification_failure"]
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    if failure:
        raise RuntimeError(failure)


if __name__ == "__main__":
    main()
