"""Transport regressions; fake engines do not stand in for interop evidence."""
import json
import os
from pathlib import Path
import select
import subprocess
import sys

import pytest

from tools.probe_v90modem_closed_loop import EnginePeer


def peer_for(tmp_path, body, timeout=1, mode='x2'):
    engine = tmp_path / 'engine'
    engine.write_text(f'#!{sys.executable}\nimport os, time\n' + body)
    engine.chmod(0o755)
    return EnginePeer(tmp_path, engine, fast=True, frame_timeout=timeout, mode=mode)


def test_fragmented_engine_reply(tmp_path):
    peer = peer_for(tmp_path, '''
header = os.read(0, 2)
n = int.from_bytes(header, 'little')
data = bytearray()
while len(data) < n:
    data.extend(os.read(0, n - len(data)))
for b in data:
    os.write(1, bytes([b]))
    time.sleep(0.005)
''')
    try:
        assert peer.exchange(b'\xffabc') == b'\xffabc'
    finally:
        peer.stop()
    assert peer.status()['octets_received'] == 4
    assert peer.status()['engine_exit'] == 0
    assert (tmp_path / 'engine-tx.g711').read_bytes() == b'\xffabc'
    assert peer.process.stdout.closed


@pytest.mark.parametrize('mode', ['x2', 'v90'])
def test_engine_modulation_selection(tmp_path, mode, monkeypatch):
    monkeypatch.delenv('ME_V90_DIL_AUTOTERMINATE_CYCLES', raising=False)
    peer = peer_for(tmp_path, "os.read(0, 4096)\nos.write(1, os.environ['ME_MODE'].encode())\n", mode=mode)
    try:
        assert peer.exchange(b'?' * len(mode)) == mode.encode()
        assert peer.environment['ME_MODE'] == mode
        if mode == 'v90':
            assert peer.environment['ME_V90_DIL_AUTOTERMINATE_CYCLES'] == '0'
        else:
            assert 'ME_V90_DIL_AUTOTERMINATE_CYCLES' not in peer.environment
    finally:
        peer.stop()


@pytest.mark.parametrize('cycles', ['1', '2'])
def test_explicit_dil_profile_is_preserved(tmp_path, monkeypatch, cycles):
    monkeypatch.setenv('ME_V90_DIL_AUTOTERMINATE_CYCLES', cycles)
    peer = peer_for(tmp_path, "os.read(0, 4096)\nos.write(1, os.environ['ME_V90_DIL_AUTOTERMINATE_CYCLES'].encode())\n", mode='v90')
    try:
        assert peer.exchange(b'?') == cycles.encode()
        assert peer.environment['ME_V90_DIL_AUTOTERMINATE_CYCLES'] == cycles
    finally:
        peer.stop()


def test_partial_engine_reply_has_bounded_timeout(tmp_path):
    peer = peer_for(tmp_path, "os.write(1, b'a')\nwhile os.read(0, 4096):\n    pass\n",
                    timeout=0.1)
    try:
        peer.start()
        assert select.select([peer.process.stdout], [], [], 5)[0]
        with pytest.raises(TimeoutError, match='1/4 octets'):
            peer.exchange(b'abcd')
        assert peer.samples == 0  # incomplete frames are not counted as delivered
        assert peer.error == 'engine frame: 1/4 octets'
    finally:
        peer.stop()


def test_partial_engine_reply_eof(tmp_path):
    peer = peer_for(tmp_path, "os.read(0, 4096)\nos.write(1, b'a')\n")
    try:
        with pytest.raises(EOFError, match='1/4 octets'):
            peer.exchange(b'abcd')
        assert peer.error == 'engine closed: 1/4 octets'
    finally:
        peer.stop()


@pytest.mark.parametrize('frame_ms', [5, 20, 100])
def test_analog_probe_uses_configured_frame_grid(frame_ms):
    # Import in a fresh interpreter: line framing is selected at import time,
    # and changing it in the pytest process would contaminate other tests.
    root = Path(__file__).resolve().parents[1]
    code = '''
import json
from tools import probe_v90modem_closed_loop as p
print(json.dumps([p.LINE_FRAME_SAMPLES, p.LINE_FRAME_INSTRUCTIONS]))
'''
    result = subprocess.run([sys.executable, '-c', code], cwd=root,
                            env={**os.environ, 'COURIER_LINE_FRAME_MS': str(frame_ms)},
                            capture_output=True, text=True, check=True)
    assert json.loads(result.stdout) == [8 * frame_ms, 4348 * frame_ms]
