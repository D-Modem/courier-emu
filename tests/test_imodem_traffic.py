from copy import deepcopy

import pytest

from tools.imodem_traffic import Traffic, check_traffic, record


def test_bidirectional_fragmented_records_are_exact_and_bounded():
    caller, answer = Traffic("O", 2, 127), Traffic("A", 2, 127)
    caller.start(100)
    answer.start(100)
    for frame in range(100, 120):
        c, a = caller.next_record(frame), answer.next_record(frame)
        assert caller.next_record(frame) is None
        assert answer.next_record(frame) is None
        for offset in range(0, len(c), 7):
            answer.receive(c[offset:offset + 7], frame)
            caller.receive(a[offset:offset + 7], frame)
    assert caller.received == answer.received == 20
    assert caller.next_record(120) is None
    assert not caller.errors and not answer.errors


@pytest.mark.parametrize("bad", [record("O", 1, 32), record("A", 0, 32),
                                 record("O", 0, 32).replace("~", "!"),
                                 "\r\nNO CARRIER\r\n"])
def test_corruption_wrong_direction_and_sequence_fail(bad):
    traffic = Traffic("A", 120, 32)
    traffic.start(10)
    traffic.receive(bad, 20)
    assert traffic.errors
    assert traffic.next_record(20) is None


def test_coalesced_and_partial_records():
    traffic = Traffic("A", 120, 32)
    traffic.start(0)
    last = record("O", 2, 32)
    traffic.receive(record("O", 0, 32) + record("O", 1, 32) + last[:10], 5)
    assert traffic.received == 2 and len(traffic.pending) == 10
    traffic.receive(last[10:], 6)
    assert traffic.received == 3 and not traffic.pending


def sides():
    traffic = {"started": True, "target_frames": 1200, "elapsed_frames": 1210,
               "received_records": 500, "sent_records": 500, "errors": [],
               "pending_bytes": 0, "last_rx_frame": 1199, "max_gap_frames": 3}
    side = {"traffic": traffic, "error": None,
            "mailbox": {"error": None, "pcm": {"rx_empty_frames": 0}},
            "bri": {"call_state": "active"}}
    return {"originate": deepcopy(side), "answer": deepcopy(side)}


def test_checker_rejects_host_terminal_output_drops():
    pair = sides()
    pair["originate"]["serial"] = {"a": {"output_dropped": 1}}
    with pytest.raises(AssertionError, match="host terminal output dropped"):
        check_traffic(pair)


def test_checker_rejects_uart_overruns():
    pair = sides()
    pair["answer"]["serial"] = {"a": {"overruns": 1}}
    with pytest.raises(AssertionError, match="UART overrun"):
        check_traffic(pair)


def test_receive_gap_diagnostics_are_bounded_and_include_initial_wait():
    traffic = Traffic("A", 120, 32)
    traffic.start(100)
    frame = 100
    for sequence in range(20):
        frame += sequence + 1
        value = record("O", sequence, 32)
        traffic.receive(value[:5], frame - 1)
        traffic.receive(value[5:], frame)
    status = traffic.status(frame)
    assert status["max_gap_frames"] == 20
    assert status["mean_receive_gap_frames"] == 10.5
    assert status["largest_receive_gaps"] == [
        {"sequence": sequence, "start_frame": sequence * (sequence + 1) // 2,
         "end_frame": (sequence + 1) * (sequence + 2) // 2,
         "gap_frames": sequence + 1}
        for sequence in range(19, 9, -1)
    ]
    status["largest_receive_gaps"][0]["gap_frames"] = 999
    assert traffic.status(frame)["largest_receive_gaps"][0]["gap_frames"] == 20


def test_target_throughput_excludes_drain_and_idle_tail():
    traffic = Traffic("A", 2, 32)
    traffic.start(100)
    for sequence, frame in enumerate((101, 120, 121)):
        traffic.receive(record("O", sequence, 32), frame)
    status = traffic.status(1000)
    size = len(record("O", 0, 32))
    assert status["received_bytes"] == 3 * size
    assert status["target_received_bytes"] == 2 * size
    assert status["target_receive_bytes_per_second"] == size


def test_receive_gap_ties_keep_earliest_sequences():
    traffic = Traffic("A", 2, 32)
    traffic.start(100)
    for sequence in range(12):
        traffic.receive(record("O", sequence, 32), 101 + sequence)
    assert [gap["sequence"] for gap in traffic.status(112)["largest_receive_gaps"]] == list(range(10))


def test_checker_accepts_sustained_traffic_and_one_inflight_record():
    pair = sides()
    check_traffic(pair)
    pair["answer"]["traffic"]["sent_records"] += 1
    pair["originate"]["traffic"]["pending_bytes"] = 10
    check_traffic(pair)


@pytest.mark.parametrize("field,value", [("started", False), ("elapsed_frames", 1199),
                                         ("received_records", 1), ("errors", ["bad"]),
                                         ("max_gap_frames", 51), ("last_rx_frame", 10),
                                         ("sent_records", 502), ("pending_bytes", 1)])
def test_checker_rejects_false_success(field, value):
    pair = sides()
    pair["originate"]["traffic"][field] = value
    with pytest.raises(AssertionError):
        check_traffic(pair)
