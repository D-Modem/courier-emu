from tools.inspect_quad_hdlc import FLAG, crc16, frames, interface_frames, lapm


def wire(data):
    fcs = crc16(data) ^ 0xffff
    bits = []
    ones = 0
    for byte in data + fcs.to_bytes(2, "little"):
        for bit in range(8):
            value = byte >> bit & 1
            bits.append(value)
            ones = ones + 1 if value else 0
            if ones == 5:
                bits.append(0)
                ones = 0
    return list(FLAG) + bits + list(FLAG)


def words(bits):
    bits = bits + [1] * (-len(bits) % 8)
    return [sum(bits[i + bit] << bit for bit in range(8)) for i in range(0, len(bits), 8)]


def test_x25_crc_known_vector_and_residue():
    assert crc16(b"123456789") == 0x6f91
    assert crc16(b"123456789" + bytes.fromhex("6e90")) == 0xf0b8


def test_bit_unaligned_stuffed_frame_and_high_bank_flags():
    raw = bytes.fromhex("030004") + b"\xff\x7e\xf8PAYLOAD"
    packed = [word | 0x4000 for word in words([1, 0, 1] + wire(raw))]
    found = frames(packed)
    assert len(found) == 1
    assert found[0]["crc_valid"]
    assert found[0]["start_bit"] == 3
    assert found[0]["kind"] == "I"
    assert found[0]["ns"] == 0 and found[0]["nr"] == 2
    assert found[0]["payload_hex"] == raw[3:].hex()


def test_shared_delimiter_idle_flags_and_bad_crc_do_not_invent_frames():
    first, second = wire(bytes.fromhex("030102")), wire(bytes.fromhex("030506"))
    bad = wire(bytes.fromhex("0363"))
    bad[10] ^= 1
    found = frames(words(list(FLAG) * 4 + first + second[8:] + bad))
    assert [frame["kind"] for frame in found if frame["crc_valid"]] == ["RR", "RNR"]
    assert any(not frame["crc_valid"] for frame in found)


def test_framed_octet_interface_preserves_fcs_and_distinguishes_dsp_generated_crc():
    data = bytes.fromhex("030109")
    raw = data + (crc16(data) ^ 0xffff).to_bytes(2, "little")
    events = ([{"direction": "dsp-to-cpu", "word": word} for word in [*raw, 0x1000]]
              + [{"direction": "cpu-to-dsp", "word": word}
                 for word in [0xff00, *data, 0x10f3, 0x10f3, 0xff00]])
    received = interface_frames(events, "dsp-to-cpu")
    sent = interface_frames(events, "cpu-to-dsp")
    assert len(received) == len(sent) == 1
    assert received[0]["crc_valid"] is True
    assert received[0]["kind"] == sent[0]["kind"] == "RR"
    assert received[0]["nr"] == sent[0]["nr"] == 4
    assert sent[0]["crc_valid"] is None  # TX FCS is not present in the host words.


def test_receive_mode_transition_does_not_prefix_detection_bits_to_first_hdlc_frame():
    raw = bytes.fromhex("030109b1ad")
    events = [{"direction": "dsp-to-cpu", "word": word}
              for word in [255, 17, 0x91, 0xff00, *raw, 0x1000]]
    found = interface_frames(events, "dsp-to-cpu")
    assert len(found) == 1 and found[0]["crc_valid"]
    assert found[0]["kind"] == "RR"
    found = interface_frames([{"direction": "dsp-to-cpu", "word": word}
                              for word in [*raw, 0xff00]], "dsp-to-cpu", 0xff00)
    assert len(found) == 1 and found[0]["crc_valid"]


def test_unknown_interface_status_breaks_continuity_instead_of_inventing_bytes():
    events = [{"direction": "dsp-to-cpu", "word": word}
              for word in [3, 1, 9, 0x2000, 0xb1, 0xad, 0x1000]]
    found = interface_frames(events, "dsp-to-cpu")
    assert len(found) == 1
    assert not found[0]["crc_valid"]
    assert "kind" not in found[0]


def test_lapm_extended_supervisory_and_unnumbered_controls():
    assert lapm(bytes.fromhex("030980")) == {"address": 3, "kind": "REJ", "nr": 64, "pf": 0}
    assert lapm(bytes.fromhex("037f"))["kind"] == "SABME"
    assert lapm(bytes.fromhex("0373"))["kind"] == "UA"
    assert lapm(bytes.fromhex("0353"))["kind"] == "DISC"
