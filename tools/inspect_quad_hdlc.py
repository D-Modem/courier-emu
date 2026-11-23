#!/usr/bin/env python3
"""Decode captured packed Quad bank bits as HDLC, offline and CRC checked."""
import argparse
from collections import Counter
import gzip
import json
from pathlib import Path

FLAG = (0, 1, 1, 1, 1, 1, 1, 0)


def crc16(data):
    crc = 0xffff
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0x8408 if crc & 1 else 0)
    return crc


def frames(words):
    # The original supervisor dispatches AX with CX=8: low bits first.
    bits = [(word >> bit) & 1 for word in words for bit in range(8)]
    previous = None
    position = 0
    result = []
    while position + 8 <= len(bits):
        if tuple(bits[position:position + 8]) != FLAG:
            position += 1
            continue
        if previous is not None and position > previous + 8:
            stuffed = bits[previous + 8:position]
            data = []
            ones = 0
            valid = True
            for bit in stuffed:
                if ones == 5:
                    if bit:
                        valid = False
                        break
                    ones = 0
                    continue
                data.append(bit)
                ones = ones + 1 if bit else 0
            if ones == 5:  # A mandatory stuffed zero cannot be omitted.
                valid = False
            if valid and data and len(data) % 8 == 0:
                raw = bytes(sum(data[i + bit] << bit for bit in range(8))
                            for i in range(0, len(data), 8))
                item = {"start_bit": previous, "end_bit": position + 8,
                        "octets": len(raw), "hex": raw.hex(),
                        "crc_valid": len(raw) >= 4 and crc16(raw) == 0xf0b8}
                if item["crc_valid"]:
                    item.update(lapm(raw[:-2]))
                result.append(item)
        previous = position
        position += 8
    return result


def lapm(data):
    if len(data) < 2:
        return {"kind": "short"}
    control = data[1]
    result = {"address": data[0]}
    if not control & 1 and len(data) >= 3:
        result.update(kind="I", ns=control >> 1, nr=data[2] >> 1,
                      pf=data[2] & 1, payload_hex=data[3:].hex())
    elif control & 3 == 1 and len(data) >= 3:
        result.update(kind={0: "RR", 1: "RNR", 2: "REJ", 3: "SREJ"}[(control >> 2) & 3],
                      nr=data[2] >> 1, pf=data[2] & 1)
    else:
        result.update(kind={0x6f: "SABME", 0x63: "UA", 0x43: "DISC", 0x0f: "DM",
                            0x87: "FRMR", 0xaf: "XID"}.get(control & ~0x10, "U"),
                      control=control, pf=bool(control & 0x10))
    return result


def interface_frames(events, direction, rx_delimiter=0x1000):
    """Later firmware modes use framed octets, not the earlier raw-bit path.

    RX 1000 terminates frames with their received FCS. TX 10f3 terminates
    host-supplied octets; the DSP generates the flags, stuffing and FCS.
    Preserve other status values rather than guessing what their bits mean.
    """
    pending = bytearray()
    result = []
    for event in events:
        if event["direction"] != direction:
            continue
        word = event["word"]
        if 0 <= word <= 255:
            pending.append(word)
        elif (direction == "cpu-to-dsp" and word == 0x10f3
              or direction == "dsp-to-cpu" and word == rx_delimiter):
            if pending:
                raw = bytes(pending)
                valid = (len(raw) >= 4 and crc16(raw) == 0xf0b8
                         if direction == "dsp-to-cpu" else None)
                item = {"hex": raw.hex(), "octets": len(raw), "crc_valid": valid,
                        "status": word, "cycle": event.get("cycles"),
                        "frame": event.get("frame")}
                if direction == "cpu-to-dsp" or valid:
                    item.update(lapm(raw if direction == "cpu-to-dsp" else raw[:-2]))
                result.append(item)
            pending.clear()
        elif word != 0xff00 or direction == "dsp-to-cpu":
            # Quad's ff00 transition separates detection bits from framed
            # octets. On TX it is an idle token, not an application octet.
            pending.clear()
    return result


def inspect(events, rx_delimiter=0x1000):
    report = {}
    for direction in ("cpu-to-dsp", "dsp-to-cpu"):
        captured = frames([event["word"] for event in events if event["direction"] == direction])
        valid = [frame for frame in captured if frame["crc_valid"]]
        octets = interface_frames(events, direction, rx_delimiter)
        report[direction] = {"candidate_frames": len(captured), "valid_frames": len(valid),
                             "kinds": dict(Counter(frame["kind"] for frame in valid)),
                             "frames": valid, "interface_frames": octets,
                             "interface_kinds": dict(Counter(frame.get("kind", "bad FCS") for frame in octets)),
                             "status_words": {f"{word:04x}": count for word, count in Counter(
                                 event["word"] for event in events if event["direction"] == direction
                                 and event["word"] > 255).most_common(16)}}
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--rx-delimiter", type=lambda value: int(value, 0), default=0x1000,
                        help="framed RX terminator: Quad 0x1000 (default), I-modem 0xff00")
    args = parser.parse_args()
    text = (gzip.decompress(args.capture.read_bytes()).decode("utf-8")
            if args.capture.suffix == ".gz" else args.capture.read_text())
    report = inspect(json.loads(text), args.rx_delimiter)
    report["rx_delimiter"] = f"{args.rx_delimiter:04x}"
    report["scope"] = "Bounded captured bank words only; no data is fed to either modem."
    text = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.write_text(text)
    print(text, end="")


if __name__ == "__main__":
    main()
