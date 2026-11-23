"""Read-only traffic evidence for a Quad/I-modem pair's bounded soak window."""
import argparse
from collections import deque
import json
from pathlib import Path
import re

from tools.imodem_traffic import Traffic, check_record_window
from tools.probe_imodem_pair import connect_result


class QuadTraffic:
    def __init__(self, seconds, size, progress_path=None):
        self.traffic = Traffic("A", seconds, size)
        self.cursor = 0
        self.connect_text = ""
        self.snapshot = None
        self.progress_path = Path(progress_path) if progress_path else None
        self.history = deque(maxlen=32)
        self.next_progress = 0

    def service(self, machine, peer, endpoint):
        traffic = self.traffic
        if getattr(peer, "frame_octets", 800) != 800:
            raise ValueError("traffic currently requires 100-ms media frames")
        incoming = bytes(b & 127 for b in machine.serial[self.cursor:]).decode("ascii", "replace")
        self.cursor = len(machine.serial)
        if self.snapshot is not None:
            # Preserve window health, but account for real in-flight data
            # during drain. The two CONNECT results need not share a frame.
            if not peer.error and not self.snapshot.get("failure"):
                traffic.receive(incoming, peer.frames)
            if (peer.error or self.snapshot.get("failure")
                    or peer.frames >= traffic.start_frame + traffic.target_frames + 20):
                machine.request_stop()
            return
        if traffic.start_frame is None:
            self.connect_text += incoming
            if connect_result(self.connect_text) is None:
                return
            # CONNECT is complete; everything after its CRLF is application data.
            start = self.connect_text.index("CONNECT")
            end = self.connect_text.index("\r\n", start) + 2
            incoming = self.connect_text[end:]
            self.connect_text = ""
            traffic.start(peer.frames)
        traffic.receive(incoming, peer.frames)
        online = bool(machine.uc.mem_read(0x8311, 1)[0] & 4)
        if online and machine.uart.receive_enabled and not machine.serial_rx:
            value = traffic.next_record(peer.frames)
            if value is not None:
                machine.serial_rx.extend(value.encode("ascii"))
        elapsed = peer.frames - traffic.start_frame
        failure = None
        if getattr(machine, "serial_truncated", False):
            failure = "Quad terminal capture filled before the traffic window completed"
        elif traffic.errors:
            failure = "corrupt or out-of-order Quad traffic"
        elif elapsed - traffic.last_rx_frame > 50:
            failure = "Quad receive traffic stalled for over five bearer seconds"
        elif peer.error:
            failure = "media peer closed before the traffic window completed"
        elif not online:
            failure = "Quad carrier cleared during traffic window"
        if peer.frames >= self.next_progress or failure:
            self.next_progress = peer.frames + 20
            self.history.append({
                "frame": peer.frames, "instructions": machine.instructions,
                "traffic": traffic.status(peer.frames), "uart": machine.uart.status(),
                "input_queued": len(machine.serial_rx),
                "cpu": {f"{a:04x}": int.from_bytes(machine.uc.mem_read(a, n), "little")
                        for a, n in ((0x81f8, 2), (0x81f4, 2), (0x8311, 1), (0xff64, 2))},
            })
            if self.progress_path:
                self.progress_path.write_text(json.dumps(list(self.history), indent=2) + "\n")
        if failure or peer.frames >= traffic.start_frame + traffic.target_frames:
            self.snapshot = {
                "frame": peer.frames, "instructions": machine.instructions,
                "traffic": traffic.status(peer.frames), "carrier": online,
                "uart": machine.uart.status(), "endpoint": endpoint.status(),
                "dsp_error": endpoint.core.state().get("error") if endpoint.core else "no core",
                "failure": failure,
            }
            if failure:
                machine.request_stop()


def check_quad_traffic(imodem, quad):
    caller = imodem.get("traffic_snapshot")
    answer = quad.get("traffic_snapshot")
    if answer and answer.get("failure"):
        raise AssertionError(answer["failure"])
    if not caller or not answer:
        raise AssertionError("both endpoints must complete the requested traffic window")
    if imodem["error"] or quad["error"]:
        raise AssertionError("CPU execution failed")
    if (caller["dsp_error"] or answer["dsp_error"] or caller["peer_error"]
            or answer["endpoint"]["media_peer"]["error"]):
        raise AssertionError("DSP or media failure during traffic window")
    if (not caller["carrier"] or not answer["carrier"]
            or caller["call_state"] != "active"):
        raise AssertionError("carrier lost during traffic window")
    if (caller["pcm_underruns"] or caller.get("bearer_underruns", 0)
            or answer["endpoint"]["pcm_rx_underruns"]):
        raise AssertionError("PCM underrun during traffic window")
    if answer["uart"]["overruns"] or any(
            channel.get("overruns", 0) or channel.get("output_dropped", 0)
            for channel in caller["serial"].values()):
        raise AssertionError("terminal byte loss during traffic window")
    windows = {"originate": caller["traffic"], "answer": answer["traffic"]}
    drains = {"originate": drained_records(imodem, "O", caller["traffic"]),
              "answer": drained_records(quad, "A", answer["traffic"])}
    for role, far in (("originate", "answer"), ("answer", "originate")):
        window, drain = windows[role], drains[role]
        check_record_window(window, role)
        if drain["errors"] or drain["received_records"] < window["received_records"]:
            raise AssertionError(f"{role}: corrupt or incomplete drain evidence")
        sent = windows[far]["sent_records"]
        outstanding = sent - drain["received_records"]
        if not 0 <= outstanding <= 1:
            raise AssertionError(f"{role}: missing or unsolicited records after drain")
        if (outstanding == 0 and drain["pending_bytes"]
                or window["received_records"] >= sent and window["pending_bytes"]):
            raise AssertionError(f"{role}: unexpected trailing bytes")


def drained_records(report, role, window):
    """Use streamed drain accounting, or replay a historical full UART capture.

    Timing/health still come exclusively from the measured window snapshot.
    This does not fabricate bytes or infer completion of a partial record.
    """
    if report.get("traffic_drain") is not None:
        return report["traffic_drain"]
    texts = ([(name, report.get(name, "")) for name in ("serial_a", "serial_internal", "serial_b")]
             if role == "O" else [("terminal", report.get("terminal", ""))])
    for name, text in texts:
        match = re.search(r"(?:^|[\r\n])CONNECT[^\r\n]*\r\n", text)
        if match:
            channel = report.get("serial", {}).get(name.removeprefix("serial_"), {})
            if role == "O" and channel.get("capture_truncated", False):
                raise AssertionError("full UART capture unavailable for drain replay")
            replay = Traffic(role, 1, window["record_size"])
            replay.start(0)
            replay.receive(text[match.end():], 0)
            return {"received_records": replay.received, "pending_bytes": len(replay.pending),
                    "errors": list(replay.errors), "source": "full UART capture replay"}
    raise AssertionError("missing terminal drain evidence")


def main():
    parser = argparse.ArgumentParser(description="Verify saved Quad/I-modem traffic evidence without changing it")
    parser.add_argument("imodem", type=Path)
    parser.add_argument("quad", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    caller = json.loads(args.imodem.read_text())
    answer = json.loads(args.quad.read_text())
    verdict = {"imodem_source": str(args.imodem), "quad_source": str(args.quad)}
    try:
        check_quad_traffic(caller, answer)
    except AssertionError as exc:
        verdict.update(traffic_verified=False, verification_failure=str(exc))
    else:
        verdict.update(traffic_verified=True, verification_failure=None,
                       windows={"imodem": caller["traffic_snapshot"]["traffic"],
                                "quad": answer["traffic_snapshot"]["traffic"]},
                       drain={"imodem": drained_records(caller, "O", caller["traffic_snapshot"]["traffic"]),
                              "quad": drained_records(answer, "A", answer["traffic_snapshot"]["traffic"])})
    text = json.dumps(verdict, indent=2) + "\n"
    if args.output:
        args.output.write_text(text)
    print(text, end="")
    if not verdict["traffic_verified"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
