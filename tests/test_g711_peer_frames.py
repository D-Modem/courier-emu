from collections import deque
from types import SimpleNamespace

import pytest

from tools.probe_imodem_pair import G711Peer, HEADER


@pytest.mark.parametrize("frame_octets", [160, 800])
def test_peer_buffers_and_exchanges_exact_selected_frame_size(frame_octets):
    peer = G711Peer("unused", listen=False)
    peer.frame_octets = frame_octets
    sent = []
    peer.handle = SimpleNamespace(sendall=sent.append)
    replies = deque([HEADER.pack(frame_octets), b"\x7a" * frame_octets] * 2)

    def read(size):
        value = replies.popleft()
        assert len(value) == size
        return value

    peer._read = read
    assert peer.exchange(b"\xff" * (frame_octets - 1)) == b""
    assert not sent
    assert peer.exchange(b"\xff" * (frame_octets + 1)) == b"\x7a" * (frame_octets * 2)
    assert sent == [HEADER.pack(frame_octets) + b"\xff" * frame_octets] * 2
    assert peer.frames == 2
    assert peer.sent == peer.received == frame_octets * 2
    assert peer.status()["frame_octets"] == frame_octets
    assert not peer.pending and not replies
