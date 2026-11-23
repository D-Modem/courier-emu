from tools.inspect_quad_v42 import detection_run, inspect


def packed(characters, marks=9, prefix=7):
    bits = [1] * prefix
    for character in characters:
        bits += [0] + [(character >> bit) & 1 for bit in range(8)] + [1] * (1 + marks)
    bits += [1] * (-len(bits) % 8)
    return [sum(bits[offset + bit] << bit for bit in range(8))
            for offset in range(0, len(bits), 8)]


def test_odp_is_packed_bits_not_terminal_bytes():
    words = packed([0x11, 0x91] * 12)
    run = detection_run(words, (0x11, 0x91))
    assert run == {"characters": 24, "start_bit": 7, "end_bit": 7 + 23 * 19 + 10,
                   "first_character": 0x11, "mark_bits_min": 9, "mark_bits_max": 9}
    assert detection_run(words, (0x43, 0x45))["characters"] == 0


def test_detects_adp_and_preserves_original_offsets_after_invalid_words():
    words = [0xffff] * 6 + packed([0x43, 0x45] * 5, marks=12)
    run = detection_run(words, (0x43, 0x45))
    assert run["characters"] == 10
    assert run["start_bit"] == 48 + 7
    assert run["mark_bits_min"] == run["mark_bits_max"] == 12


def test_invalid_receive_words_do_not_join_runs():
    words = packed([0x11, 0x91] * 3)
    run = detection_run(words + [0xffff] + words, (0x11, 0x91))
    assert run["characters"] == 6
    assert run["start_bit"] == 7


def test_unexpected_character_breaks_alternation():
    words = packed([0x11, 0x91, 0x55, 0x11, 0x91, 0x11])
    assert detection_run(words, (0x11, 0x91))["characters"] == 3
    words = packed([0x11] * 5)
    assert detection_run(words, (0x11, 0x91))["characters"] == 1


def test_empty_capture_and_direction_separation():
    assert inspect([])["receive_detection_runs"]["ODP"]["characters"] == 0
    events = [{"direction": "cpu-to-dsp", "bank": 0, "word": 0x40ff}] * 4
    events += [{"direction": "dsp-to-cpu", "bank": i % 6, "word": word}
               for i, word in enumerate(packed([0x11, 0x91] * 3))]
    report = inspect(events)
    assert report["transmit_common_words"] == [{"word": "40ff", "count": 4}]
    assert report["receive_detection_runs"]["ODP"]["characters"] == 6
