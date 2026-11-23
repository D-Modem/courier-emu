#!/usr/bin/env python3
"""Extract endpoint RTCP receiver reports; PBX RTP capture alone is not delivery proof.

Standard-library only. Supports classic Ethernet/raw-IPv4 and Linux cooked pcaps. Receiver loss
is the endpoint's report, not an independent near-end capture or a BER measure.
Exit 1 means reported loss or no selected report; exit 0 means selected reports
contain no reported loss, not proof of complete end-to-end modem acceptance.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import socket
import struct


def receiver_reports(payload: bytes) -> list[dict]:
    """Parse a compound RTCP datagram, preserving signed cumulative loss."""
    rows = []
    at = 0
    while at < len(payload):
        if at + 4 > len(payload):
            raise ValueError('truncated RTCP header')
        first, kind, length = struct.unpack_from('!BBH', payload, at)
        size = (length + 1) * 4
        if first >> 6 != 2 or at + size > len(payload):
            raise ValueError('invalid RTCP version or length')
        part = payload[at:at + size]
        at += size
        if first & 0x20:
            padding = part[-1]
            if at != len(payload) or not 0 < padding <= size - 4:
                raise ValueError('invalid RTCP padding')
            part = part[:-padding]
        if kind not in (200, 201):
            continue
        count = first & 31
        begin = 28 if kind == 200 else 8
        if len(part) < begin + 24 * count:
            raise ValueError('truncated RTCP sender/receiver report')
        row = dict(packet_type=kind, sender_ssrc=f'{struct.unpack_from("!I", part, 4)[0]:08x}', reports=[])
        if kind == 200:
            row['sender_packets'], row['sender_octets'] = struct.unpack_from('!II', part, 20)
        for k in range(count):
            b = part[begin + 24*k:begin + 24*(k+1)]
            ssrc = struct.unpack_from('!I', b)[0]
            highest, jitter, lsr, dlsr = struct.unpack_from('!IIII', b, 8)
            row['reports'].append(dict(source_ssrc=f'{ssrc:08x}',
                fraction_lost=b[4], fraction_lost_percent=b[4] * 100 / 256,
                cumulative_lost=int.from_bytes(b[5:8], 'big', signed=True),
                extended_highest_sequence=highest, jitter_samples=jitter,
                last_sr=lsr, delay_since_last_sr_seconds=dlsr / 65536))
        rows.append(row)
    return rows


def pcap_udp(data: bytes):
    """Yield unfragmented IPv4 UDP packets, retaining capture epoch and endpoints."""
    orders = {b'\xd4\xc3\xb2\xa1': '<', b'\xa1\xb2\xc3\xd4': '>'}
    if len(data) < 24 or data[:4] not in orders:
        raise ValueError('requires a classic microsecond pcap')
    order = orders[data[:4]]
    link = struct.unpack_from(order + 'I', data, 20)[0]
    if link not in (1, 12, 101, 113, 276):
        raise ValueError('requires Ethernet, Linux cooked or raw IPv4 capture')
    at = 24
    while at < len(data):
        if at + 16 > len(data):
            raise ValueError('truncated pcap record header')
        sec, usec, size, _ = struct.unpack_from(order + 'IIII', data, at)
        at += 16
        if at + size > len(data):
            raise ValueError('truncated pcap record')
        frame = data[at:at + size]
        at += size
        if link == 1:
            if len(frame) < 14:
                continue
            offset, ethertype = 14, struct.unpack_from('!H', frame, 12)[0]
            while ethertype in (0x8100, 0x88a8):
                if len(frame) < offset + 4:
                    raise ValueError('truncated VLAN header')
                ethertype = struct.unpack_from('!H', frame, offset + 2)[0]
                offset += 4
            if ethertype != 0x0800:
                continue
            ip = frame[offset:]
        elif link in (113, 276):
            # tcpdump -i any uses SLL (16 bytes) or SLL2 (20 bytes).
            # SLL puts the protocol at byte 14; SLL2 puts it first.
            offset, protocol_at = (16, 14) if link == 113 else (20, 0)
            if len(frame) < offset:
                raise ValueError('truncated Linux cooked header')
            if struct.unpack_from('!H', frame, protocol_at)[0] != 0x0800:
                continue
            ip = frame[offset:]
        else:
            ip = frame
        if len(ip) < 20 or ip[0] >> 4 != 4:
            continue
        ihl = (ip[0] & 15) * 4
        total = struct.unpack_from('!H', ip, 2)[0]
        if ip[9] != 17 or struct.unpack_from('!H', ip, 6)[0] & 0x3fff:
            continue
        if ihl < 20 or len(ip) < ihl + 8 or total < ihl + 8:
            raise ValueError('invalid IPv4 UDP header')
        sport, dport, length = struct.unpack_from('!HHH', ip, ihl)
        if length < 8 or ihl + length > min(total, len(ip)):
            raise ValueError('truncated IPv4 UDP payload')
        yield dict(epoch=sec + usec / 1e6, src=socket.inet_ntoa(ip[12:16]),
                   dst=socket.inet_ntoa(ip[16:20]), sport=sport, dport=dport), ip[ihl+8:ihl+length]


def analyze(data: bytes, ports: set[int], *, source: str | None = None,
            ssrc: str | None = None, clock_rate: float = 8000) -> dict:
    if not ports or any(not 0 < p < 65536 for p in ports) or not math.isfinite(clock_rate) or not clock_rate > 0:
        raise ValueError('valid RTCP ports and a positive RTP clock rate required')
    selected = []
    for endpoint, payload in pcap_udp(data):
        if not ports.intersection((endpoint['sport'], endpoint['dport'])):
            continue
        if source is not None and endpoint['src'] != source:
            continue
        for row in receiver_reports(payload):
            reports = [r for r in row['reports'] if ssrc is None or r['source_ssrc'] == ssrc]
            for r in reports:
                r['jitter_ms'] = r['jitter_samples'] * 1000 / clock_rate
            selected.append(endpoint | row | dict(reports=reports))
    reports = [r for row in selected for r in row['reports']]
    return dict(scope=dict(rtcp_ports=sorted(ports), reporter_ip=source, reported_ssrc=ssrc,
                          rtp_clock_rate=clock_rate),
                receiver_report_blocks=len(reports),
                endpoint_reports_loss=(any(r['cumulative_lost'] > 0 or r['fraction_lost'] > 0 for r in reports)
                                       if reports else None),
                max_interval_loss_percent=max((r['fraction_lost_percent'] for r in reports), default=None),
                reports=selected,
                warning='Endpoint-reported RTP loss, not BER or proof of the exact dropping hop. No report is not zero loss.')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('pcap', type=Path)
    ap.add_argument('--port', type=int, action='append', required=True, help='selected RTCP port (repeatable)')
    ap.add_argument('--source', help='reporting endpoint IPv4 address')
    ap.add_argument('--ssrc', help='reported RTP SSRC, hexadecimal')
    ap.add_argument('--clock-rate', type=float, default=8000)
    ap.add_argument('--output', type=Path)
    args = ap.parse_args()
    try:
        numeric_ssrc = int(args.ssrc, 16) if args.ssrc is not None else None
        if numeric_ssrc is not None and not 0 <= numeric_ssrc <= 0xffffffff:
            raise ValueError('SSRC must fit unsigned 32 bits')
        ssrc = f'{numeric_ssrc:08x}' if numeric_ssrc is not None else None
        result = analyze(args.pcap.read_bytes(), set(args.port), source=args.source,
                         ssrc=ssrc, clock_rate=args.clock_rate)
    except ValueError as e:
        ap.error(str(e))
    text = json.dumps(result, indent=2) + '\n'
    if args.output:
        args.output.write_text(text)
    else:
        print(text, end='')
    return 0 if result['receiver_report_blocks'] and not result['endpoint_reports_loss'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
