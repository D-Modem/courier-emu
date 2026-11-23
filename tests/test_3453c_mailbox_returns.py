"""Guard the original post-carrier ISR return, not an injected carrier event."""
from pathlib import Path

import pytest

from courier_emu.firmware3453 import profile_for
from courier_emu.images import load_image
from courier_emu.machine import _MAILBOX_IRET_PCS

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('capture,actual', [
    ('3453bc-firmware-read-2.2.09', 0x6ed9a),
    ('3453c-5MBRZ16P0186-firmware-read-20261014', 0x6eefa),
])
def test_original_post_carrier_mailbox_iret_is_registered(capture, actual):
    path = ROOT / 'dumps' / capture / 'firmware.bin'
    image = load_image(path)
    profile = profile_for(image)
    canonical = 0x6eefa
    assert profile.address(canonical) == actual
    assert canonical in _MAILBOX_IRET_PCS
    # POP ES; POPA; MOV [FF02],8000; IRET in the unchanged supervisor.
    end = actual - 0x40000 + 1
    firmware = path.read_bytes()
    assert firmware[end - 9:end] == bytes.fromhex('0761c70602ff0080cf')
    # The RX callback still selected while CONNECT is being emitted aborts
    # the call on a key: OR [0694],80; MOV [0847],17. Hold DTE input until
    # the guest, not the harness, selects its online data receiver.
    start = (image.entry_segment << 4) + profile.abort_rx_callback - 0x40000
    assert firmware[start + 30:start + 40] == bytes.fromhex('800e940680c606470817')
