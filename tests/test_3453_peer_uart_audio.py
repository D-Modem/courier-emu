"""Independent WAV decoder controls; no modem firmware or receive-byte injection."""
import math

import pytest

from tools.decode_3453_peer_uart import decode


@pytest.mark.parametrize('mark,space', [(2225, 2025), (1270, 1070)])
@pytest.mark.parametrize('rate', [7200, 8000])
def test_independent_bell103_uart_decoder(mark, space, rate):
    payload = b'UART\r\x00\xff\x55\xaa'
    bits = [1] * 32
    for value in payload:
        bits.extend([0, *[(value >> k) & 1 for k in range(8)], 1])
    bits.extend([1] * 32)
    phase = 0.37
    native = []
    for bit in bits:
        for _ in range(24):
            native.append(round(3000 * math.sin(phase)))
            phase += 2 * math.pi * (mark if bit else space) / 7200
    samples = [native[min(len(native) - 1, i * 7200 // rate)]
               for i in range(len(native) * rate // 7200)]
    runs = decode(samples, rate, mark, space)
    assert any(payload in bytes.fromhex(row['hex']) for row in runs)
