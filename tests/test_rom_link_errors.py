from types import SimpleNamespace

import pytest

from courier_emu.rom_link_errors import (BLER_COUNT, ERROR_FLAG, OUTPUT_SIGNATURE,
                                         SIGNATURES, RomLinkErrorObserver)
from courier_emu.v120 import crc16


def fixture(engine):
    if engine == 'interpreter':
        from courier_emu import x86_interpreter as api
    else:
        import unicorn as api
        from unicorn import x86_const
        api = SimpleNamespace(**{n: getattr(api, n) for n in ('Uc', 'UC_ARCH_X86', 'UC_MODE_16')},
                              **{n: getattr(x86_const, n) for n in dir(x86_const) if n.startswith('UC_X86_REG_')})
    uc = api.Uc(api.UC_ARCH_X86, api.UC_MODE_16)
    uc.mem_map(0, 0x100000)
    for address, value in SIGNATURES.items():
        uc.mem_write(address, value)
    for name, value in [('DS', 0), ('ES', 0), ('SS', 0), ('SP', 0x1000)]:
        uc.reg_write(getattr(api, 'UC_X86_REG_' + name), value)
    m = SimpleNamespace(uc=uc, cpu_engine=engine, online_mode=True, instructions=123, dsp_bridge=None)
    return m, api


@pytest.mark.parametrize('engine', ['interpreter', 'unicorn'])
@pytest.mark.parametrize('alternate', [False, True])
def test_original_reject_and_counter_writes_capture_the_correct_wrapped_ring(engine, alternate):
    m, api = fixture(engine)
    uc = m.uc
    low, high = (0x1a80, 0x1b00) if alternate else (0xb000, 0xc000)
    start = high - 2
    data = b'abcde'
    for address, value in [(0x262 if alternate else 0x25a, start), (0x3bc, len(data)),
                            (0x2af, crc16(data)), (0x2b3, 0)]:
        uc.mem_write(address, value.to_bytes(2, 'little'))
    uc.mem_write(start, data[:2])
    uc.mem_write(low, data[2:])
    observer = RomLinkErrorObserver(m)
    pc = 0x9015f if alternate else 0x90137
    uc.reg_write(api.UC_X86_REG_CS, 0x8f46)
    uc.emu_start(pc, pc + 5, count=1)
    assert bytes(uc.mem_read(ERROR_FLAG, 1)) == b'\x01'
    event, = observer.events
    assert event['pc'] == pc and event['writer_pc_verified']
    assert event['receive_ring']['hex'] == data.hex()
    assert event['receive_ring']['crc_matches_firmware']
    # Observe, do not increment the counter in Python.
    assert observer.status()['bler_count'] == 0
    uc.reg_write(api.UC_X86_REG_CS, 0x8000)
    uc.emu_start(0x854c8, 0x854d2, count=2)
    assert observer.status()['bler_count'] == 1
    assert observer.events[-1]['pc'] == 0x854c8
    assert observer.events[-1]['bler_before_write'] == 0


def test_bler_low_word_wrap_is_preserved():
    m, api = fixture('interpreter')
    m.uc.mem_write(BLER_COUNT, (0xffff).to_bytes(4, 'little'))
    observer = RomLinkErrorObserver(m)
    m.uc.reg_write(api.UC_X86_REG_CS, 0x8000)
    m.uc.emu_start(0x854c8, 0x854d2, count=2)
    assert observer.status()['bler_count'] == 0x10000
    assert observer.events[0]['write_value'] == 0


def test_history_is_bounded_but_every_rejection_is_counted_and_zero_is_ignored():
    m, api = fixture('interpreter')
    observer = RomLinkErrorObserver(m, limit=2)
    m.uc.reg_write(api.UC_X86_REG_CS, 0x8f46)
    m.uc.reg_write(api.UC_X86_REG_IP, 0x90137 - 0x8f460 + 5)
    for _ in range(10):
        observer.on_write(m.uc, None, ERROR_FLAG, 1, 1, None)
    observer.on_write(m.uc, None, ERROR_FLAG, 1, 0, None)
    observer.on_write(m.uc, None, ERROR_FLAG - 1, 2, 0x100, None)
    assert len(observer.events) == 2
    assert observer.counts == {'online:pending_error': 10}
    assert observer.status()['bler_count'] == 0
    assert bytes(m.uc.mem_read(ERROR_FLAG, 1)) == b'\0'


def test_unknown_rom_fails_closed():
    m, api = fixture('interpreter')
    m.uc.mem_write(0x907b3, b'\0')
    with pytest.raises(ValueError, match='unsupported analog ROM'):
        RomLinkErrorObserver(m)


def test_output_snapshot_is_safe_after_core_close_and_fails_closed_on_new_epoch():
    from courier_emu.dsp import LaneHostIo, NativeC5x
    import struct

    m, api = fixture('interpreter')
    observer = RomLinkErrorObserver(m)
    lane = LaneHostIo()
    try:
        m._lane_io = lane
        with NativeC5x.from_program(0x8320, struct.pack('<12H', *OUTPUT_SIGNATURE)) as core:
            m.dsp_bridge = SimpleNamespace(core=core)
            lane.configure(core.handle, True, command_port=0x18, ack_port=0x1a,
                           lane_first=0x40, banks=6, dsp_first=0x58, dsp_status=0x56)
            lane.set_recent()
            observer.arm_bank_trace()
            assert observer.output_exhaustion()['output_signature_verified']
        # Final MachineResult construction happens after the DSP has closed.
        assert observer.status()['output_exhaustion']['output_signature_verified']
        lane.arm_bank_trace()  # A reset/rebuild also starts another epoch.
        assert not observer.status()['output_exhaustion']['output_signature_verified']
    finally:
        lane.close()


def test_connect_arms_native_trace_once_not_on_payload():
    from courier_emu.machine import CourierMachine

    m = CourierMachine.__new__(CourierMachine)
    calls = []
    m.serial = bytearray()
    m.serial_trace = []
    m.online_mode = False
    m._serial_input_after_connect = []
    m.console = None
    m._rom_link_errors = SimpleNamespace(arm_bank_trace=lambda: calls.append('arm'))
    for byte in b'\r\nCONNECT 53333/ARQ/x2\r\npayload CONNECT\r\n':
        m._capture_serial(byte)
    assert calls == ['arm']
    assert m.online_mode


def test_signatures_match_the_unmodified_403_capture():
    from pathlib import Path
    from courier_emu.rom import CourierRom
    path = Path('dumps/courier-board-21210-capture-403/courier-board.rom')
    if not path.exists():
        pytest.skip('optional original ROM')
    rom = CourierRom.load(path)
    for address, value in SIGNATURES.items():
        assert rom.at(address, len(value)) == value
    origin, resident = rom.dsp_program_segments()[0]
    offset = 2 * (0x8320 - origin)
    assert resident[offset:offset + 2 * len(OUTPUT_SIGNATURE)] == b''.join(
        word.to_bytes(2, 'little') for word in OUTPUT_SIGNATURE)
