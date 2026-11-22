"""Quad digital highway to an analog Courier's existing socket line.

Reuse the exchange codec and level calibration from the I-modem line bridge.
No negotiation, carrier, or terminal data is synthesized here.
"""
from types import SimpleNamespace

from .bearer_line import BearerLineLink, LINE_FRAME_SAMPLES, PCMU_SILENCE
from .line import CALL_RINGING


class QuadLinePeer(BearerLineLink):
    frame_octets = LINE_FRAME_SAMPLES

    def __init__(self, line, *, record=False):
        super().__init__(line)
        self.capture = bytearray()
        self.record = record
        # QuadC50Endpoint already supplies the initial transit reserve.
        self._primed = True
        self.error = None

    @property
    def frames(self):
        return self.line.frames

    @property
    def ringing(self):
        return self.line.peer_ringing or self.line.peer_call_state == CALL_RINGING

    def start(self):
        # Opening the highway must not pretend that the guest answered a call.
        self.poll()

    def answer(self):
        # Called only when the original firmware accepts the chassis answer.
        if not self.answered:
            self.answered = True
            self.events.append(f"the Quad accepted the chassis answer at frame {self.frames}: off hook")

    def exchange(self, octets):
        self._pending.extend(octets)
        reply = bytearray()
        while len(self._pending) >= self.frame_octets and self.line.connected:
            frame = bytes(self._pending[:self.frame_octets])
            del self._pending[:self.frame_octets]
            incoming = bytearray()
            dsc = SimpleNamespace(queue_bearer=lambda channel, data: incoming.extend(data))
            self._exchange(dsc, 1, frame)
            # Before answer the physical highway carries idle codewords.
            reply.extend(incoming or bytes((PCMU_SILENCE,)) * len(frame))
        if self.line.closed:
            self.error = "analog line closed"
        if self.record:
            self.capture.extend(reply)
        return bytes(reply)

    def stop(self):
        self.close()

    def status(self):
        return {**super().status(), "frames": self.frames,
                "frame_octets": self.frame_octets, "error": self.error}
