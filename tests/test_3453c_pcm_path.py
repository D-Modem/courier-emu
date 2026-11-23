"""Independent primary-serial PCM test, not a patched modem call."""
import struct

from courier_emu.dsp import NativeC5x
from courier_emu.bridge import CourierDspBridge
from courier_emu.xmf import XmfImage
from pathlib import Path


def test_dsp_primary_serial_pcm_reaches_si3034_and_line_resampler():
    # A separate DSP test program: load signed PCM and write DXR, repeatedly.
    # No captured supervisor/resident is modified or executed in this test.
    pcm = 0x2468
    words = [0xbc00, 0xbf80, pcm, 0x8821, 0x7980, 0x6000]
    with NativeC5x.from_program(0x6000, struct.pack('<6H', *words), model='c52') as core:
        core.configure_si3034_codec()
        core.configure_line_frame_interrupt(5, 0xffff)
        for control in (0x0704, 0x083f, 0x0a00, 0x0911, 0x0660, 0x0f00):
            core.host_write(0x21, 1)
            core.host_write(0x21, control)
        period = core.codec_state()['frame_period']
        # Finish pending secondary FSYNC while the serial transmitter is reset.
        core.step(period)
        core.host_write(0x22, 0xc0)  # XRST/RRST
        core.set_pc(0x6000)
        core.queue_codec_rx([0x1356] * 64)
        core.step(period * 16 + period // 16)
        assert core.serial_state()['dxr'] == pcm
        assert core.line_tx_samples()[-8:] == [pcm] * 8
        assert core.serial_state()['drr'] == 0x1356
        assert core.serial_state()['tdxr_writes'] == 0

        # Exercise the actual bridge's codec-to-telephone-line conversion too.
        bridge = CourierDspBridge(XmfImage.load(Path(__file__).resolve().parents[1] / '2_3_33.XMF'))
        try:
            bridge.core.close()
            bridge.core = core
            bridge._take_line_audio()
            assert bridge._line_service['tx_peak_codec'] == pcm
            assert bridge._line_service['tx_peak_line'] > 0
            assert any(bridge._exchange_line_buffer)
        finally:
            core.close()
