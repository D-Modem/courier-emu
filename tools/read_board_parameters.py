"""Read F8000..FBFFF twice via ATGR; save credential-bearing data privately."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from courier_emu.xmodem_sdl import Port
from courier_emu.parameters import checksum

ROW = re.compile(rb'^\s*([0-9A-Fa-f]{4}):([0-9A-Fa-f]{4})\s+((?:[0-9A-Fa-f]{4}\s+){7}[0-9A-Fa-f]{4})\s*$', re.M)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device', default='/dev/cu.usbserial-FT4TQOFT')
    parser.add_argument('--baud', type=int, default=19200)
    parser.add_argument('--serial', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    # Refuse destinations outside the repository's Git-ignored private archive.
    private = Path(__file__).resolve().parents[1] / '.artifact-archives'
    if not args.output.resolve().is_relative_to(private.resolve()):
        parser.error('output must be inside .artifact-archives (contains credentials)')
    args.output.mkdir(parents=True, mode=0o700, exist_ok=False)
    args.output.chmod(0o700)
    images = []
    with Port(args.device, args.baud) as port:
        port.drain(quiet=.3, limit=2)
        port.write(b'ATI7\r')
        time.sleep(.3)
        identity = port.drain(quiet=.5)
        if args.serial.encode() not in identity:
            raise RuntimeError('Unexpected board identity')
        (args.output / 'identity.txt').write_bytes(identity)
        for pass_number in (1, 2):
            image = bytearray()
            for offset in range(0, 0x4000, 0x100):
                page = None
                for attempt in range(1, 4):
                    port.write(f'ATGRF800:{offset:04X}\r'.encode())
                    time.sleep(.05)
                    raw = port.drain(quiet=.25, limit=5)
                    (args.output / f'pass{pass_number}-{offset:04x}-a{attempt}.txt').write_bytes(raw)
                    rows = list(ROW.finditer(raw))
                    if len(rows) != 16:
                        continue
                    if any(int(row[1], 16) != 0xF800 or int(row[2], 16) != offset + n * 16
                           for n, row in enumerate(rows)):
                        continue
                    page = b''.join(int(word, 16).to_bytes(2, 'little')
                                    for row in rows for word in row[3].split())
                    if len(page) == 256:
                        break
                    page = None
                if page is None:
                    raise RuntimeError(f'Invalid dump page at offset {offset:04x}; partial replies retained privately')
                image.extend(page)
            (args.output / f'f8000-fbfff-pass{pass_number}.bin').write_bytes(image)
            images.append(bytes(image))
            print(f'Pass {pass_number}: {len(image)} bytes captured.', flush=True)
    matches = images[0] == images[1]
    report = {'board_serial': args.serial, 'physical_start': '0xF8000',
              'bytes_per_pass': 16384, 'passes_match': matches,
              'sha256': [hashlib.sha256(data).hexdigest() for data in images],
              'memory_writes': False, 'sectors': []}
    for offset in range(0, 0x4000, 0x1000):
        sector = images[0][offset:offset+0x1000]
        report['sectors'].append({'address': hex(0xF8000 + offset),
                                 'erased': all(b == 255 for b in sector),
                                 'checksum_valid': checksum(sector) == int.from_bytes(sector[-2:], 'little')})
    if matches:
        (args.output / 'f8000-fbfff.bin').write_bytes(images[0])
    (args.output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    if not matches:
        raise RuntimeError('Settings passes differ; no verified combined image published')


if __name__ == '__main__':
    main()
