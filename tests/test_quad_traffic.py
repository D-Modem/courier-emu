from copy import deepcopy
from types import SimpleNamespace
from collections import deque

import pytest

from tools.imodem_traffic import record
from tools.quad_traffic import QuadTraffic, check_quad_traffic, drained_records


def reports():
    stats = {"started": True, "target_frames": 1800, "elapsed_frames": 1800,
             "received_records": 50, "sent_records": 50, "errors": [],
             "pending_bytes": 0, "last_rx_frame": 1790, "max_gap_frames": 30}
    caller = {"traffic_snapshot": {"traffic": deepcopy(stats), "carrier": True,
              "call_state": "active", "dsp_error": None, "pcm_underruns": 0,
              "bearer_underruns": 0,
              "serial": {}, "peer_error": None}, "error": None}
    quad = {"traffic_snapshot": {"traffic": deepcopy(stats), "carrier": True,
            "uart": {"overruns": 0}, "dsp_error": None,
            "endpoint": {"pcm_rx_underruns": 0, "media_peer": {"error": None}}}, "error": None}
    for side in (caller, quad):
        side['traffic_drain'] = {'received_records': 50, 'pending_bytes': 0, 'errors': []}
    return caller, quad


def offset_windows():
    caller, quad = reports()
    for side, received, sent, pending, last in ((caller, 70, 71, 74, 1777),
                                               (quad, 71, 72, 0, 1765)):
        side.pop('traffic_drain')
        side['traffic_snapshot']['traffic'].update(
            target_frames=1800, elapsed_frames=1800, record_size=64,
            received_records=received, sent_records=sent, pending_bytes=pending,
            last_rx_frame=last)
    caller['serial_a'] = ('\r\nCONNECT 9600/ARQ/V34/LAPM\r\n'
                          + ''.join(record('A', n, 64) for n in range(71))
                          + record('A', 71, 64)[:59])
    quad['terminal'] = ('\r\nCONNECT 9600/ARQ\r\n'
                        + ''.join(record('O', n, 64) for n in range(71)))
    return caller, quad


def test_offset_connect_windows_use_real_drain_not_two_different_end_times():
    caller, quad = offset_windows()
    check_quad_traffic(caller, quad)
    drain = drained_records(caller, 'O', caller['traffic_snapshot']['traffic'])
    assert drain['received_records'] == 71 and drain['pending_bytes'] == 59
    assert drain['source'] == 'full UART capture replay'


@pytest.mark.parametrize('failure', ['missing_record', 'corrupt_prefix', 'truncated_capture'])
def test_drain_replay_does_not_waive_loss_corruption_or_missing_capture(failure):
    caller, quad = offset_windows()
    if failure == 'missing_record':
        caller['serial_a'] = ('\r\nCONNECT 9600/ARQ\r\n'
                              + ''.join(record('A', n, 64) for n in range(70)))
    elif failure == 'corrupt_prefix':
        caller['serial_a'] += '!'
    else:
        caller['serial'] = {'a': {'capture_truncated': True}}
    with pytest.raises(AssertionError):
        check_quad_traffic(caller, quad)


def test_accepts_completed_healthy_duplex_window():
    check_quad_traffic(*reports())


@pytest.mark.parametrize("side,field,value", [
    (0, "traffic_snapshot", None), (1, "traffic_snapshot", None),
    (0, "error", "CPU failure"), (1, "error", "CPU failure")])
def test_incomplete_or_failed_execution_cannot_pass(side, field, value):
    pair = reports()
    pair[side][field] = value
    with pytest.raises(AssertionError):
        check_quad_traffic(*pair)


@pytest.mark.parametrize("side,field,value", [
    (0, "carrier", False), (1, "carrier", False),
    (0, "dsp_error", "bad opcode"), (1, "dsp_error", "no core"),
    (0, "peer_error", "closed"), (0, "pcm_underruns", 1),
    (0, "bearer_underruns", 1),
    (0, "call_state", "null"),
    (0, "serial", {"a": {"overruns": 1}}),
    (0, "serial", {"a": {"output_dropped": 1}}),
    (1, "uart", {"overruns": 1}),
    (1, "endpoint", {"pcm_rx_underruns": 1, "media_peer": {"error": None}}),
    (1, "endpoint", {"pcm_rx_underruns": 0, "media_peer": {"error": "closed"}}),
])
def test_window_health_is_required(side, field, value):
    pair = reports()
    pair[side]["traffic_snapshot"][field] = value
    with pytest.raises(AssertionError):
        check_quad_traffic(*pair)


@pytest.mark.parametrize("field,value", [("errors", ["corrupt"]),
    ("max_gap_frames", 51), ("received_records", 2), ("elapsed_frames", 1799),
    ("sent_records", 52), ("pending_bytes", 1), ("last_rx_frame", 1700)])
def test_record_integrity_duration_and_stalls_are_required(field, value):
    pair = reports()
    pair[0]["traffic_snapshot"]["traffic"][field] = value
    with pytest.raises(AssertionError):
        check_quad_traffic(*pair)


class Memory:
    def mem_read(self, address, size):
        if address == 0x8311:
            return b"\x04"
        return bytes(size)


def test_quad_traffic_waits_for_complete_connect_and_preserves_first_record():
    stream = QuadTraffic(1, 16)
    peer = SimpleNamespace(frames=100, error=None)
    machine = SimpleNamespace(serial=bytearray(b"\r\nOK\r\n\r\nCON"),
                              serial_rx=deque(), uc=Memory(), instructions=0,
                              uart=SimpleNamespace(receive_enabled=True, status=lambda: {"overruns": 0}))
    endpoint = SimpleNamespace(status=lambda: {}, core=SimpleNamespace(state=lambda: {}))
    stream.service(machine, peer, endpoint)
    assert not machine.serial_rx
    assert stream.traffic.start_frame is None
    machine.serial.extend(b"NECT 33600/ARQ\r\n" + record("O", 0, 16).encode())
    stream.service(machine, peer, endpoint)
    assert stream.traffic.start_frame == 100
    assert stream.traffic.received == 1
    assert bytes(machine.serial_rx) == record("A", 0, 16).encode()
    assert not stream.traffic.errors
    peer.frames = 110
    stream.service(machine, peer, endpoint)
    assert stream.snapshot["traffic"]["elapsed_frames"] == 10
    snapshot = deepcopy(stream.snapshot)
    peer.frames = 111
    machine.serial.extend(record("O", 1, 16).encode())
    stream.service(machine, peer, endpoint)
    assert stream.traffic.received == 2  # Consume real drain data, not just the window.
    assert stream.snapshot == snapshot
    stopped = []
    machine.request_stop = lambda: stopped.append(True)
    peer.error = "closed"
    machine.serial.extend(b"\r\nNO CARRIER\r\n")
    stream.service(machine, peer, endpoint)
    assert not stream.traffic.errors  # Intentional peer termination is outside the window.
    assert stream.snapshot == snapshot
    assert stopped == [True]
