from types import SimpleNamespace

import pytest

from courier_emu import x86_interpreter as api
from courier_emu.rom_lapm_trace import RomLapmTrace, SIGNATURES, decode_header
from courier_emu.v120 import crc16


class Memory:
    def __init__(self):
        self.memory = bytearray(1 << 20)
        self.registers = {getattr(api, 'UC_X86_REG_' + r): 0 for r in ('CS', 'IP', 'DS', 'ES')}
        self.hooks = []
        for address, data in SIGNATURES.items():
            self.memory[address:address + len(data)] = data

    def mem_read(self, address, size):
        return bytes(self.memory[address:address + size])

    def mem_write(self, address, data):
        self.memory[address:address + len(data)] = data

    def reg_read(self, reg):
        return self.registers[reg]

    def hook_add(self, *args):
        self.hooks.append(args)
        return len(self.hooks)

    def word(self, address, value):
        self.mem_write(address, value.to_bytes(2, 'little'))


def machine():
    return SimpleNamespace(uc=Memory(), cpu_engine='interpreter', online_mode=True,
                           instructions=1000, dsp_bridge=SimpleNamespace(line=SimpleNamespace(frames=100)))


@pytest.mark.parametrize('data,expected', [
    ('03000b', {'type': 'I', 'ns': 0, 'nr': 5, 'pf': 1}),
    ('038002', {'type': 'I', 'ns': 64, 'nr': 1, 'pf': 0}),
    ('030117', {'type': 'RR', 'nr': 11, 'pf': 1}),
    ('010516', {'type': 'RNR', 'nr': 11, 'pf': 0}),
    ('030902', {'type': 'REJ', 'nr': 1, 'pf': 0}),
    ('030d03', {'type': 'SREJ', 'nr': 1, 'pf': 1}),
    ('0373', {'type': 'U', 'u_control': 0x63, 'pf': 1}),
    ('0301', {'type': 'RR', 'truncated_control': True}),
    ('0401', {'type': 'unclassified-address'}),
    ('03', {'type': 'short'}),
])
def test_decode_header(data, expected):
    decoded = decode_header(bytes.fromhex(data))
    assert all(decoded.get(k) == v for k, v in expected.items())


def test_wrapped_crc_verified_rnr_snapshot_is_read_only():
    m = machine()
    trace = RomLapmTrace(m)
    uc = m.uc
    data = bytes.fromhex('030517')
    data += ((~crc16(data)) & 0xffff).to_bytes(2, 'little')
    assert crc16(data) == 0xf0b8
    uc.word(0x3bc, len(data))
    uc.word(0x2af, 0xf0b8)
    uc.word(0x262, 0x1afe)
    uc.mem_write(0x2b3, b'\x01')
    uc.mem_write(0x1afe, data[:2])
    uc.mem_write(0x1a80, data[2:])
    before = bytes(uc.memory), dict(uc.registers)
    trace.on_code(uc, 0x907b3, 6, None)
    packet = trace.status()['packets'][0]
    assert packet['firmware_crc_valid'] and packet['ring_crc_matches_firmware']
    assert packet['decoded']['type'] == 'RNR' and packet['decoded']['nr'] == 11
    assert before == (bytes(uc.memory), uc.registers)


def test_tx_stage_bounds_and_limits_are_explicit():
    m = machine()
    trace = RomLapmTrace(m, packet_limit=1, state_limit=1, window_frames=10)
    uc = m.uc
    uc.mem_write(0x2c1, b'\x03')
    uc.mem_write(0xaf5, bytes.fromhex('038002'))
    trace.on_code(uc, 0x8cb26, 5, None)
    assert trace.packets[0]['decoded']['ns'] == 64
    trace.on_code(uc, 0x8cb26, 5, None)
    assert trace.counts['packets_dropped_at_limit'] == 1
    trace.on_write(uc, 0, 0xb64, 1, 1, None)
    trace.on_write(uc, 0, 0xb65, 1, 1, None)
    assert len(trace.states) == 1 and trace.counts['states_dropped_at_limit'] == 1
    m.dsp_bridge.line.frames += 10
    trace.on_code(uc, 0x8cb26, 5, None)
    assert trace.counts['tx_staged'] == 2  # Frozen, not continuously accumulating.


def test_bad_signature_fails_before_installing_hooks():
    m = machine()
    m.uc.mem_write(0x907b3, b'\x00')
    with pytest.raises(ValueError, match='signature'):
        RomLapmTrace(m)
    assert not m.uc.hooks


def test_offline_and_invalid_ring_are_not_presented_as_verified_frames():
    m = machine()
    trace = RomLapmTrace(m)
    m.online_mode = False
    trace.on_code(m.uc, 0x907b3, 6, None)
    assert not trace.packets
    m.online_mode = True
    trace.on_code(m.uc, 0x907b3, 6, None)
    assert trace.packets[0]['invalid_ring_bounds']
    assert 'decoded' not in trace.packets[0]
