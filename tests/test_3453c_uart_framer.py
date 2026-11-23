"""Isolated original CPU 8N1 receiver, not patched callbacks in a modem call."""
import json
from pathlib import Path

import pytest

from courier_emu import x86_interpreter as x86

ROOT = Path(__file__).resolve().parents[1]


def receive_words(words, native):
    firmware = (ROOT / 'dumps/3453bc-firmware-read-2.2.09/firmware.bin').read_bytes()
    cpu = x86.Uc(0, 0)
    cpu.native_enabled = native
    cpu.mem_map(0, len(cpu.memory))
    cpu.mem_write(0x40000, firmware)
    # Unit caller only: CALL original 6EBD9; HLT. The original byte sink
    # 6878A and its receive ring are used, without a substituted byte sink.
    cpu.mem_write(0x675b0, bytes.fromhex('e82676f4'))
    cpu.mem_write(0x1ed2, bytes([7, 3]))
    cpu.mem_write(0x716, (0x11da).to_bytes(2, 'little'))
    cpu.mem_write(0x6c2, (0x2c00).to_bytes(2, 'little'))
    cpu.reg_write(x86.UC_X86_REG_CS, 0x675b)
    cpu.reg_write(x86.UC_X86_REG_SS, 0x3000)
    for word in words:
        cpu.reg_write(x86.UC_X86_REG_AX, word)
        cpu.reg_write(x86.UC_X86_REG_SP, 0xfffe)
        cpu.reg_write(x86.UC_X86_REG_FLAGS, 2)
        cpu.emu_start(0x675b0, 0, count=200)
    end = int.from_bytes(cpu.mem_read(0x6c2, 2), 'little')
    return bytes(cpu.mem_read(0x2c00, end - 0x2c00))


@pytest.mark.parametrize('native', [False, True])
@pytest.mark.parametrize('phase', [0, 1, 2])
def test_original_cpu_framer_accepts_three_sample_words(native, phase):
    payload = b'word\r'
    bits = [1] * 4
    for value in payload:
        bits.extend([0, *[(value >> k) & 1 for k in range(8)], 1])
    bits.extend([1] * 4)
    samples = [1] * phase + [bit for bit in bits for _ in range(24)]
    words = [sum(samples[offset + k] << k for k in range(3))
             for offset in range(0, len(samples) - 2, 3)]
    assert receive_words(words, native) == payload


@pytest.mark.parametrize('native', [False, True])
def test_original_cpu_framer_preserves_native_carrier_loss_nul(native):
    path = ROOT / 'artifacts/3453-bell103-data-path-20261015/carrier-loss-word-control.json'
    control = json.loads(path.read_text())
    words = [value for value, count in control['runs'] for _ in range(count)]
    assert all(0 <= value <= 7 for value in words)
    expected = bytes.fromhex(control['payload_hex']) + b'\x00'
    assert expected == bytes.fromhex(control['expected_hex'])
    assert receive_words(words, native) == expected


@pytest.mark.parametrize('native', [False, True])
@pytest.mark.parametrize('side', ['a', 'b'])
def test_original_cpu_framer_replays_exact_real_peer_words(native, side):
    # Explicitly selected synthetic-payload bit words, not board settings or
    # raw CPU traces. Replay is a control only; it never feeds the real peers.
    path = ROOT / 'artifacts/3453-bell103-data-path-20261015/received-word-controls.json'
    control = json.loads(path.read_text())[side]
    assert control['word_bits'] == 3
    words = [value for value, count in control['runs'] for _ in range(count)]
    assert all(0 <= value <= 7 for value in words)
    assert receive_words(words, native) == bytes.fromhex(control['expected_hex'])
