from pathlib import Path

import pytest

from courier_emu.images import load_image
from tools.audit_3453_line_control import audit, dial_stage_program


CAPTURE = Path('dumps/3453bc-firmware-read-2.2.09/firmware.bin')


@pytest.mark.skipif(not CAPTURE.exists(), reason='public B/C capture unavailable')
def test_line_audit_keeps_later_protocol_overlays_out_of_resident():
    from tools.c5x_disasm import decode
    words = dial_stage_program(load_image(CAPTURE))
    assert decode(words, 0x1f64).text == 'splk    @6d, #1f7c'
    assert decode(words, 0x20f5).text == 'splk    @1b, #2127'
    assert decode(words, 0x21d7).text == 'splk    @1b, #2208'
    assert words[0x1304 + 0x17] == 0x1de4  # genuine originate dispatch
    text = audit(CAPTURE)
    assert '6db02: in al, 0x5e' in text
    assert '21c8: lacc    #00008008' in text
    assert '67d6f: cmp cx, 0x2a' in text
    assert '67d72: ja 0x67d89' in text


def test_line_audit_rejects_unidentified_input(tmp_path):
    path = tmp_path / 'unknown.bin'
    path.write_bytes(b'not a firmware capture')
    with pytest.raises(ValueError, match='unmodified B/C'):
        audit(path)
