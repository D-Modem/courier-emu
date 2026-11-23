#!/usr/bin/env python3
"""Inspect captured Quad data-bank words for V.42 detection characters.

Offline analysis only: no modem state or decoded bytes are injected. Bank
words carry packed LSB-first bits, not necessarily terminal characters.
"""
import argparse
from collections import Counter
import json
from pathlib import Path


DETECTION_CHARACTERS = {"ODP": (0x11, 0x91), "ADP": (0x43, 0x45)}


def detection_run(words: list[int], characters: tuple[int, int]) -> dict:
    """Find the longest alternating 8N1 detection run in packed receive bits.

    Non-byte receive words break continuity rather than being silently
    truncated (e.g. the initial ffff bank contents). All offsets refer to the
    original receive-word stream. Mark counts exclude the character's stop bit.
    """
    bits = [(word >> bit) & 1 if 0 <= word <= 255 else None
            for word in words for bit in range(8)]
    longest = {"characters": 0, "start_bit": None, "end_bit": None,
               "first_character": None, "mark_bits_min": None, "mark_bits_max": None}
    current = None
    previous = None
    position = 0
    while position + 10 <= len(bits):
        frame = bits[position:position + 10]
        if frame[0] != 0 or frame[-1] != 1 or None in frame:
            position += 1
            continue
        value = sum(bit << index for index, bit in enumerate(frame[1:9]))
        if value in characters:
            marks = position - previous[0] - 10 if previous else None
            continuous = (previous is not None and value != previous[1]
                          and all(bit == 1 for bit in bits[previous[0] + 10:position]))
            if continuous:
                current["characters"] += 1
                current["end_bit"] = position + 10
                current["mark_bits_min"] = (marks if current["mark_bits_min"] is None
                                           else min(current["mark_bits_min"], marks))
                current["mark_bits_max"] = (marks if current["mark_bits_max"] is None
                                           else max(current["mark_bits_max"], marks))
            else:
                current = {"characters": 1, "start_bit": position, "end_bit": position + 10,
                           "first_character": value, "mark_bits_min": None, "mark_bits_max": None}
            previous = (position, value)
            if current["characters"] > longest["characters"]:
                longest = dict(current)
        else:
            previous = None
        position += 10
    return longest


def inspect(events: list[dict]) -> dict:
    receive = [event["word"] for event in events if event["direction"] == "dsp-to-cpu"]
    transmit = [event["word"] for event in events if event["direction"] == "cpu-to-dsp"]
    return {"captured_events": len(events), "receive_words": len(receive),
            "transmit_words": len(transmit),
            "transmit_common_words": [{"word": f"{word:04x}", "count": count}
                                      for word, count in Counter(transmit).most_common(8)],
            "receive_detection_runs": {name: detection_run(receive, characters)
                                       for name, characters in DETECTION_CHARACTERS.items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path, help="Quad data-lanes.json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = inspect(json.loads(args.capture.read_text()))
    report["source"] = str(args.capture)
    report["scope"] = "Captured bank events only; the probe may retain only a bounded prefix."
    text = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.write_text(text)
    print(text, end="")


if __name__ == "__main__":
    main()
