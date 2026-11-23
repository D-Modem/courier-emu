"""Stream-verified traffic over the pair probe's two ordinary DTEs."""
from collections import deque
import re

from tools.imodem_traffic import Traffic, check_records, record


class AnalogTraffic:
    def __init__(self, seconds, size=512):
        self.streams = {"analog": Traffic("O", seconds, size),
                        "imodem": Traffic("A", seconds, size)}
        self.connect = {side: "" for side in self.streams}
        self.windows = {}
        self.failure = None
        self.stalls = {}
        self.progress = deque(maxlen=32)
        self.next_progress = 0

    def receive(self, side, text, frame):
        stream = self.streams[side]
        if stream.start_frame is None:
            self.connect[side] += text
            match = re.search(r'(?:^|[\r\n])CONNECT[^\r\n]*\r\n', self.connect[side])
            if not match:
                return
            text = self.connect[side][match.end():]
            self.connect[side] = self.connect[side][:match.end()]
            stream.start(frame)
        stream.receive(text, frame)

    def update(self, frame):
        for side, stream in self.streams.items():
            if stream.start_frame is None:
                continue
            if side not in self.windows:
                if stream.errors:
                    self.failure = f'{side}: corrupt or out-of-order traffic'
                elif frame - stream.start_frame - stream.last_rx_frame > 50:
                    self.stalls.setdefault(side, frame)
                if frame - stream.start_frame >= stream.target_frames:
                    self.windows[side] = stream.status(frame)

    def next_record(self, side, frame):
        if self.failure or not all(s.start_frame is not None for s in self.streams.values()):
            return None
        remote = 'imodem' if side == 'analog' else 'analog'
        # The parent observes both DTEs, so wait for this direction's actual
        # receiver. Using the local receive count couples the two directions
        # and can permit multiple outstanding records on an asymmetric call.
        return self.streams[side].next_record(
            frame, acknowledged_records=self.streams[remote].received)

    def done(self, frame):
        if self.failure:
            return True
        if len(self.windows) != 2:
            return False
        a, i = self.streams.values()
        drained = (a.sent == i.received and i.sent == a.received
                   and not a.pending and not i.pending)
        end = max(s.start_frame + s.target_frames for s in self.streams.values())
        return drained or frame >= end + 20

    def status(self, frame):
        return {"windows": dict(self.windows),
                "drain": {side: stream.status(frame) for side, stream in self.streams.items()},
                "throughput": {side: {
                    'record_bytes_per_second': window['target_receive_bytes_per_second'],
                    'payload_bytes_per_second': window['target_receive_bytes_per_second']
                        * window['record_size'] / len(record('O', 0, window['record_size'])),
                } for side, window in self.windows.items()},
                "connect": dict(self.connect), "failure": self.failure,
                "first_stall_frames": dict(self.stalls)}

    def verify(self, frame):
        if self.failure:
            raise AssertionError(self.failure)
        if len(self.windows) != 2:
            raise AssertionError('both endpoints must complete the traffic window')
        # Window timing is frozen at the requested duration; drain evidence
        # accounts for the final in-flight record without extending the window.
        from tools.imodem_traffic import check_record_window
        for side, window in self.windows.items():
            check_record_window(window, side)
        check_records({"originate": self.streams['analog'].status(frame),
                       "answer": self.streams['imodem'].status(frame)})
