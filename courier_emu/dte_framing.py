"""The asynchronous DTE format published by the Courier attention adapter.

ATI4's active WORDLEN reader selects the active framing byte or the alternate
synchronous/leased format. ATI5's stored-profile reader lacks that selection.
Match the entire active-reader prologue so a stored-profile byte, another build's
RAM, or a coincidental immediate operand cannot be mistaken for the active one.
"""
import re

DTE_FRAMINGS = ('8N1', '7M1', '7O1', '7E1', 'stored')
_ACTIVE_WORDLEN = re.compile(
    rb'\xb0\x07\xf6\x06..\x04\x74\x0f\xf7\x06..\x04\x00\x74\x07'
    rb'\xf6\x06..\x07\xeb\x05\xf6\x06(..)\x07\x75\x02\xfe\xc0', re.S)


def locate_dte_framing(data: bytes) -> int | None:
    matches = list(_ACTIVE_WORDLEN.finditer(data))
    if len(matches) != 1:
        return None
    address = int.from_bytes(matches[0][1], 'little')
    return address if 0 < address < 0x8000 else None
