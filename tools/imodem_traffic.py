"""Bounded, deterministic full-duplex traffic for firmware pair soak tests.

ASCII records survive either 7-bit or 8-bit DTE framing. No received data,
carrier, acknowledgements or modem state is injected. One outstanding record
per direction bounds the UART queue while exercising LAPM across the call.
"""
from hashlib import sha256
from math import ceil, isfinite


def record(role: str, sequence: int, size: int) -> str:
    seed = f"courier:{role}:{sequence}".encode("ascii")
    body = "".join(sha256(seed + i.to_bytes(4, "little")).hexdigest()
                   for i in range((size + 63) // 64))[:size]
    return f"~CEMU:{role}:{sequence:08x}:{body}\r\n"


class Traffic:
    def __init__(self, role: str, seconds: float, size: int = 512):
        if (role not in ("O", "A") or not isfinite(seconds) or seconds <= 0
                or not 1 <= size <= 4096):
            raise ValueError("invalid traffic role, duration or record size")
        self.role = role
        self.remote = "A" if role == "O" else "O"
        self.target_frames = ceil(seconds * 10)
        self.size = size
        self.start_frame = None
        self.sent = self.received = self.sent_bytes = self.received_bytes = 0
        self.pending = ""
        self.errors = []
        self.last_rx_frame = self.max_gap_frames = 0
        self.largest_gaps = []
        self.gap_frames_total = 0
        self.target_received_bytes = 0
        self.sent_hash = sha256()
        self.received_hash = sha256()

    def start(self, frame: int):
        self.start_frame = frame

    def receive(self, text: str, frame: int):
        if self.errors:
            return
        self.pending += text
        elapsed = frame - self.start_frame
        while self.pending:
            expected = record(self.remote, self.received, self.size)
            count = min(len(expected), len(self.pending))
            if self.pending[:count] != expected[:count]:
                self.errors.append({"sequence": self.received,
                                    "expected": expected[:80],
                                    "actual": self.pending[:80], "frame": elapsed})
                self.pending = ""
                return
            if len(self.pending) < len(expected):
                return
            self.pending = self.pending[len(expected):]
            self.received += 1
            self.received_bytes += len(expected)
            self.received_hash.update(expected.encode('ascii'))
            gap = elapsed - self.last_rx_frame
            self.max_gap_frames = max(self.max_gap_frames, gap)
            self.gap_frames_total += gap
            self.largest_gaps.append({"sequence": self.received - 1,
                                      "start_frame": self.last_rx_frame,
                                      "end_frame": elapsed, "gap_frames": gap})
            # Keep the earliest ten worst gaps, not an unbounded per-record log.
            self.largest_gaps.sort(key=lambda item: (-item["gap_frames"], item["sequence"]))
            del self.largest_gaps[10:]
            if elapsed <= self.target_frames:
                self.target_received_bytes += len(expected)
            self.last_rx_frame = elapsed

    def next_record(self, frame: int, *, acknowledged_records: int | None = None) -> str | None:
        acknowledged = self.received if acknowledged_records is None else acknowledged_records
        if (self.start_frame is None or self.errors or
                frame - self.start_frame >= self.target_frames or
                self.sent > acknowledged):
            return None
        value = record(self.role, self.sent, self.size)
        self.sent += 1
        self.sent_bytes += len(value)
        self.sent_hash.update(value.encode('ascii'))
        return value

    def status(self, frame: int) -> dict:
        elapsed = 0 if self.start_frame is None else frame - self.start_frame
        return {"target_frames": self.target_frames, "elapsed_frames": elapsed,
                "record_size": self.size, "sent_records": self.sent,
                "received_records": self.received, "sent_bytes": self.sent_bytes,
                "received_bytes": self.received_bytes, "pending_bytes": len(self.pending),
                "sent_sha256": self.sent_hash.hexdigest(),
                "received_sha256": self.received_hash.hexdigest(),
                "last_rx_frame": self.last_rx_frame, "max_gap_frames": self.max_gap_frames,
                "largest_receive_gaps": [dict(gap) for gap in self.largest_gaps],
                "mean_receive_gap_frames": (self.gap_frames_total / self.received
                                            if self.received else None),
                "target_received_bytes": self.target_received_bytes,
                "target_receive_bytes_per_second": (self.target_received_bytes * 10 /
                                                     self.target_frames),
                "errors": list(self.errors), "started": self.start_frame is not None}


def check_traffic(sides: dict, max_gap_frames: int = 50):
    """Require sustained verified traffic, allowing one final in-flight record."""
    for role in ("originate", "answer"):
        side = sides[role]
        if side["error"] or side["mailbox"]["error"]:
            raise AssertionError(f"{role}: CPU/DSP failure")
        if side["bri"]["call_state"] != "active":
            raise AssertionError(f"{role}: call cleared")
        if side["mailbox"]["pcm"]["rx_empty_frames"]:
            raise AssertionError(f"{role}: PCM underrun")
        if any(channel.get("output_dropped", 0) for channel in side.get("serial", {}).values()):
            raise AssertionError(f"{role}: host terminal output dropped")
        if any(channel.get("overruns", 0) for channel in side.get("serial", {}).values()):
            raise AssertionError(f"{role}: UART overrun")
    check_records({role: side["traffic"] for role, side in sides.items()}, max_gap_frames)


def check_records(sides: dict, max_gap_frames: int = 50):
    """Validate matched record streams independently of either board model."""
    for role, remote in (("originate", "answer"), ("answer", "originate")):
        traffic, far = sides[role], sides[remote]
        check_record_window(traffic, role, max_gap_frames)
        outstanding = far["sent_records"] - traffic["received_records"]
        if not 0 <= outstanding <= 1:
            raise AssertionError(f"{role}: missing or unsolicited records")
        if outstanding == 0 and traffic["pending_bytes"]:
            raise AssertionError(f"{role}: unexpected trailing bytes")


def check_record_window(traffic: dict, role: str, max_gap_frames: int = 50):
    """Check duration and activity within one endpoint's measured window."""
    if not traffic["started"] or traffic["elapsed_frames"] < traffic["target_frames"]:
        raise AssertionError(f"{role}: insufficient connected bearer duration")
    if traffic["errors"]:
        raise AssertionError(f"{role}: corrupt or out-of-order traffic: {traffic['errors']}")
    if traffic["received_records"] < 10:
        raise AssertionError(f"{role}: insufficient verified traffic")
    if (traffic["max_gap_frames"] > max_gap_frames or
            traffic["last_rx_frame"] < traffic["target_frames"] - max_gap_frames):
        raise AssertionError(f"{role}: traffic stalled")
