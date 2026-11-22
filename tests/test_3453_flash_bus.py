from pathlib import Path

import pytest

from courier_emu.flash_bus3453 import FlashBus3453
from courier_emu.images import load_image
from courier_emu.flash_image import assemble_flash
from courier_emu.machine import CourierMachine
from courier_emu.codec import CodecBringUp, SiliconDaa

ROOT = Path(__file__).resolve().parents[1]
BC = ROOT / 'dumps/3453bc-firmware-read-2.2.09/firmware.bin'
C = ROOT / 'dumps/3453c-5MBRZ16P0186-firmware-read-20261014/firmware.bin'


def bus():
    return FlashBus3453(b'L' * 0x80000 + b'H' * 0x80000, 0x20, 0x22EC)


def test_gcs2_controls_flash_a19_independently_of_supervisor_entry():
    flash = bus()
    assert flash.read(0x80000, 2) == b'HH'
    assert flash.write_register(0xFF8A, 2, 0x000E)
    assert flash.read(0x80000, 2) == b'LL'
    assert flash.read(0xFC000, 2) == b'LL'
    assert flash.write_register(0xFF8A, 2, 0x800A)
    assert flash.read(0x80000, 2) == b'HH'
    assert flash.read(0xFC000, 2) == b'HH'


def test_chip_select_windows_and_relocated_peripherals_take_priority():
    flash = bus()
    assert flash.offset(0x3FFFF) is None
    assert flash.offset(0x40000) == 0x40000
    flash.write_register(0xFFA2, 2, 0x100A)
    flash.write_register(0xFFA4, 2, 0x1000)
    assert flash.offset(0xFFFF) is None
    assert flash.offset(0x10000) == 0x10000
    # Sender's copy-to-RAM window, traced at 35A82..35ACB.
    flash.write_register(0xFFA6, 2, 0x400A)
    flash.write_register(0xFFA0, 2, 0x4000)
    flash.write_register(0xFFA2, 2, 0x800A)
    assert flash.offset(0x30000) == 0x30000
    assert flash.offset(0x50000) is None
    assert flash.offset(0x90000) is None


def test_byte_writes_obey_eb_register_bitfields():
    flash = bus()
    flash.write_register(0xFF8A, 1, 0x0E)
    flash.write_register(0xFF8B, 1, 0)
    assert flash.registers[0xFF8A] == 0x000E
    assert flash.read_register(0xFF8A, 2) == 0x000E
    assert flash.read_register(0xFF8B, 1) == 0
    assert flash.read(0x7FFFF, 2) == b'LL'
    assert flash.offset(0x80000) == 0
    flash.write_register(0xFF8A, 2, 0x0006)  # disabled select
    assert flash.offset(0x40000) == 0xC0000


def test_autoselect_does_not_change_array_or_captured_bytes():
    flash = bus()
    original = flash.contents
    flash.write(0x80000, 2, 0x90)  # AMD/ST/MX require the unlock, unlike Intel.
    assert flash.mode == 'array'
    flash.write(0x8AAAA, 2, 0xAA)
    flash.write(0x85554, 2, 0x55)
    flash.write(0x8AAAA, 2, 0x90)
    assert flash.read(0x80000, 4) == bytes.fromhex('2000ec22')
    flash.write(0x80000, 2, 0xF0)
    assert flash.read(0x80000, 4) == b'HHHH'
    flash.write(0x50000, 2, 0xA55A)  # ordinary RAM probe cannot program flash
    assert flash.contents == original
    assert flash.read(0x50000, 2) == b'LL'
    flash.write(0x8AAAA, 2, 0xAA)
    flash.write(0x85554, 2, 0x55)
    with pytest.raises(ValueError, match='read-only'):
        flash.write(0x8AAAA, 2, 0xA0)


@pytest.mark.parametrize('path,identity', [(BC, '20-22EC'), (C, 'C2-22D6')])
@pytest.mark.parametrize('revision', [0x13, 0])
def test_original_ati7_reports_flash_and_asic_codec_identity(tmp_path, path, identity, revision):
    boot = ROOT / ('dumps/3453bc-4MBRYA8G1514-bootmodem-read-20261014/bootmodem.bin'
                   if path == BC else
                   'dumps/3453c-5MBRZ16P0186-bootmodem-read-20261014/bootmodem.bin')
    complete = tmp_path / 'flash.bin'
    complete.write_bytes(assemble_flash(boot.read_bytes(), path.read_bytes(), b'\xff' * 0x4000))
    codec = CodecBringUp(SiliconDaa(revision=revision))
    machine = CourierMachine(load_image(complete), with_dsp=True, codec=codec,
                             serial_input=b'ATI7\r')
    try:
        result = machine.run(4_000_000).to_dict()
        assert result['error'] is None
        assert result['serial_input_remaining'] == 0
        assert identity in result['serial_text']
        assert f'DAA rev                {revision:04X}' in result['serial_text']
        assert result['dsp_bridge']['bootstrap_match'] is True
        assert result['flash']['bus']['autoselects'] > 0
        assert result['flash']['bus']['read_only'] is True
        assert result['dsp_bridge']['runtime_inbound_delivered'][f'007b:{revision:04x}'] > 0
    finally:
        machine.dsp_bridge.core.close()


@pytest.mark.parametrize('path', [BC, C])
@pytest.mark.parametrize('mode', ['normal', 'bootmodem'])
def test_mailbox_iret_releases_dsp_paced_board_tick(tmp_path, path, mode):
    from courier_emu.firmware3453 import profile_for
    boot = ROOT / ('dumps/3453bc-4MBRYA8G1514-bootmodem-read-20261014/bootmodem.bin'
                   if path == BC else
                   'dumps/3453c-5MBRZ16P0186-bootmodem-read-20261014/bootmodem.bin')
    complete = tmp_path / 'flash.bin'
    complete.write_bytes(assemble_flash(boot.read_bytes(), path.read_bytes(), b'\xff' * 0x4000))
    image = load_image(complete, firmware_mode=mode)
    profile = profile_for(image)
    for canonical in (0x677F1, 0x677F8):
        assert image.data[profile.address(canonical)] == 0xCF  # actual IRET
    machine = CourierMachine(image, with_dsp=True, serial_input=b'ATI0\r', tick_source='dsp')
    try:
        result = machine.run(4_000_000).to_dict()
        assert result['error'] is None
        assert result['ticks'] > 100
        assert result['serial_input_remaining'] == 0
        assert 'OK' in result['serial_text']
        assert result['dsp_bridge']['bootstrap_match'] is True
    finally:
        machine.dsp_bridge.core.close()
