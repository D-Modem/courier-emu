#!/usr/bin/env python3
"""Exercise asymmetric x2 with a digital Quad server and an analog Courier client."""
import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from tools.probe_imodem_pair import connect_result, stop_worker
from tools.quad_directional_link import inspect_directional_link

ROOT = Path(__file__).resolve().parents[1]


def check_asymmetric(summary, analog, quad):
    for role in ("analog", "quad"):
        if not re.search(r"\bx2(?:client|server)?\b", summary[f"{role}_connect"] or "", re.I):
            raise AssertionError(f"{role} did not negotiate asymmetric x2")
    if quad["x2_status_inputs"]["8954"] & 4:
        raise AssertionError("symmetric x2 is not an asymmetric control")
    if analog["error"] or analog["dsp_bridge"]["error"] or quad["error"]:
        raise AssertionError("CPU/DSP execution failed")
    if not all(summary["payload_checks"].values()):
        raise AssertionError("bidirectional payloads were not delivered")
    if not int(quad["peek"]["8311"], 16) & 4 or not analog["online_mode"]:
        raise AssertionError("carrier cleared")
    if (quad["endpoint"]["pcm_rx_underruns"] or quad["host_serial"]["overruns"]
            or analog["dsp_bridge"].get("line_service", {}).get("rx_empty_connected", 0)):
        raise AssertionError("connected PCM underrun or UART overrun")
    requested = summary.get("line_frames_requested", 0)
    if requested and (quad["endpoint"]["media_peer"]["frames"] < requested
                      or analog["dsp_bridge"]["line"]["frames"] < requested):
        raise AssertionError("shared media duration was not completed")
    if "NO CARRIER" in summary["analog_terminal"] or "NO CARRIER" in quad["terminal"]:
        raise AssertionError("guest lost carrier")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--analog", type=Path,
                        default=ROOT / "dumps/courier-board-21210-capture-403/courier-board.rom")
    parser.add_argument("--analog-instructions", type=int, default=450_000_000)
    parser.add_argument("--quad-instructions", type=int, default=250_000_000)
    parser.add_argument("--line-frames", type=int, default=3000,
                        help="shared termination boundary; 3000 frames is 60 seconds at 20 ms")
    parser.add_argument("--frame-ms", type=int, choices=(20, 100), default=20)
    parser.add_argument("--analog-send", default="ANALOG-TO-QUAD-482619")
    parser.add_argument("--quad-send", default="QUAD-TO-ANALOG-731954")
    parser.add_argument("--check-x2", action="store_true")
    parser.add_argument("--check-x2-v34", action="store_true",
                        help="also require reciprocal DSP rates and the stock V.34 upstream receiver")
    args = parser.parse_args()
    if args.line_frames <= 0:
        raise ValueError("line frame limit must be positive")
    if not args.analog_send or not args.quad_send or args.analog_send == args.quad_send:
        raise ValueError("use distinct, nonempty payloads")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "COURIER_LINE_FRAME_MS": str(args.frame_ms), "COURIER_LINE_DIGITAL": "1"}
    with tempfile.TemporaryDirectory(prefix="quad-analog-") as directory, ExitStack() as cleanup:
        socket = str(Path(directory) / "line.sock")
        commands = [
            [sys.executable, "-m", "courier_emu", "run", str(args.analog.resolve()),
             "--instructions", str(args.analog_instructions), "--line-link", socket,
             "--line-listen", "--line-frames", str(args.line_frames), "--with-dsp", "--nvram-fixture", "idsdl403",
             "--board-id", "7", "--dip-preset", "default", "--tick-ms", "5",
             "--at", "ATX1S27=1S58=48&M5&K0DT5551234", "--serial-input-after", "5000000",
             "--send-after-connect", args.analog_send, "--summary"],
            [sys.executable, str(ROOT / "tools/probe_quad_call.py"), "--answer", "--enable-v8",
             "--line-socket", socket, "--line-frames", str(args.line_frames), "--terminal-init", "Q0V1&A3&B0S76=133S81=32",
             "--feature-mask", "0x20", "--send", args.quad_send, "--trace-negotiation",
             "--instructions", str(args.quad_instructions), "--output", str(output / "quad")],
        ]
        workers = []
        for role, command in zip(("analog", "quad"), commands):
            stdout = cleanup.enter_context((output / f"{role}.log").open("w"))
            stderr = cleanup.enter_context((output / f"{role}-stderr.log").open("w"))
            process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=stdout, stderr=stderr)
            cleanup.callback(stop_worker, process)
            workers.append((role, process))
        failures = [f"{role} exited {process.returncode}" for role, process in workers if process.wait()]
        if failures:
            raise RuntimeError(", ".join(failures))
    analog = json.loads((output / "analog.log").read_text())
    quad = json.loads((output / "quad/results.json").read_text())
    terminal = bytes(b & 127 for b in bytes.fromhex(analog["serial_hex"])).decode("ascii", "replace")
    summary = {"topology": "digital Quad server / analog Courier client", "frame_ms": args.frame_ms,
               "line_frames_requested": args.line_frames,
               "line_frames": {"quad": quad["endpoint"]["media_peer"]["frames"],
                               "analog": analog["dsp_bridge"]["line"]["frames"]},
               "analog_connect": connect_result(terminal), "quad_connect": connect_result(quad["terminal"]),
               "analog_terminal": terminal, "quad_terminal": quad["terminal"],
               "quad_x2_status": quad["x2_status_inputs"],
               "payload_checks": {"analog_to_quad": args.analog_send in quad["terminal"],
                                  "quad_to_analog": args.quad_send in terminal}}
    try:
        check_asymmetric(summary, analog, quad)
    except AssertionError as exc:
        summary.update(x2_data_verified=False, verification_failure=str(exc))
    else:
        summary.update(x2_data_verified=True, verification_failure=None)
    if args.check_x2_v34:
        try:
            if not summary['x2_data_verified']:
                raise AssertionError(summary['verification_failure'])
            summary['directional_link'] = inspect_directional_link(analog, quad)
        except AssertionError as exc:
            summary.update(x2_v34_verified=False, verification_failure=str(exc))
        else:
            summary['x2_v34_verified'] = True
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    if ((args.check_x2 and not summary["x2_data_verified"])
            or (args.check_x2_v34 and not summary['x2_v34_verified'])):
        raise RuntimeError(summary["verification_failure"])


if __name__ == "__main__":
    main()
