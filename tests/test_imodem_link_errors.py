from types import SimpleNamespace

import pytest
from unicorn import Uc, UC_ARCH_X86, UC_MODE_16
from unicorn.x86_const import (UC_X86_REG_DS, UC_X86_REG_ES, UC_X86_REG_SS,
                               UC_X86_REG_SP, UC_X86_REG_CS, UC_X86_REG_IP)

from tools.imodem_link_errors import (LinkErrorObserver, SIGNATURES, ERROR_FLAG,
                                     BLER_COUNT, crc16_lapm)


def machine():
    uc = Uc(UC_ARCH_X86, UC_MODE_16)
    uc.mem_map(0, 0x100000)
    for address, data in SIGNATURES.items():
        uc.mem_write(address, data)
    for reg, value in [(UC_X86_REG_DS, 0x2600), (UC_X86_REG_ES, 0x3200),
                       (UC_X86_REG_SS, 0x2600), (UC_X86_REG_SP, 0xff00)]:
        uc.reg_write(reg, value)
    return SimpleNamespace(uc=uc, instructions=123, timer_ticks=45,
                           mailbox=SimpleNamespace(core=None))


def word(uc, offset, value):
    uc.mem_write(0x26000 + offset, value.to_bytes(2, 'little'))


def test_real_instruction_hooks_observe_original_flag_and_bler_without_changing_them():
    m = machine()
    observer = LinkErrorObserver(m, lambda: {'phase': 'traffic', 'frame': 12})
    m.uc.reg_write(UC_X86_REG_CS, 0xb3d9)
    m.uc.emu_start(0xb4c8a, 0xb4c8f, count=1)
    assert m.uc.mem_read(ERROR_FLAG, 1) == b'\x01'
    m.uc.reg_write(UC_X86_REG_CS, 0xa400)
    m.uc.emu_start(0xa9881, 0xa988b, count=2)
    assert observer.status()['bler_count'] == 1
    events = observer.events
    assert [e['kind'] for e in events] == ['pending_error', 'bler_increment']
    assert events[0]['pc'] == 0xb4c8a
    assert events[1]['pc'] == 0xa9881
    assert events[1]['bler_before_write'] == 0
    assert events[1]['write_value'] == 1


def test_native_interpreter_uses_its_own_hook_and_register_constants():
    from courier_emu import x86_interpreter as api
    uc = api.Uc(api.UC_ARCH_X86, api.UC_MODE_16, profile='386ex')
    uc.mem_map(0, 0x100000)
    for address, data in SIGNATURES.items():
        uc.mem_write(address, data)
    for name, value in [('DS', 0x2600), ('ES', 0x3200), ('SS', 0x2600),
                        ('SP', 0xff00), ('CS', 0xb3d9)]:
        uc.reg_write(getattr(api, 'UC_X86_REG_' + name), value)
    m = SimpleNamespace(uc=uc, cpu_engine='interpreter', instructions=123,
                        timer_ticks=45, mailbox=SimpleNamespace(core=None))
    observer = LinkErrorObserver(m, lambda: {'phase': 'traffic'})
    uc.emu_start(0xb4c8a, 0, count=1)
    assert observer.events[0]['pc'] == 0xb4c8a
    assert observer.events[0]['registers']['ds'] == 0x2600
    uc.reg_write(api.UC_X86_REG_CS, 0xa400)
    uc.emu_start(0xa9881, 0, count=2)
    assert observer.status()['bler_count'] == 1
    assert observer.events[1]['pc'] == 0xa9881


def test_bler_low_word_wrap_is_not_mistaken_for_a_counter_reset():
    m = machine()
    m.uc.mem_write(BLER_COUNT, (0xffff).to_bytes(4, 'little'))
    observer = LinkErrorObserver(m, lambda: {'phase': 'traffic'})
    m.uc.reg_write(UC_X86_REG_CS, 0xa400)
    m.uc.emu_start(0xa9881, 0xa988b, count=2)
    assert observer.status()['bler_count'] == 0x10000
    event, = observer.events
    assert event['write_value'] == 0
    assert event['bler_before_write'] == 0xffff
    assert observer.status()['counts'] == {'traffic:bler_increment': 1}


def test_capture_is_bounded_per_phase_and_kind_but_all_events_are_counted():
    m = machine()
    context = {'phase': 'pre-traffic', 'frame': 1}
    observer = LinkErrorObserver(m, lambda: dict(context), limit=2)
    for _ in range(5):
        observer.on_write(m.uc, None, ERROR_FLAG, 1, 1, None)
    context['phase'] = 'traffic'
    observer.on_write(m.uc, None, ERROR_FLAG, 1, 1, None)
    observer.on_write(m.uc, None, BLER_COUNT, 2, 1, None)
    observer.on_write(m.uc, None, ERROR_FLAG, 1, 0, None)
    assert len(observer.events) == 4
    assert observer.status()['counts'] == {'pre-traffic:pending_error': 5,
                                           'traffic:pending_error': 1,
                                           'traffic:bler_increment': 1}
    assert m.uc.mem_read(ERROR_FLAG, 1) == b'\0'
    assert observer.status()['bler_count'] == 0


@pytest.mark.parametrize('alternate,start,low,high', [(False, 0xbefe, 0x8d00, 0xbf00),
                                                     (True, 0xfe, 0x80, 0x100)])
def test_rejected_ring_capture_wraps_at_original_receive_buffer_boundary(alternate, start, low, high):
    m = machine()
    # Both reject writers see CF32 cleared; the writer identifies the ring.
    word(m.uc, 0xcf32, 0)
    m.uc.reg_write(UC_X86_REG_CS, 0xb3d9)
    m.uc.reg_write(UC_X86_REG_IP, (0xb4cb2 if alternate else 0xb4c8a) - 0xb3d90)
    word(m.uc, 0xcaae if alternate else 0xcaa6, start)
    word(m.uc, 0xd070, 5)
    m.uc.mem_write(0x32000 + start, b'ab')
    m.uc.mem_write(0x32000 + low, b'cde')
    observer = LinkErrorObserver(m, lambda: {'phase': 'traffic'})
    observer.on_write(m.uc, None, ERROR_FLAG, 1, 1, None)
    assert observer.events[0]['receive_ring'] == {
        'segment': 0x3200, 'start': start, 'length': 5, 'hex': b'abcde'.hex(),
        'crc16_raw': crc16_lapm(b'abcde'), 'crc_matches_firmware': False}


def test_crc_uses_hdlc_reflection_initial_state_and_good_frame_residue():
    data = b'123456789'
    assert crc16_lapm(data) == 0x6f91
    fcs = (crc16_lapm(data) ^ 0xffff).to_bytes(2, 'little')
    assert crc16_lapm(data + fcs) == 0xf0b8


def test_first_rejection_snapshots_native_history_once_per_phase_without_advancing_dsp():
    m = machine()
    calls = []
    core = SimpleNamespace(
        state=lambda: {}, io_port_stats=lambda ports: {},
        io_events=lambda **kw: calls.append(kw) or [],
        io_event_total=lambda: 12345,
        data_events=lambda: list(range(2050)), data=lambda address: address,
        _link_bit_capture=True, pc_captures=lambda: [[1, 2, 3, 6, 0, 8]])
    m.mailbox.core = core
    context = {'phase': 'traffic'}
    observer = LinkErrorObserver(m, lambda: dict(context))
    for _ in range(3):
        observer.on_write(m.uc, None, ERROR_FLAG, 1, 1, None)
    context['phase'] = 'post-window'
    observer.on_write(m.uc, None, ERROR_FLAG, 1, 1, None)
    assert calls == [{'limit': 2048, 'ports': tuple(range(0x58, 0x5e))}] * 2
    first, second, third, last = observer.events
    assert len(first['dsp_data_history']) == 2048
    assert first['dsp_data_history'][0] == 2
    assert first['dsp_io_event_total'] == 12345
    assert first['dsp_bit_capture']['rows'] == [[1, 2, 3, 6, 0, 8]]
    assert 'dsp_bank_history' not in second and 'dsp_bank_history' not in third
    assert 'dsp_bank_history' in last
    assert m.uc.mem_read(ERROR_FLAG, 1) == b'\0'


def test_unknown_firmware_fails_closed_before_installing_hooks():
    m = machine()
    m.uc.mem_write(0xa9881, b'\x90')
    with pytest.raises(ValueError, match='unsupported I-modem firmware'):
        LinkErrorObserver(m, lambda: {'phase': 'traffic'})


def test_saved_rejections_reproduce_firmware_crc_before_the_record_gap():
    import json
    from pathlib import Path
    root = Path('artifacts/imodem-x2-first-crc-20261026-212243')
    if not (root / 'link-errors.json').exists():
        pytest.skip('optional saved paired-call evidence')
    report = json.loads((root / 'link-errors.json').read_text())
    rejects = [event for event in report['events'] if event['kind'] == 'pending_error']
    assert len(rejects) == 8
    for event in rejects:
        ring = event['receive_ring']
        data = bytes.fromhex(ring['hex'])
        assert len(data) == ring['length']
        assert crc16_lapm(data) == event['cells']['cf2e'] == ring['crc16_raw']
        assert ring['crc_matches_firmware']
        assert crc16_lapm(data) != 0xf0b8
        assert event['writer_pc_verified']
        # Return from the original HDLC-close reject call at b5298.
        assert int.from_bytes(bytes.fromhex(event['stack_hex'])[:2], 'little') == 0x150b
    first_gap = json.loads((root / 'first-stall.json').read_text())
    assert rejects[0]['frame'] == 390 < first_gap['frame'] == 440
    assert sum(value for key, value in report['counts'].items()
               if key.endswith(':bler_increment')) == report['bler_count'] == 252


def test_signatures_match_the_supplied_firmware():
    from pathlib import Path
    from courier_emu.nac import NacImage
    if not Path('Ie030002.nac').exists():
        pytest.skip('optional local firmware')
    base, data = NacImage.load('Ie030002.nac').flatten()
    for address, expected in SIGNATURES.items():
        assert data[address-base:address-base+len(expected)] == expected
