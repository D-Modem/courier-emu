import ctypes
import subprocess
from pathlib import Path


ROOT = Path(__file__).parents[1]
LIFT = ROOT / "artifacts/x2-server-decomp-20261004/x2_server_lift.c"


def _lift(tmp_path):
    so = tmp_path / "lift.so"
    subprocess.run(["clang", "-shared", "-fPIC", "-Wall", "-Werror",
                    str(LIFT), "-o", str(so)], check=True)
    return ctypes.CDLL(str(so))


def _arrays():
    typ = ctypes.c_uint16 * 65536
    return typ(), typ(), typ()


class _TrainingRx(ctypes.Structure):
    _fields_ = [("state", ctypes.c_uint16), ("run_count", ctypes.c_uint16),
                ("zero_count", ctypes.c_uint16), ("pair_index", ctypes.c_uint16),
                ("bitmap", ctypes.c_uint16)]


def test_symmetric_training_receiver_accepts_probe_cycle(tmp_path):
    lib = _lift(tmp_path)
    lib.server_training_receiver_step.argtypes = [ctypes.POINTER(_TrainingRx), ctypes.c_uint16]
    lib.server_training_receiver_pair.argtypes = [ctypes.POINTER(_TrainingRx), ctypes.c_uint16]
    rx = _TrainingRx()
    for _ in range(7):
        assert lib.server_training_receiver_step(ctypes.byref(rx), 0x7E) == 0
    for _ in range(7):
        assert lib.server_training_receiver_step(ctypes.byref(rx), 0) == 0
    for i in range(128):
        assert lib.server_training_receiver_step(ctypes.byref(rx), i) == 1
        result = lib.server_training_receiver_pair(ctypes.byref(rx), 255 - i)
        assert result == (2 if i == 127 else 1)
    assert rx.pair_index == 0


def test_symmetric_training_receiver_records_tolerated_pair_bits(tmp_path):
    lib = _lift(tmp_path)
    lib.server_training_receiver_step.argtypes = [ctypes.POINTER(_TrainingRx), ctypes.c_uint16]
    lib.server_training_receiver_pair.argtypes = [ctypes.POINTER(_TrainingRx), ctypes.c_uint16]
    rx = _TrainingRx()
    for _ in range(7): lib.server_training_receiver_step(ctypes.byref(rx), 0x7F)
    for _ in range(7): lib.server_training_receiver_step(ctypes.byref(rx), 1)
    assert lib.server_training_receiver_step(ctypes.byref(rx), 1) == 1
    assert lib.server_training_receiver_pair(ctypes.byref(rx), 254) == 1
    assert rx.bitmap != 0


def test_symmetric_training_receiver_restarts_on_bad_pair(tmp_path):
    lib = _lift(tmp_path)
    lib.server_training_receiver_step.argtypes = [ctypes.POINTER(_TrainingRx), ctypes.c_uint16]
    lib.server_training_receiver_pair.argtypes = [ctypes.POINTER(_TrainingRx), ctypes.c_uint16]
    rx = _TrainingRx()
    for _ in range(7): lib.server_training_receiver_step(ctypes.byref(rx), 0x7E)
    for _ in range(7): lib.server_training_receiver_step(ctypes.byref(rx), 0)
    assert lib.server_training_receiver_step(ctypes.byref(rx), 0) == 1
    assert lib.server_training_receiver_pair(ctypes.byref(rx), 0) == 0xFFFF
    assert rx.state == 0 and rx.pair_index == 0


def test_alternate_stream_source_wraps_and_acknowledges(tmp_path):
    lib = _lift(tmp_path)
    d, io, output = _arrays()
    page = 0x980
    d[page + 7] = 0x67
    d[page + 0x7B] = 1
    io[0x57] = 0x80
    io[0x67] = 0x1234

    lib.server_stream_source(d, io, page)

    assert d[page] == 0x1234
    assert d[page + 7] == 0x62
    assert io[0x57] == 0


def test_alternate_stream_source_reset_sets_empty_sentinel(tmp_path):
    lib = _lift(tmp_path)
    d, io, output = _arrays()
    page = 0x980
    d[page + 7] = 0x65
    d[page + 0x7B] = 1
    d[0x39F] = 0x4000

    lib.server_stream_source(d, io, page)

    assert d[page + 7] == 0x62
    assert d[page] == 0xFF00


def test_alternate_stream_sink_suppresses_duplicate_and_wraps(tmp_path):
    lib = _lift(tmp_path)
    d, io, output = _arrays()
    page = 0x980
    d[page + 0x27] = 0x67
    d[page + 0x7B] = 1
    d[page + 0x71] = 2
    d[page + 0x20] = 0xFF00
    d[page + 0x72] = 0xFF00
    io[0x57] = 0x8000

    lib.server_stream_sink(d, io, output, page)
    assert d[page + 0x27] == 0x67
    assert output[0x67] == 0
    assert io[0x57] == 0x8000

    # A new word is delivered and the six-word ring wraps to 0062.
    d[page + 0x20] = 0xBEEF
    lib.server_stream_sink(d, io, output, page)
    assert output[0x67] == 0xBEEF
    assert d[page + 0x27] == 0x62
    assert io[0x57] == 0

    # Ordinary repeated payload is not suppressed, even with bit 1 set.
    io[0x57] = 0x400
    lib.server_stream_sink(d, io, output, page)
    assert output[0x62] == 0xBEEF
    assert d[page + 0x27] == 0x63
    assert io[0x57] == 0


def test_stream_source_normal_page_falls_back_to_pa6(tmp_path):
    lib = _lift(tmp_path)
    d, io, _ = _arrays()
    d[0x387] = 0x5A
    d[0x3FB] = 1
    io[0x56] = 4
    io[0x5A] = 0x1234
    io[0x57] = 0xFFFF
    lib.server_stream_source(d, io, 0x380)
    assert d[0x380] == 0x1234
    assert d[0x387] == 0x5B
    assert io[0x56] == 0
    assert io[0x57] == 0xFFFF


def test_stream_sink_normal_page_filters_then_falls_back_to_pa6(tmp_path):
    lib = _lift(tmp_path)
    d, io, output = _arrays()
    d[0x327] = 0x58
    d[0x37B] = 1
    d[0x371] = 2
    d[0x320] = d[0x372] = 0xFF00
    io[0x56] = 0x100
    lib.server_stream_sink(d, io, output, 0x300)
    assert io[0x56] == 0x100
    assert d[0x327] == 0x58
    d[0x371] = 0
    lib.server_stream_sink(d, io, output, 0x300)
    assert output[0x58] == 0xFF00
    assert io[0x56] == 0
    assert d[0x327] == 0x59


def test_stream_sink_full_updates_history_without_acknowledging(tmp_path):
    lib = _lift(tmp_path)
    d, io, output = _arrays()
    d[0x9A7] = 0x65
    d[0x9FB] = 1
    d[0x9A0] = 0xBEEF
    io[0x57] = 1  # unrelated status bit
    lib.server_stream_sink(d, io, output, 0x980)
    assert d[0x9F2] == 0xBEEF
    assert d[0x9A7] == 0x65
    assert output[0x65] == 0
    assert io[0x57] == 1
