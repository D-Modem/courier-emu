#!/usr/bin/env python3
"""Exercise QF060003 chassis commands through the card's real RAM mailbox.

Writes only chassis-owned input window bytes, never call flags, DSP program
words or firmware function pointers. The controller supplies flash/RAM first.
"""
import argparse
from collections import Counter, deque
import hashlib
import json
from pathlib import Path
import struct
from types import SimpleNamespace

from courier_emu.machine import CourierMachine
from courier_emu.nvram import CourierNvram, IDSDL403_NVRAM
from courier_emu.quad_board import QuadBoard
from courier_emu.quad_c50 import QuadC50Endpoint
from courier_emu.quad_image import QuadImage
from tools.probe_imodem_pair import connect_result
from tools.quad_traffic import QuadTraffic
from tools.quad_directional_link import V34_RX, V34_RX_END, receive_code_sha256

ROOT = Path(__file__).resolve().parents[1]
WATCH = {0xed4d0: "window_poll", 0xed4f8: "window_copy", 0xf4672: "dispatch",
         0xf47bc: "type1", 0xf4856: "allowlist", 0xf4895: "parameter_lookup",
         0xf7b13: "session_arm", 0xf7c74: "line_setting", 0xf7ca5: "bearer_setting",
         0xf3c1f: "handler_call", 0xf8f2a: "chassis_answer", 0xdd868: "answer_callback",
         0xc7cfc: "answer", 0xcab68: "answer_overlay_poll",
         0xcee5f: "overlay_request", 0xf7b62: "session_watchdog",
         0xf3691: "line_personality_probe",
         0xc89ad: "receive_callback_reset_call", 0xc8fbe: "receive_callback_reset_clear",
         0xc5577: "receive_async_init", 0xc55af: "receive_async_select",
         0xc55ec: "receive_special_select", 0xd2b57: "receive_callback_restore",
         0xd592d: "receive_framing_install"}
# Every bank dispatch, before the indirect call through the guest's 839d.
RECEIVE_DISPATCH = {0xd4f2e: 0, 0xd4f4b: 1, 0xd4f68: 2,
                    0xd4f85: 3, 0xd4fa2: 4, 0xd4fc2: 5}


def chassis_frame(parameter: int, value: int | None, sequence: int,
                  kind: int = 1) -> bytes:
    body = struct.pack("<H", parameter)
    if value is not None:
        body += bytes((1, value))
    return struct.pack("<4H", 0, 0, len(body) + 2, kind | ((sequence & 1) << 14)) + body


def terminal_initialization_ready(machine, *, expected_results=1):
    """Read the real command completion before posting any chassis requests."""
    output_start = machine.quad_terminal.output_start or 0
    text = bytes(byte & 127 for byte in machine.serial[output_start:]).decode("ascii", "replace")
    if "\r\nERROR\r\n" in text:
        raise RuntimeError("Quad terminal initialization returned ERROR")
    return (not machine.serial_rx and not machine.uart.pending and not machine.uart.receive_unread
            and int.from_bytes(machine.uc.mem_read(0x81f8, 2), "little") == 0x91e6
            and text.count("\r\nOK\r\n") >= expected_results)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=ROOT / "docs/x2/Qf060003.zip")
    parser.add_argument("--instructions", type=int, default=12_000_000)
    parser.add_argument("--without-dsp", action="store_true")
    parser.add_argument("--dsp-slice-cycles", type=int, choices=(64, 512), default=64,
                        help="runtime native service batch; sample clocks and download pacing are unchanged")
    parser.add_argument("--answer", action="store_true")
    parser.add_argument("--terminal-init", default="Q0V1",
                        help="original firmware AT initialization before chassis requests")
    parser.add_argument("--send", default="", help="DTE payload queued after firmware CONNECT")
    parser.add_argument("--online-byte-interval", type=int, default=100_000,
                        help="instruction spacing for online DTE bytes; command timing is unchanged")
    parser.add_argument("--traffic-seconds", type=float, default=0)
    parser.add_argument("--traffic-size", type=int, default=64)
    parser.add_argument("--modem-mode", type=int, choices=range(6), default=2,
                        help="003f wire enum: 2 selects firmware mode 4 (normal/error control); 0 disables it")
    parser.add_argument("--parameter-0042", type=int, choices=range(3), default=1,
                        help="type-1 0042 parameter (1 is the startup profile default)")
    parser.add_argument("--feature-mask", type=lambda value: int(value, 0), choices=range(256),
                        help="provision chassis feature 01f2; bit 0x20 enables local x2 availability")
    parser.add_argument("--enable-v8", action="store_true",
                        help="clear S54 bits 0 and 6 through recovered type-1 parameters")
    parser.add_argument("--snapshot-frame", type=int, action="append", default=[])
    parser.add_argument("--snapshot-read-range")
    parser.add_argument("--trace-data-lanes", action="store_true",
                        help="capture packed CPU/DSP data words without full DSP memory tracing")
    parser.add_argument("--trace-negotiation", action="store_true",
                        help="record original x2 status reports and save the final DSP image")
    parser.add_argument("--trace-dsp", action="store_true",
                        help="save received wire bytes and periodic DSP data snapshots")
    parser.add_argument("--socket", help="connect a byte-exact G711Peer Unix socket")
    parser.add_argument("--line-socket", help="connect an analog Courier LineLink socket")
    parser.add_argument("--line-frames", type=int, help="stop at this common analog line frame boundary")
    parser.add_argument("--line-mode", choices=("digital", "analog", "unprovisioned"),
                        default="digital", help="chassis-owned b4b5 line-availability field")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    traffic = QuadTraffic(args.traffic_seconds, args.traffic_size,
                          args.output / "traffic-progress.json") if args.traffic_seconds else None
    if args.online_byte_interval <= 0:
        raise ValueError("online byte interval must be positive")
    if args.line_frames is not None and (not args.line_socket or args.line_frames <= 0):
        raise ValueError("line frame limit requires an analog line and a positive frame count")
    if args.socket and args.line_socket:
        raise ValueError("choose a digital peer or an analog line, not both")
    if traffic and (not args.socket or args.send or not args.answer):
        raise ValueError("traffic requires a media peer and answer mode, without marker sends")
    args.output.mkdir(parents=True, exist_ok=True)
    board = QuadBoard()
    controller_image = QuadImage.controller(args.archive)
    controller = CourierMachine(controller_image, quad_board=board)
    boot = controller.run(8_000_000)
    if boot.error:
        raise RuntimeError(boot.error)
    board.flush()
    image = QuadImage.modem(bytes(board.flash[0]), bytes(board.ram[0]))
    # A persistent chassis identity input, not a pre-reset RAM fixture or a
    # direct write to the guest's 878a personality selector.
    line_kind = None if args.line_mode == "unprovisioned" else (2 if args.line_mode == "digital" else 1)
    peer = None
    if args.socket or args.line_socket:
        if args.without_dsp or args.line_mode != "digital":
            raise ValueError("a media peer requires a digital line and DSP")
        from tools.probe_imodem_pair import G711Peer
        class RecordingPeer(G711Peer):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.capture = bytearray()

            def exchange(self, octets):
                incoming = super().exchange(octets)
                if args.trace_dsp:
                    self.capture.extend(incoming)
                return incoming

        if args.line_socket:
            from courier_emu.line import LineLink
            from courier_emu.quad_line import QuadLinePeer
            peer = QuadLinePeer(LineLink(args.line_socket, digital=True), record=args.trace_dsp)
        else:
            peer = RecordingPeer(args.socket, listen=False)
    endpoint = None if args.without_dsp else QuadC50Endpoint(
        media_peer=peer, trace_data_lanes=args.trace_dsp or args.trace_data_lanes,
        data_lane_limit=131_072, service_slice_cycles=args.dsp_slice_cycles)
    if endpoint:
        endpoint.connect_digital_call(law="mu")
    machine = CourierMachine(image, quad_terminal=True, tick_ms=5, quad_c50=endpoint,
                             quad_line_kind=line_kind,
                             nvram=CourierNvram(data=bytearray(IDSDL403_NVRAM)),
                             serial_input=("AT" + args.terminal_init + "\r").encode("ascii"), max_io_events=100,
                             peek={a: f"{a:04x}" for a in
                                   (0x9d1e, 0x9d1c, 0xa895, 0xa897, 0x9c2e,
                                    0x9c50, 0x9c72, 0x9c40, 0x8b3e, 0xb4b0,
                                    0x81f8, 0x9cb3, 0x9ca6, 0x8311, 0x82f7,
                                    0x878a, 0xb4b5, 0xa863)})
    machine.quad_terminal.online_interval = args.online_byte_interval
    # Independent host sequence starts at zero; no reading/modifying guest
    # sequence state. Arm, configure operating mode (2 -> firmware value 4),
    # and parameter 0042 (retain its startup profile value by default).
    commands = [(0x80e6, None, 1), (0x003f, args.modem_mode, 1),
                (0x0042, args.parameter_0042, 1)]
    if args.feature_mask is not None:
        commands.append((0x01f2, args.feature_mask, 1))
    if args.enable_v8:
        commands.extend(((0x014c, 0, 1), (0x015e, 0, 1)))
    if args.answer:
        commands.append((0x8094, None, 3))
    counts = Counter()
    line_probes = []
    frames = []
    sequence = 0
    next_frame = 4_000_000
    answer_sent = False
    snapshots = []
    receive_calls = deque(maxlen=96)
    receive_callback_counts = Counter()
    next_snapshot = 4_000_000
    payload_sent_at = None
    next_terminal_poll = 10_000_000
    initialization_completed_at = None
    next_init_poll = 4_000_000
    next_traffic_poll = 0
    negotiation = deque(maxlen=512)
    negotiation_flags = set()
    from tools.dsp_snapshots import DspSnapshots
    dsp_snapshots = DspSnapshots(args.output / "dsp-snapshots", args.snapshot_frame,
                                 tuple(int(a, 16) for a in args.snapshot_read_range.split(":"))
                                 if args.snapshot_read_range else None)

    def observe(pc):
        nonlocal sequence, next_frame, answer_sent, next_snapshot, payload_sent_at, next_terminal_poll
        nonlocal initialization_completed_at, next_init_poll, next_traffic_poll
        if args.line_frames is not None and peer.frames >= args.line_frames:
            machine.request_stop()
            return
        if dsp_snapshots.targets and endpoint and peer and peer.frames >= dsp_snapshots.targets[0]:
            dsp_snapshots.poll(endpoint.core, peer.frames, machine.instructions)
        if traffic and machine.instructions >= next_traffic_poll:
            next_traffic_poll = machine.instructions + 10_000
            traffic.service(machine, peer, endpoint)
        if args.line_socket and pc == 0xc7d3f:
            peer.answer()
        if args.trace_negotiation and pc == 0xd5076:
            regs = machine._x86_const
            flags = machine.uc.reg_read(regs.UC_X86_REG_AX)
            if flags not in negotiation_flags and len(negotiation_flags) < 16 and endpoint and endpoint.core:
                negotiation_flags.add(flags)
                for space in ("program", "data"):
                    getter = getattr(endpoint.core, space)
                    (args.output / f"negotiation-{flags:04x}-{space}.bin").write_bytes(
                        struct.pack("<65536H", *(getter(a) for a in range(65536))))
            negotiation.append({
                "instructions": machine.instructions,
                "frame": peer.frames if peer else None,
                "flags": machine.uc.reg_read(regs.UC_X86_REG_AX),
                "reply_tag": endpoint._reply.get(0x5e) if endpoint else None,
                "cpu": {f"{a:04x}": int.from_bytes(machine.uc.mem_read(a, n), "little")
                        for a, n in ((0x8954, 1), (0x8312, 1), (0xa879, 1), (0xa87e, 1))},
                "dsp": {f"{a:04x}": endpoint.core.data(a) for a in
                        (0x039a, 0x039b, 0x039f, 0xffd9, 0xffdd, 0xffdf)}
                        if endpoint and endpoint.core else None,
            })
        if args.send and payload_sent_at is None and machine.instructions >= next_terminal_poll:
            next_terminal_poll = machine.instructions + 10_000
            output_start = machine.quad_terminal.output_start or 0
            text = bytes(byte & 127 for byte in machine.serial[output_start:]).decode("ascii", "replace")
            if connect_result(text) is not None:
                machine.serial_rx.extend(args.send.encode("ascii"))
                payload_sent_at = machine.instructions
        if args.trace_dsp and pc in RECEIVE_DISPATCH:
            regs = machine._x86_const
            cs = machine.uc.reg_read(regs.UC_X86_REG_CS)
            callback = int.from_bytes(machine.uc.mem_read(0x839d, 2), "little")
            receive_callback_counts[f"{cs:04x}:{callback:04x}"] += 1
            # Retain the tail across all six banks, not the first 96 calls
            # (which are usually idle ff bytes before ODP even arrives).
            receive_calls.append({"pc": pc, "instructions": machine.instructions,
                                  "bank": RECEIVE_DISPATCH[pc], "cs": cs,
                                  "cx": machine.uc.reg_read(regs.UC_X86_REG_CX),
                                  "ax": machine.uc.reg_read(regs.UC_X86_REG_AX),
                                  "callback": callback, "callback_physical": cs * 16 + callback,
                                  "character_callback": int.from_bytes(
                                      machine.uc.mem_read(0x8399, 2), "little")})
        if (args.trace_dsp and endpoint and endpoint.core
                and machine.instructions >= next_snapshot):
            core = endpoint.core
            snapshots.append({"instructions": machine.instructions,
                              "state": core.state(), "host_serial": machine.uart.status(),
                              "cpu": {f"{a:04x}": int.from_bytes(machine.uc.mem_read(a, n), "little")
                                      for a, n in ((0x83a6, 1), (0x8399, 2), (0x839d, 2), (0x839f, 2),
                                                   (0x8206, 2), (0x8208, 2), (0x8311, 1),
                                                   (0x81f8, 1), (0x9c7b, 1), (0x893a, 2),
                                                   (0x8220, 2), (0x88fc, 2), (0x88fa, 2),
                                                   (0x8515, 2), (0x8517, 2), (0x88f6, 2), (0x88f8, 2),
                                                   (0x8838, 1), (0x8954, 1), (0x895f, 2),
                                                   (0xa879, 1), (0xa87e, 1))},
                              "data": {f"{a:04x}": core.data(a) for a in
                                       (*range(0x300, 0x400), *range(0xb60, 0xc00),
                                        *range(0xff00, 0x10000))}})
            next_snapshot += 1_000_000
        if pc in WATCH:
            counts[WATCH[pc]] += 1
        if pc == 0xf3691:
            line_probes.append({"instructions": machine.instructions,
                                "b4b5": machine.uc.mem_read(0xb4b5, 1)[0],
                                "878a": machine.uc.mem_read(0x878a, 1)[0]})
        if machine.instructions < next_frame:
            return
        if commands:
            if initialization_completed_at is None:
                if machine.instructions < next_init_poll:
                    return
                next_init_poll = machine.instructions + 10_000
                if not terminal_initialization_ready(
                        machine, expected_results=args.terminal_init.count("\r") + 1):
                    return
                initialization_completed_at = machine.instructions
            if machine.uc.mem_read(0xb4b0, 1)[0] & 4:
                return
            if commands[0][0] == 0x8094 and args.line_socket and not peer.ringing:
                return
            parameter, value, kind = commands.pop(0)
            frame = chassis_frame(parameter, value, sequence, kind)
            if parameter == 0x8094:
                answer_sent = True
            machine.uc.mem_write(0xb6de, frame)
            status = machine.uc.mem_read(0xb4b0, 1)[0]
            machine.uc.mem_write(0xb4b0, bytes(((status & ~0x80) | 0x14,)))
            frames.append({"instructions": machine.instructions,
                           "parameter": f"{parameter:04x}", "frame": frame.hex()})
            sequence ^= 1
            next_frame = machine.instructions + 1_000_000

    machine._code_observer = observe
    try:
        try:
            result = machine.run(args.instructions)
        except Exception as exc:
            result = SimpleNamespace(status="execution-error", error=str(exc),
                                     instructions=machine.instructions,
                                     peek={f"{a:04x}": bytes(machine.uc.mem_read(a, 1)).hex()
                                           for a in machine.peek})
        terminal = machine.quad_terminal
        report = {"status": result.status, "error": result.error,
                  "instructions": result.instructions,
                  "controller_sha256": hashlib.sha256(controller_image.data).hexdigest(),
                  "modem_flash_sha256": hashlib.sha256(image.data).hexdigest(),
                  "line_mode": args.line_mode, "line_probes": line_probes,
                  "line_kind_input": line_kind, "enable_v8": args.enable_v8,
                  "terminal_init": args.terminal_init,
                  "initialization_completed_at": initialization_completed_at,
                  "feature_mask_input": args.feature_mask,
                  "working_s_registers": {
                      str(register): machine.uc.mem_read(0xa82d + register, 1)[0]
                      for register in (54, 76, 81)},
                  "x2_status_inputs": {
                      f"{address:04x}": int.from_bytes(machine.uc.mem_read(address, size), "little")
                      for address, size in ((0x8838, 1), (0x8954, 1), (0x895f, 2),
                                            (0x9f56, 1), (0x89b2, 1), (0xa889, 1),
                                            (0xa8a2, 1), (0xa8a3, 1))},
                  "modem_mode_wire": args.modem_mode,
                  "working_modem_mode": int(result.peek["a895"], 16),
                  "frames": frames, "answer_sent": answer_sent,
                  "counts": dict(counts), "peek": result.peek,
                  "negotiation_trace": list(negotiation),
                  "traffic_snapshot": traffic.snapshot if traffic else None,
                  "traffic_drain": ({"received_records": traffic.traffic.received,
                                     "pending_bytes": len(traffic.traffic.pending),
                                     "errors": list(traffic.traffic.errors),
                                     "source": "streamed UART drain"} if traffic else None),
                  "traffic": traffic.traffic.status(peer.frames) if traffic else None,
                  "input_remaining": len(machine.serial_rx),
                  "payload_sent_at": payload_sent_at, "payload": args.send,
                  "online_byte_interval": args.online_byte_interval,
                  "host_serial": machine.uart.status(),
                  "terminal_bytes_received": terminal.received,
                  "terminal": bytes(b & 127 for b in machine.serial[
                      terminal.output_start or 0:]).decode("ascii", "replace"),
                  "endpoint": endpoint.status() if endpoint else None,
                  "dsp": endpoint.core.state() if endpoint and endpoint.core else None,
                  "serial": endpoint.core.serial_state() if endpoint and endpoint.core else None,
                  "dsp_cells": {f"{a:04x}": endpoint.core.data(a) for a in
                                (0x039f, 0xffd9, 0x039a, 0x039b, 0x0065, 0x0068)}
                                if endpoint and endpoint.core else None}
        if endpoint and endpoint.core:
            report['v34_receive_code_sha256'] = receive_code_sha256(
                [endpoint.core.program(a) for a in range(V34_RX, V34_RX_END)])
        if traffic and traffic.snapshot and traffic.snapshot.get("failure"):
            (args.output / "traffic-ram.bin").write_bytes(bytes(machine.uc.mem_read(0, 0x40000)))
        if endpoint:
            if args.trace_data_lanes:
                (args.output / "data-lanes.json").write_text(json.dumps(endpoint.data_lane_events) + "\n")
            (args.output / "tx.g711").write_bytes(endpoint.transmit_g711())
            if args.trace_negotiation and endpoint.core:
                (args.output / "negotiation-dsp-program.bin").write_bytes(struct.pack(
                    "<65536H", *(endpoint.core.program(a) for a in range(65536))))
                (args.output / "negotiation-dsp-data.bin").write_bytes(struct.pack(
                    "<65536H", *(endpoint.core.data(a) for a in range(65536))))
            if args.trace_dsp and endpoint.core:
                report["dsp_ports"] = endpoint.core.io_port_stats()
                report["dsp_io"] = {f"{a:04x}": endpoint.core.io(a)
                                    for a in range(0x50, 0x61)}
                report["io_event_total"] = endpoint.core.io_event_total()
                report["io_event_cursor"] = endpoint._event_cursor
                (args.output / "io-events.json").write_text(json.dumps(endpoint.core.io_events()) + "\n")
                (args.output / "data-lanes.json").write_text(json.dumps(endpoint.data_lane_events) + "\n")
                (args.output / "receive-calls.json").write_text(json.dumps(list(receive_calls)) + "\n")
                (args.output / "receive-callback-counts.json").write_text(
                    json.dumps(dict(receive_callback_counts), indent=2) + "\n")
                (args.output / "dsp-program.bin").write_bytes(struct.pack(
                    "<65536H", *(endpoint.core.program(a) for a in range(65536))))
                (args.output / "overlay-words.bin").write_bytes(struct.pack(
                    f"<{len(endpoint.program)}H", *endpoint.program))
                (args.output / "dsp-data.bin").write_bytes(struct.pack(
                    "<65536H", *(endpoint.core.data(a) for a in range(65536))))
                (args.output / "snapshots.json").write_text(json.dumps(snapshots) + "\n")
                (args.output / "dsp-data-events.json").write_text(
                    json.dumps(endpoint.core.data_events()) + "\n")
                if peer:
                    (args.output / "rx.g711").write_bytes(peer.capture)
        (args.output / "results.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
        if result.error:
            raise RuntimeError(result.error)
    finally:
        if endpoint and endpoint.core:
            endpoint.core.close()
        if peer:
            peer.stop()


if __name__ == "__main__":
    main()
