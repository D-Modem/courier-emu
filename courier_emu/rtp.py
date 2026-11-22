"""RTP/G.711 framing, diagnostics and bounded timestamp-based playout."""
from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class RtpPacket:
    sequence: int
    timestamp: int
    ssrc: int
    payload_type: int
    payload: bytes


def parse_rtp(packet: bytes) -> RtpPacket:
    """Strip all RFC 3550 headers/padding; reject truncated or invalid packets."""
    if len(packet) < 12 or packet[0] >> 6 != 2:
        raise ValueError('invalid RTP fixed header')
    offset = 12 + 4 * (packet[0] & 15)
    if offset > len(packet):
        raise ValueError('truncated RTP CSRC list')
    if packet[0] & 0x10:
        if offset + 4 > len(packet):
            raise ValueError('truncated RTP extension header')
        words = int.from_bytes(packet[offset + 2:offset + 4], 'big')
        offset += 4 + words * 4
        if offset > len(packet):
            raise ValueError('truncated RTP extension data')
    end = len(packet)
    if packet[0] & 0x20:
        padding = packet[-1]
        if not padding or padding > end - offset:
            raise ValueError('invalid RTP padding')
        end -= padding
    return RtpPacket(int.from_bytes(packet[2:4], 'big'),
                     int.from_bytes(packet[4:8], 'big'),
                     int.from_bytes(packet[8:12], 'big'), packet[1] & 127,
                     packet[offset:end])


class RtpTransmitStats:
    def __init__(self):
        self.rebuffer_events = 0
        self.max_packet_gap_ms = 0.0
        self.max_deadline_late_ms = 0.0
        self.max_queue_samples = 0
        self.max_packets_per_flush = 0
        self.last_sent_at = None
        self.last_produced_at = None
        self.produced_samples = 0
        self.max_producer_gap_ms = 0.0
        self.rebuffer_history = []
        self.sent_samples = 0
        self.sample_clock_late_ms = 0.0
        self.max_sample_clock_late_ms = 0.0
        self._sample_clock_at = None
        self._sample_clock_samples = 0

    def produced(self, now, samples, queued):
        if not samples:
            return
        if self.last_produced_at is not None:
            self.max_producer_gap_ms = max(
                self.max_producer_gap_ms, max(0, now - self.last_produced_at) * 1000)
        self.last_produced_at = now
        self.produced_samples += samples
        self.max_queue_samples = max(self.max_queue_samples, queued)

    def rebuffered(self, now, queued):
        self.rebuffer_events += 1
        self.rebuffer_history.append({
            'monotonic_seconds': now, 'queued_samples': queued,
            'producer_gap_ms': (None if self.last_produced_at is None else
                                max(0, now - self.last_produced_at) * 1000),
        })
        del self.rebuffer_history[:-32]

    def sent(self, now, deadline, queued, samples=160):
        # Keep an independent reference: sender deadline re-anchoring must not
        # conceal accumulated sample-clock slip behind small per-packet gaps.
        if self.last_sent_at is None:
            self._sample_clock_at = deadline
            self._sample_clock_samples = 0
        expected = self._sample_clock_at + self._sample_clock_samples / 8000
        self.sample_clock_late_ms = (now - expected) * 1000
        self.max_sample_clock_late_ms = max(self.max_sample_clock_late_ms,
                                          self.sample_clock_late_ms)
        self._sample_clock_samples += samples
        self.sent_samples += samples
        if self.last_sent_at is not None:
            self.max_packet_gap_ms = max(self.max_packet_gap_ms,
                                          max(0, now - self.last_sent_at) * 1000)
        self.last_sent_at = now
        self.max_deadline_late_ms = max(self.max_deadline_late_ms,
                                        max(0, now - deadline) * 1000)
        self.max_queue_samples = max(self.max_queue_samples, queued)

    def status(self):
        return {name: value for name, value in vars(self).items()
                if not name.startswith('_') and name not in ('last_sent_at', 'last_produced_at')}


class RtpReceiveStats:
    """Observe arrival order without mistaking forward gaps for proven loss.

    A delayed/reordered packet can close a sequence gap. These are diagnostic
    events, not RTCP loss estimates. Duplicate suppression is safe; ordering
    and loss concealment still require a timestamp-based playout buffer.
    """
    def __init__(self):
        self.invalid_packets = 0
        self.duplicates = 0
        self.reordered_packets = 0
        self.sequence_gap_events = 0
        self.timestamp_jump_events = 0
        self.ssrc_changes = 0
        self.max_arrival_gap_ms = 0.0
        self.max_timestamp_gap_samples = 0
        self.reset_stream()

    def reset_stream(self):
        """A new call may reuse sequence numbers; retain diagnostic totals."""
        self._recent = deque(maxlen=256)
        self._seen = set()
        self._last = None
        self._last_time = None

    def observe(self, packet: RtpPacket, now: float) -> bool:
        """Return False for a repeated recent SSRC/sequence/timestamp identity."""
        key = (packet.ssrc, packet.sequence, packet.timestamp)
        if key in self._seen:
            self.duplicates += 1
            return False
        if len(self._recent) == self._recent.maxlen:
            self._seen.remove(self._recent[0])
        self._recent.append(key)
        self._seen.add(key)
        if self._last_time is not None:
            self.max_arrival_gap_ms = max(self.max_arrival_gap_ms,
                                          max(0, now - self._last_time) * 1000)
        self._last_time = now
        previous = self._last
        if previous is not None:
            if previous.ssrc != packet.ssrc:
                self.ssrc_changes += 1
            else:
                sequence_delta = (packet.sequence - previous.sequence + 32768) % 65536 - 32768
                timestamp_delta = (packet.timestamp - previous.timestamp + 2**31) % 2**32 - 2**31
                if sequence_delta < 0:
                    self.reordered_packets += 1
                    return True  # Keep the high-water mark for subsequent packets.
                if sequence_delta > 1:
                    self.sequence_gap_events += 1
                gap = timestamp_delta - len(previous.payload)
                if gap:
                    self.timestamp_jump_events += 1
                    self.max_timestamp_gap_samples = max(self.max_timestamp_gap_samples, gap)
        self._last = packet
        return True

    def status(self):
        return {name: value for name, value in vars(self).items() if not name.startswith('_')}


class RtpPlayout:
    """Fixed-delay, 8-kHz playout; no carrier synthesis or loss concealment.

    The SDP endpoint owns the stream; its first nonempty packet pins the SSRC
    until reset. Timestamps, not sequence numbers, place samples. Missing
    samples become explicitly counted codec idle octets at their deadlines.
    Far-future timestamps and overlaps are rejected rather than resetting the
    clock. A stalled consumer fails closed instead of allocating unbounded PCM.
    """
    def __init__(self, *, delay_samples=480, capacity_samples=16000, silence=0xff):
        if not 0 <= delay_samples < capacity_samples:
            raise ValueError('invalid RTP playout delay/capacity')
        self.delay_samples = delay_samples
        self.capacity_samples = capacity_samples
        self.silence = silence
        self.rejected_sources = 0
        self.rejected_ssrc = 0
        self.late_packets = 0
        self.out_of_window_packets = 0
        self.overlap_packets = 0
        self.missing_samples = 0
        self.played_samples = 0
        self.reset_stream()

    def reset_stream(self):
        self._ssrc = None
        self._endpoint = None
        self._timestamp = None
        self._deadline = None
        self._cursor = 0
        self._samples = {}

    def push(self, packet, source, expected_source, now):
        if expected_source is None or source != expected_source:
            self.rejected_sources += 1
            return False
        if self._endpoint is not None and source != self._endpoint:
            self.rejected_sources += 1
            return False
        if self._ssrc is not None and packet.ssrc != self._ssrc:
            self.rejected_ssrc += 1
            return False
        if not packet.payload:
            return False
        if len(packet.payload) > self.capacity_samples:
            self.out_of_window_packets += 1
            return False
        if self._timestamp is None:
            self._ssrc = packet.ssrc
            self._endpoint = source
            self._timestamp = packet.timestamp
            self._deadline = now + self.delay_samples / 8000
        start = (packet.timestamp - self._timestamp + 2**31) % 2**32 - 2**31
        # The first datagram need not be the earliest one. During priming,
        # allow an earlier timestamp to extend the head without changing the
        # wall-clock deadline or exceeding the bounded timestamp window.
        if start < 0 and self._cursor == 0 and now < self._deadline:
            shift = -start
            if shift + max(self._samples, default=-1) + 1 > self.capacity_samples:
                self.out_of_window_packets += 1
                return False
            self._samples = {i + shift: value for i, value in self._samples.items()}
            self._timestamp = packet.timestamp
            start = 0
        # Even before drain(), samples whose deadlines passed cannot be revived.
        due = max(0, int((now - self._deadline) * 8000))
        if start < max(self._cursor, due):
            self.late_packets += 1
            return False
        end = start + len(packet.payload)
        if end > self._cursor + self.capacity_samples:
            self.out_of_window_packets += 1
            return False
        if any(i in self._samples for i in range(start, end)):
            self.overlap_packets += 1
            return False
        self._samples.update(enumerate(packet.payload, start))
        return True

    def drain(self, now):
        if self._deadline is None:
            return b''
        end = max(0, int((now - self._deadline) * 8000))
        count = max(0, end - self._cursor)
        if count > self.capacity_samples:
            raise RuntimeError('RTP playout consumer stalled beyond bounded capacity')
        result = bytearray()
        for i in range(self._cursor, end):
            value = self._samples.pop(i, None)
            if value is None:
                self.missing_samples += 1
                value = self.silence
            result.append(value)
        self._cursor = max(self._cursor, end)
        self.played_samples += count
        return bytes(result)

    def owns(self, source, ssrc):
        return self._endpoint == source and self._ssrc == ssrc

    def status(self):
        return dict(delay_samples=self.delay_samples,
                    capacity_samples=self.capacity_samples,
                    buffered_samples=len(self._samples),
                    rejected_sources=self.rejected_sources,
                    rejected_ssrc=self.rejected_ssrc,
                    late_packets=self.late_packets,
                    out_of_window_packets=self.out_of_window_packets,
                    overlap_packets=self.overlap_packets,
                    missing_samples=self.missing_samples,
                    played_samples=self.played_samples)
