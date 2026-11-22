"""Keep the XMF transport separate from the DSP's interrupt-ROM mapping."""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def image(name):
    from courier_emu.images import load_image
    path = ROOT / name
    if not path.exists():
        pytest.skip(f"optional local firmware {name} is unavailable")
    return load_image(path)


@pytest.mark.parametrize('name', ['main211.xmf', 'main2205.XMF', '2_3_33.XMF'])
def test_xmf_uses_eb_interrupt_mask_layout(name):
    from courier_emu.machine import CourierMachine
    from courier_emu.timers import EbInterruptController, IMASK
    machine = CourierMachine(image(name))
    controller = machine.timers.controller
    assert isinstance(controller, EbInterruptController)
    controller.write(IMASK, 0x0040)
    assert not controller.enabled('int2')
    assert controller.enabled('int3')
    controller.write(IMASK, 0x0080)
    assert controller.enabled('int2')
    assert not controller.enabled('int3')


def test_xmf_maps_vectors_without_starting_rom_downloader():
    from courier_emu import boot_rom
    from courier_emu.bridge import CourierDspBridge, XMF_TRANSFER
    bridge = CourierDspBridge(image('main211.xmf'))
    try:
        assert bridge.transfer is XMF_TRANSFER
        assert bridge.maps_onchip_rom
        assert not bridge.boot_rom_enabled
        origin, resident = bridge.image.dsp_program_segments()[0]
        assert not bridge._loader_started
        assert bridge.core.program(origin) == int.from_bytes(resident[:2], 'little')
        assert bridge.core.program(0) == int.from_bytes(boot_rom.mask_rom()[:2], 'little')
    finally:
        bridge.core.close()


def test_rom_retains_real_mask_rom_download_path():
    from courier_emu.bridge import CourierDspBridge, ROM_TRANSFER
    bridge = CourierDspBridge(image('IDSDL302.ROM'))
    try:
        assert bridge.transfer is ROM_TRANSFER
        assert bridge.boot_rom_enabled
        assert bridge.core.pc() == 0
        origin, _ = bridge.image.dsp_program_segments()[0]
        assert bridge.core.program(origin) == 0
    finally:
        bridge.core.close()


def test_xmf_native_execution_reaches_at_response(monkeypatch):
    from courier_emu.machine import CourierMachine
    monkeypatch.setenv('COURIER_X86_NATIVE', '1')
    machine = CourierMachine(image('main211.xmf'), with_dsp=True, serial_input=b'AT\r')
    try:
        result = machine.run(9_000_000)
        assert result.error is None
        assert 'OK' in result.serial_text
        assert machine.uc.native_enabled
        assert machine._lane_io is None
    finally:
        machine.dsp_bridge.core.close()


class DiagnosticConsole:
    poll_instructions = 8192
    closed = False

    def __init__(self, followup=b'ATI3\r'):
        self.followup = followup
        self.output = bytearray()
        self.sent_diagnostic = False
        self.sent_followup = False
        self.ready_polls = 0

    def poll(self, limit=4096):
        if not self.sent_diagnostic:
            self.sent_diagnostic = True
            return b'ATI11\r'
        if self.output.count(b'OK\r\n') == 1 and not self.sent_followup:
            self.ready_polls += 1
            if self.ready_polls >= 4:
                self.sent_followup = True
                return self.followup
        if self.output.count(b'OK\r\n') == 2:
            self.closed = True
        return b''

    def write(self, value):
        self.output.append(value)

    def show_lamps(self, line):
        pass

    def summary(self):
        return {}

    def close(self):
        self.closed = True


@pytest.mark.parametrize('followup', [b'AT\r', b'ATI3\r', b'ATI11\r'])
def test_xmf_ati11_completes_diagnostic_report(followup):
    from courier_emu.machine import CourierMachine
    console = DiagnosticConsole(followup)
    machine = CourierMachine(image('main211.xmf'), with_dsp=True, console=console)
    try:
        result = machine.run(12_000_000)
        assert result.error is None
        assert 'Link Diagnostics' in result.serial_text
        assert 'Carrier Freq' in result.serial_text
        assert 'V.90 Status' in result.serial_text
        assert result.serial_text.count('OK\r\n') == 2, result.serial_text
        if followup == b'ATI3\r':
            assert 'USRobotics Courier V.Everything EXT' in result.serial_text
        if followup == b'ATI11\r':
            assert result.serial_text.count('Link Diagnostics') == 2
        assert result.serial_input_remaining == 0
        assert result.ticks > 0
        assert machine.timers.controller.enabled('int3')
    finally:
        machine.dsp_bridge.core.close()
