"""Assemble captured bootmodem/main/settings into a private 1 MiB flash image."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from courier_emu.flash_image import assemble_flash, CourierFlashImage


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bootmodem', type=Path, required=True)
    parser.add_argument('--normal', type=Path, required=True)
    parser.add_argument('--settings', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    archive = Path(__file__).resolve().parents[1] / '.artifact-archives'
    if not args.output.resolve().is_relative_to(archive.resolve()):
        parser.error('output must be inside .artifact-archives: settings contain credentials')
    data = assemble_flash(args.bootmodem.read_bytes(), args.normal.read_bytes(), args.settings.read_bytes())
    args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with args.output.open('xb') as stream:
        args.output.chmod(0o600)
        stream.write(data)
    # Validate both entry vectors and both DSP download tables.
    for mode in ('normal', 'bootmodem'):
        image = CourierFlashImage.load(args.output, mode)
        image.dsp_program_segments()
    print(f'Assembled {len(data)} bytes; both firmware modes validated: {args.output}')


if __name__ == '__main__':
    main()
