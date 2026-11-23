import struct

import pytest

from tools.analyze_rtcp import analyze, main, pcap_udp, receiver_reports


def report(*, kind=200, lost=177, fraction=21, ssrc=0x0c8d583e):
    block = struct.pack('!IB', ssrc, fraction) + lost.to_bytes(3, 'big', signed=True)
    block += struct.pack('!IIII', 5488, 4, 123, 32768)
    body = struct.pack('!I', 0x16270498)
    if kind == 200:
        body += struct.pack('!IIIII', 0, 0, 0, 2514, 402240)
    body += block
    return struct.pack('!BBH', 0x81, kind, len(body)//4) + body


def pcap(payload, *, source=b'\x0a\x45\x46\xdd', port=6031, vlan=False):
    udp = struct.pack('!HHHH', port, 11421, len(payload)+8, 0) + payload
    ip = struct.pack('!BBHHHBBH4s4s', 0x45, 0, 20+len(udp), 0, 0, 64, 17, 0,
                     source, b'\xc0\xa8\x58\x7a') + udp
    frame = bytes(12) + (b'\x81\x00\x00\x01\x08\x00' if vlan else b'\x08\x00') + ip
    return struct.pack('<IHHIIII', 0xa1b2c3d4, 2, 4, 0, 0, 65535, 1) + struct.pack('<IIII', 1, 234000, len(frame), len(frame)) + frame


@pytest.mark.parametrize('kind', [200, 201])
def test_receiver_report_fields(kind):
    row, = receiver_reports(report(kind=kind))
    assert row['sender_ssrc'] == '16270498'
    r, = row['reports']
    assert r['source_ssrc'] == '0c8d583e'
    assert r['fraction_lost_percent'] == 8.203125
    assert r['cumulative_lost'] == 177
    assert r['jitter_samples'] == 4
    assert r['delay_since_last_sr_seconds'] == .5
    if kind == 200:
        assert row['sender_packets'] == 2514


def test_negative_cumulative_loss_is_signed():
    assert receiver_reports(report(lost=-2))[0]['reports'][0]['cumulative_lost'] == -2


def test_compound_sdes_and_padding():
    sr = report()
    sdes = struct.pack('!BBH', 0x81, 202, 3) + bytes(12)
    assert len(receiver_reports(sr+sdes)) == 1
    padded = bytes([sr[0] | 0x20]) + sr[1:2] + struct.pack('!H', len(sr)//4) + sr[4:] + b'\0\0\0\x04'
    assert receiver_reports(padded) == receiver_reports(sr)
    with pytest.raises(ValueError, match='padding'):
        receiver_reports(padded+sdes)


@pytest.mark.parametrize('data', [b'\x80', report()[:-1], b'\x01'+report()[1:], b'\x81\xc8\x00\x00'])
def test_invalid_rtcp_is_not_zero_loss(data):
    with pytest.raises(ValueError):
        receiver_reports(data)


@pytest.mark.parametrize('vlan', [False, True])
def test_pcap_scope_and_clock(vlan):
    result = analyze(pcap(report(), vlan=vlan), {6031}, source='10.69.70.221', ssrc='0c8d583e')
    assert result['endpoint_reports_loss']
    assert result['receiver_report_blocks'] == 1
    assert result['reports'][0]['epoch'] == 1.234
    assert result['reports'][0]['reports'][0]['jitter_ms'] == .5
    for args in [dict(source='192.0.2.1'), dict(ssrc='ffffffff')]:
        missing = analyze(pcap(report()), {6031}, **args)
        assert missing['receiver_report_blocks'] == 0
        assert missing['endpoint_reports_loss'] is None
        assert missing['max_interval_loss_percent'] is None


@pytest.mark.parametrize('clock_rate', [0, -1, float('nan'), float('inf')])
def test_invalid_clock_is_rejected(clock_rate):
    with pytest.raises(ValueError):
        analyze(pcap(report()), {6031}, clock_rate=clock_rate)


def test_no_report_is_not_zero_loss():
    sr = struct.pack('!BBH', 0x80, 200, 6) + bytes(24)
    assert analyze(pcap(sr), {6031})['receiver_report_blocks'] == 0
    assert analyze(pcap(report(), port=9999), {6031})['receiver_report_blocks'] == 0


@pytest.mark.parametrize('payload,expected', [
    (report(), 1),
    (report(lost=0, fraction=0), 0),
    (struct.pack('!BBH', 0x80, 200, 6) + bytes(24), 1),
])
def test_cli_retains_evidence_and_does_not_pass_loss_or_missing(tmp_path, monkeypatch, payload, expected):
    path, output = tmp_path/'test.pcap', tmp_path/'out.json'
    path.write_bytes(pcap(payload))
    monkeypatch.setattr('sys.argv', ['analyze_rtcp', str(path), '--port', '6031', '--output', str(output)])
    assert main() == expected
    assert output.exists()


@pytest.mark.parametrize('link,size,protocol_at', [(113, 16, 14), (276, 20, 0)])
def test_linux_cooked_capture_preserves_reports_and_checks_headers(link, size, protocol_at):
    original = pcap(report())
    header = bytearray(original[:24])
    struct.pack_into('<I', header, 20, link)

    def cooked(protocol=0x0800, truncate=False):
        prefix = bytearray(size)
        struct.pack_into('!H', prefix, protocol_at, protocol)
        frame = bytes(prefix[:-1]) if truncate else bytes(prefix) + original[54:]
        return bytes(header) + struct.pack('<IIII', 1, 234000, len(frame), len(frame)) + frame

    assert analyze(cooked(), {6031}) == analyze(original, {6031})
    assert list(pcap_udp(cooked(protocol=0x86dd))) == []
    with pytest.raises(ValueError, match='Linux cooked header'):
        list(pcap_udp(cooked(truncate=True)))


@pytest.mark.parametrize('data', [b'', pcap(report())[:-1], pcap(report())[:30]])
def test_pcap_truncation_is_not_zero_loss(data):
    with pytest.raises(ValueError):
        list(pcap_udp(data))
