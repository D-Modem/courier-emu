#!/usr/bin/env python3
"""Write the idsdl403 settings EEPROM with other feature records.

The six feature records (ATY14's fields: 1 country, 2 features, 3 type2,
4 type1, 5 and 6 unused) are three encoded octets each, at byte 0xbc of the
part, in the order 2, 3, 4, 5, 6, 1. The encoding is the inverse of the
decoder at 7.1.4's d929 (and IDSDL302's e237). The checksum byte at 511 is
made again, so the boot block accepts the part.

    PYTHONPATH=. .venv/bin/python tools/feature_nvram.py out.sav --features 15

Use the file with tools/probe_v90modem_closed_loop.py (COURIER_NVRAM) to call
D-Modem's x2 upgrade host (AT+X2UP=2) with a Courier that has no x2 bit.
"""
import argparse
from pathlib import Path

from courier_emu.nvram import (CHECKSUM_BYTE, IDSDL403_NVRAM,
                               encode_idsl302_record, settings_checksum)

RECORDS_BYTE = 0xBC
ORDER = (2, 3, 4, 5, 6, 1)


def decode_fixture():
    """The six records of the fixture, record 1 first."""
    values = {}
    for i, rec in enumerate(ORDER):
        for v in range(256):
            if encode_idsl302_record(v) == IDSDL403_NVRAM[RECORDS_BYTE + 3 * i:RECORDS_BYTE + 3 * i + 3]:
                values[rec] = v
                break
    return [values[r] for r in range(1, 7)]


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('output', type=Path)
    p.add_argument('--features', type=int, help='record 2 (ATC8), for example 15')
    p.add_argument('--country', type=int, help='record 1 (ATC10)')
    args = p.parse_args()
    recs = decode_fixture()
    if args.country is not None:
        recs[0] = args.country
    if args.features is not None:
        recs[1] = args.features
    data = bytearray(IDSDL403_NVRAM)
    data[RECORDS_BYTE:RECORDS_BYTE + 18] = b''.join(
        encode_idsl302_record(recs[r - 1]) for r in ORDER)
    data[CHECKSUM_BYTE] = settings_checksum(data)
    args.output.write_bytes(data)
    print('records', ','.join('%03d' % v for v in recs))


if __name__ == '__main__':
    main()
