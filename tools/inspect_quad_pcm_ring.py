#!/usr/bin/env python3
"""Inspect access traces of the resident QF/I-modem eight-frame PCM ring.

Use --snapshot-read-range bd0:bdf with two --snapshot-frame arguments to
capture memory-events.json between frames. PC assignments are specific to the
resident firmware used by probe_quad_pair.py. This inspects ownership/order,
not waveform quality or the contents of the demodulated data.
"""
from __future__ import annotations

import argparse
import gzip
import json
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

# ISR RX store, datapump RX read, datapump TX store, ISR TX read.
PCS = {
    "quad": (0x840c, 0x80dd, 0x81b1, 0x840d),
    "imodem": (0x836e, 0x80d9, 0x8138, 0x836f),
}


def analyze(events, endpoint="quad"):
    rx_store, rx_load, tx_store, tx_load = PCS[endpoint]
    roles = {rx_store: "rx_write", rx_load: "rx_read",
             tx_store: "tx_write", tx_load: "tx_read"}
    counts = Counter()
    writes = {"rx": Counter(), "tx": Counter()}
    consumed = {"rx": {}, "tx": {}}
    previous = {}
    errors = []
    for event in events:
        role = roles.get(event["pc"])
        if role is None:
            continue
        address = event["address"]
        direction, operation = role.split("_")
        expected_parity = direction == "tx"
        if not 0xbd0 <= address <= 0xbdf or address % 2 != expected_parity:
            errors.append({"kind": "unexpected_address", "role": role, **event})
            continue
        counts[role] += 1
        if role in previous:
            expected = 0xbd0 + ((previous[role] - 0xbd0 + 2) % 16)
            if address != expected:
                counts[role + "_order_errors"] += 1
                errors.append({"kind": "order", "role": role, "expected": expected, **event})
        previous[role] = address
        if operation == "write":
            writes[direction][address] += 1
        else:
            current = writes[direction][address]
            # The trace can start mid-ring or have had its prefix pruned.
            if address in consumed[direction]:
                fresh = current - consumed[direction][address]
                if fresh != 1:
                    kind = "stale_read" if fresh == 0 else "overwritten_samples"
                    counts[direction + "_" + kind] += 1
                    errors.append({"kind": kind, "role": role, "fresh_writes": fresh, **event})
            consumed[direction][address] = current
    return {"endpoint": endpoint, "events": len(events), "counts": dict(counts),
            "errors": errors, "ok": not errors}


def compare_octets(transmitted, received):
    """Align overlapping captures and report internal insertions/deletions.

    Ignore unmatched capture edges, not unmatched samples inside the overlap.
    A 64-byte anchor avoids mistaking equal individual G.711 codewords for
    an alignment. Sample indices refer to the original captures.
    """
    source_offset = transmitted.find(received[:64]) if len(received) >= 64 else -1
    receive_offset = 0
    if source_offset < 0:
        source_offset = 0
        receive_offset = received.find(transmitted[:64]) if len(transmitted) >= 64 else -1
    if receive_offset < 0:
        return {"aligned": False, "ok": False, "slips": []}
    source, incoming = transmitted[source_offset:], received[receive_offset:]
    slips = []
    matched = 0
    for kind, a, b, c, d in SequenceMatcher(None, source, incoming, autojunk=False).get_opcodes():
        if kind == "equal":
            matched += b - a
        elif (kind == "replace" or (kind == "insert" and a < len(source))
              or (kind == "delete" and c < len(incoming))):
            slips.append({"kind": kind, "tx_index": a + source_offset,
                          "rx_index": c + receive_offset,
                          "transmitted": source[a:b].hex(), "received": incoming[c:d].hex()})
    return {"aligned": True, "source_offset": source_offset, "receive_offset": receive_offset,
            "matched_samples": matched, "slips": slips, "ok": not slips}


def compare_transport(quad, imodem):
    def stream(events, pc, shift):
        return bytes((e["value"] >> shift) & 255 for e in events if e["pc"] == pc)
    return {
        "quad_to_imodem": compare_octets(stream(quad, PCS["quad"][3], 0),
                                          stream(imodem, PCS["imodem"][0], 8)),
        "imodem_to_quad": compare_octets(stream(imodem, PCS["imodem"][3], 8),
                                          stream(quad, PCS["quad"][0], 0)),
    }


def load_events(path):
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == '.gz' else raw)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--endpoint", choices=PCS, default="quad")
    parser.add_argument("--peer-trace", type=Path, help="other endpoint's matching memory-events.json")
    args = parser.parse_args()
    events = load_events(args.trace)
    result = analyze(events, args.endpoint)
    if args.peer_trace:
        peer_events = load_events(args.peer_trace)
        quad, imodem = (events, peer_events) if args.endpoint == "quad" else (peer_events, events)
        result["transport"] = compare_transport(quad, imodem)
        result["ok"] = result["ok"] and all(side["ok"] for side in result["transport"].values())
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
