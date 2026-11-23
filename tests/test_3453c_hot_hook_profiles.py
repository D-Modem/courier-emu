"""A relocated delay hook must not corrupt another profile's live ISR."""
from pathlib import Path

from courier_emu.daa import CourierDaa
from courier_emu.exchange import LineExchange
from courier_emu.flash_image import assemble_flash
from courier_emu.images import load_image
from courier_emu.machine import CourierMachine

ROOT = Path(__file__).resolve().parents[1]


def test_bc_timer_isr_does_not_truncate_guest_tone_library_download(tmp_path):
    boot = (ROOT / 'dumps/3453bc-4MBRYA8G1514-bootmodem-read-20261014/bootmodem.bin').read_bytes()
    normal = (ROOT / 'dumps/3453bc-firmware-read-2.2.09/firmware.bin').read_bytes()
    path = tmp_path / 'synthetic-settings-flash.bin'
    path.write_bytes(assemble_flash(boot, normal, b'\xff' * 0x4000))
    machine = CourierMachine(load_image(path), with_dsp=True, tick_source='dsp',
                             daa=CourierDaa('quiet'), exchange=LineExchange(),
                             serial_input=b'AT\r')
    bridge = machine.dsp_bridge
    observed = []
    original_status = bridge.status

    def status_with_library_snapshot():
        if not bridge.core.closed:
            observed.append(bridge.core.program(0x413))
        return original_status()

    bridge.status = status_with_library_snapshot
    try:
        assert 0x58684 in machine._actual_hot_addresses  # genuine BC delay LOOP
        assert 0x5868c not in machine._actual_hot_addresses  # BC ISR's CLD
        result = machine.run(3_000_000).to_dict()
        assert result['error'] is None
        assert observed and observed[-1] == 0xbc07
        assert result['dsp_bridge']['overlay_words_verified'] >= 4092
    finally:
        bridge.core.close()
