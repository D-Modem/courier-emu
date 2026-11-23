#!/usr/bin/env python3
"""Build the hardware-only Apple backend, reusing v90modem's audio utilities."""
from pathlib import Path
import argparse
import os
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def build(v90modem: Path, output: Path) -> Path:
    if sys.platform != "darwin":
        raise RuntimeError("Apple line hardware requires macOS")
    source = v90modem.resolve() / "tools"
    if not (source / "apple_usb_modem_audio.m").is_file():
        raise FileNotFoundError(f"missing {source / 'apple_usb_modem_audio.m'}")
    flags = shlex.split(subprocess.check_output(
        ["pkg-config", "--cflags", "--libs", "libusb-1.0"], text=True))
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([os.environ.get("CC", "clang"), "-O2", "-std=gnu11", "-fblocks",
                    "-I", str(source), str(ROOT / "native/apple_line.m"),
                    "-framework", "AVFoundation", "-framework", "AudioToolbox",
                    "-framework", "CoreAudio", "-framework", "Foundation",
                    *flags, "-o", str(output)], check=True)
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v90modem", type=Path, default=ROOT.parent / "v90modem")
    parser.add_argument("--output", type=Path, default=ROOT / ".build/apple_line")
    args = parser.parse_args()
    print(build(args.v90modem, args.output))
