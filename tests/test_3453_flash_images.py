"""Captured 3453 flash layout, guarded profiles and native boot-mode execution."""
from pathlib import Path

import pytest

from courier_emu.flash_image import CourierFlashImage, assemble_flash
from courier_emu.firmware3453 import profile_for
from courier_emu.images import load_image
from courier_emu.machine import CourierMachine
from courier_emu.machine_map import courier_machine_map
from courier_emu.xmf import XmfFormatError, XmfImage

ROOT = Path(__file__).resolve().parents[1]
CAPTURES = {
    'bc': (
        ROOT / 'dumps/3453bc-4MBRYA8G1514-bootmodem-read-20261014/bootmodem.bin',
        ROOT / 'dumps/3453bc-firmware-read-2.2.09/firmware.bin',
    ),
    'c': (
        ROOT / 'dumps/3453c-5MBRZ16P0186-bootmodem-read-20261014/bootmodem.bin',
        ROOT / 'dumps/3453c-5MBRZ16P0186-firmware-read-20261014/firmware.bin',
    ),
}


def assembled(tmp_path, family):
    boot, normal = CAPTURES[family]
    path = tmp_path / 'whole-flash.bin'
    path.write_bytes(assemble_flash(boot.read_bytes(), normal.read_bytes(), b'\xff' * 0x4000))
    return path


@pytest.mark.parametrize('family', CAPTURES)
def test_split_boot_capture_and_complete_layout(tmp_path, family):
    boot, normal = CAPTURES[family]
    path = assembled(tmp_path, family)
    raw = path.read_bytes()
    assert len(raw) == 0x100000
    assert raw[:0x40000] == boot.read_bytes()[:0x40000]
    assert raw[0x40000:0xf8000] == normal.read_bytes()
    assert raw[0xf8000:0xfc000] == b'\xff' * 0x4000
    assert raw[0xfc000:] == boot.read_bytes()[0x40000:]
    image = load_image(boot)
    assert image.firmware_mode == 'bootmodem'
    assert not image.complete_flash
    assert image.entry_physical == 0x17FAF
    assert image.memory_image()[:0x10000] == bytes(0x10000)
    assert image.memory_image()[0x80000:0xc0000] == b'\xff' * 0x40000
    assert load_image(path).memory_image()[0x80000:0xc0000] == raw[0x80000:0xc0000]
    with pytest.raises(XmfFormatError, match='no normal'):
        load_image(boot, firmware_mode='normal')
    with pytest.raises(ValueError, match='missing normal'):
        image.select_mode('normal')


@pytest.mark.parametrize('family', CAPTURES)
def test_dsp_tables_have_distinct_cache_entries_for_each_mode(tmp_path, family):
    path = assembled(tmp_path, family)
    normal = load_image(path, firmware_mode='normal')
    boot = load_image(path, firmware_mode='bootmodem')
    assert normal.digest == boot.digest
    assert normal.dsp_segments()[0].file_offset == 0x402F0
    assert boot.dsp_segments()[0].file_offset == 0x2E0
    assert normal.dsp_program_segments() == boot.dsp_program_segments()
    assert normal.dsp_program_segments() == XmfImage.load(CAPTURES[family][1]).dsp_program_segments()
    assert normal.select_mode('bootmodem').dsp_program_segments() == boot.dsp_program_segments()
    assert courier_machine_map(normal).region_at(0x20000).device == 'ram'
    assert courier_machine_map(boot).region_at(0x20000).device == 'flash'
    assert courier_machine_map(boot).serial_callback.first == 0x2a6


@pytest.mark.parametrize('field,length', [('boot', 0), ('normal', 0), ('settings', 0)])
def test_assembly_rejects_missing_regions(field, length):
    parts = {'boot': b'\xff' * 0x44000, 'normal': b'\xff' * 0xb8000, 'settings': b'\xff' * 0x4000}
    parts[field] = bytes(length)
    with pytest.raises(ValueError):
        assemble_flash(parts['boot'], parts['normal'], parts['settings'])


def test_invalid_entry_vector_is_rejected(tmp_path):
    path = assembled(tmp_path, 'c')
    raw = bytearray(path.read_bytes())
    raw[0x3fff0] = 0
    path.write_bytes(raw)
    with pytest.raises(XmfFormatError, match='entry vector'):
        CourierFlashImage.load(path)


def test_profile_is_guarded_by_code_not_settings(tmp_path):
    path = assembled(tmp_path, 'bc')
    image = load_image(path)
    profile = profile_for(image)
    raw = bytearray(path.read_bytes())
    raw[0xf805f] = 0x12  # artificial credential byte must not change code selection
    path.write_bytes(raw)
    assert profile_for(load_image(path)) is profile
    raw[image.supervisor_offset+0x100] ^= 1
    path.write_bytes(raw)
    assert profile_for(load_image(path)) is None
    with pytest.raises(ValueError, match='verified 3453'):
        CourierMachine(load_image(path))


def execute(image, commands, limit=4_000_000, *, port_values=None, boot_select_pulse=False):
    uarts = {profile_for(image).address(0x5944D)}
    if getattr(image, 'complete_flash', False):
        for mode in ('normal', 'bootmodem'):
            profile = profile_for(image.select_mode(mode))
            if profile is not None:
                uarts.add(profile.address(0x5944D))
    def release_selection(address):
        # Model a momentary selection input: AL has already sampled it.
        # Holding a raw port override also masks later board inputs.
        if address == 0xFDE08:
            machine.port_values.pop(0x14, None)

    machine = CourierMachine(image, with_dsp=True, serial_input=commands,
                             port_values=port_values,
                             code_observer=release_selection if boot_select_pulse else None,
                             pc_watch={uart: 'uart' for uart in uarts})
    try:
        result = machine.run(limit).to_dict()
        assert result['error'] is None
        assert result['status'] == 'main-loop'
        assert result['serial_input_remaining'] == 0
        assert result['dsp_bridge']['bootstrap_match'] is True
        assert '3368' in result['serial_text']  # execution check, not hardware identity
        assert 'OK' in result['serial_text']
        assert result['pc_watch_counts']['uart'] > 0
        assert all(event['pc'] in {f'{uart:05x}' for uart in uarts}
                   for event in result['pc_watch'])
        return result
    finally:
        machine.dsp_bridge.core.close()


def test_cli_forwards_selected_firmware_mode(tmp_path):
    from courier_emu.cli import build_parser, _worker_command
    path = assembled(tmp_path, 'bc')
    args = build_parser().parse_args(['run', str(path), '--firmware-mode', 'bootmodem', '--with-dsp'])
    command = _worker_command(args)
    index = command.index('--firmware-mode')
    assert command[index+1] == 'bootmodem'


@pytest.mark.parametrize('family', CAPTURES)
@pytest.mark.parametrize('mode', ['normal', 'bootmodem'])
def test_captured_supervisors_boot_and_answer_original_at_parser(family, mode):
    boot, normal = CAPTURES[family]
    execute(load_image(boot if mode == 'bootmodem' else normal), b'ATI0\r')


@pytest.mark.parametrize('family', CAPTURES)
def test_whole_flash_roundtrip_switch_and_multiple_commands(tmp_path, family):
    path = assembled(tmp_path, family)
    result = execute(load_image(path), b'ATZ!!\rATI0\rATZ!!\rATI0\r', 10_000_000)
    assert result['serial_text'].count('3368') == 2
    assert result['flash']['firmware_mode'] == 'normal'
    assert [entry['mode'] for entry in result['flash']['mode_switches']] == ['bootmodem', 'normal']


def test_power_on_entry_and_unfinished_loader_are_not_reported_as_booted(tmp_path):
    image = load_image(assembled(tmp_path, 'bc'), power_on=True)
    assert image.entry_physical == 0xFFFF0
    assert image.memory_image()[0x80000:] == image.data[0x80000:]
    result = CourierMachine(image).run(1).to_dict()
    power = result['flash']['power_on']
    assert power['reset_vector_executed'] is True
    assert power['normal_crc_valid'] is None
    assert power['selected_mode'] is None
    assert power['loader_exit_instruction'] is None


def test_power_on_cli_forwarding_and_invalid_combinations(tmp_path):
    from courier_emu.cli import build_parser, _worker_command
    path = assembled(tmp_path, 'bc')
    args = build_parser().parse_args(['run', str(path), '--power-on', '--with-dsp'])
    assert '--power-on' in _worker_command(args)
    with pytest.raises(XmfFormatError, match='selected by the guest loader'):
        load_image(path, power_on=True, firmware_mode='bootmodem')
    with pytest.raises(XmfFormatError, match='requires'):
        load_image(CAPTURES['bc'][1], power_on=True)
    raw = bytearray(path.read_bytes())
    raw[0xFC100] ^= 1
    path.write_bytes(raw)
    with pytest.raises(XmfFormatError, match='reset loader'):
        load_image(path, power_on=True)


@pytest.mark.parametrize('family', CAPTURES)
@pytest.mark.parametrize('selection', ['normal', 'input-recovery', 'bad-crc', 'bad-supervisor'])
def test_power_on_real_loader_checks_crc_and_selects_firmware(tmp_path, family, selection):
    path = assembled(tmp_path, family)
    corrupt = selection in ('bad-crc', 'bad-supervisor')
    if corrupt:
        raw = bytearray(path.read_bytes())
        # Cover both an intact supervisor with a bad application CRC and a
        # damaged supervisor which must not be required to start recovery.
        offset = 0xE0000 if selection == 'bad-crc' else 0x57CB0
        raw[offset] ^= 1
        path.write_bytes(raw)
    original = path.read_bytes()
    ports = {0x14: 0xFFBF} if selection == 'input-recovery' else None
    result = execute(load_image(path, power_on=True), b'ATI0\r', 14_000_000,
                     port_values=ports, boot_select_pulse=selection == 'input-recovery')
    power = result['flash']['power_on']
    assert power['reset_vector_executed'] is True
    assert power['normal_crc_valid'] is (not corrupt)
    assert power['boot_select_normal'] == (
        None if corrupt else selection == 'normal')
    assert power['selected_mode'] == ('normal' if selection == 'normal' else 'bootmodem')
    assert power['loader_exit_instruction'] > 8_000_000  # CRC was not bypassed.
    assert result['flash']['firmware_mode'] == power['selected_mode']
    assert result['flash']['mode_switches'] == []  # Initial selection is not ATZ!!.
    assert path.read_bytes() == original


@pytest.mark.parametrize('family', CAPTURES)
def test_power_on_boot_only_capture_has_real_missing_image_fallback(family):
    image = load_image(CAPTURES[family][0], power_on=True)
    assert image.memory_image()[0x80000:0xC0000] == b'\xff' * 0x40000
    result = execute(image, b'ATI0\r')
    power = result['flash']['power_on']
    assert power['reset_vector_executed'] is True
    assert power['normal_crc_valid'] is False
    assert power['boot_select_normal'] is None
    assert power['selected_mode'] == 'bootmodem'
    assert power['loader_exit_instruction'] < 10_000


def test_power_on_then_atz_roundtrip_retains_reset_evidence(tmp_path):
    path = assembled(tmp_path, 'bc')
    result = execute(load_image(path, power_on=True),
                     b'ATZ!!\rATI0\rATZ!!\rATI0\r', 18_000_000)
    assert result['serial_text'].count('3368') == 2
    assert result['flash']['power_on']['selected_mode'] == 'normal'
    assert result['flash']['power_on']['normal_crc_valid'] is True
    assert result['flash']['firmware_mode'] == 'normal'
    assert [entry['mode'] for entry in result['flash']['mode_switches']] == ['bootmodem', 'normal']
