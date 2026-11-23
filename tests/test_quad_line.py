from courier_emu.quad_line import QuadLinePeer
from courier_emu.line import CALL_RINGING, CALL_ANSWERED
from courier_emu.sip import linear_to_ulaw


class Line:
    digital = connected = True
    closed = peer_ringing = False
    peer_call_state = CALL_RINGING
    peer_off_hook = True
    frames = 0

    def __init__(self):
        self.sent = []

    def exchange(self, frame):
        self.sent.append(frame)
        self.frames += 1

    def receive_audio(self):
        return [1000] * len(self.sent[-1].samples)

    def status(self):
        return {"frames": self.frames}

    def close(self):
        self.closed = True
        self.connected = False


def test_highway_start_does_not_answer_or_inject_carrier():
    line = Line()
    peer = QuadLinePeer(line)
    peer.start()
    assert not peer.answered
    assert peer.ringing
    assert peer.exchange(b"\xff" * peer.frame_octets) == b"\xff" * peer.frame_octets
    assert not line.sent[-1].off_hook
    assert line.sent[-1].call_state == CALL_RINGING
    assert not any(line.sent[-1].samples)


def test_answer_bridges_codec_samples_with_one_existing_transit_reserve():
    line = Line()
    peer = QuadLinePeer(line, record=True)
    peer.start()
    peer.answer()
    assert peer.exchange(b"\xff" * (peer.frame_octets - 1)) == b""
    reply = peer.exchange(b"\xff")
    expected = linear_to_ulaw(peer._clip(1000 * peer.from_line))
    assert reply == bytes((expected,)) * peer.frame_octets
    assert len(reply) == peer.frame_octets  # No second idle reserve from BearerLineLink.
    assert peer.capture == reply
    assert line.sent[-1].off_hook
    assert line.sent[-1].call_state == CALL_ANSWERED
    assert peer.frames == 1
    assert peer.status()["frame_octets"] == peer.frame_octets
    peer.stop()
    assert line.closed
