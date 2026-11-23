/* Manual C semantic reconstruction: first-x2 I-modem IM020104.NAC.
 * Not vendor source or a complete modem. DSP PCs are word addresses.
 * These server/symmetric routines also implement digital bearer modes;
 * a 7-bit DS0 word is not the analogue x2 six-symbol PCM rate ladder.
 */
#include <stdint.h>
#include <stdbool.h>

/* e2b1/e2d4/e2db/e438: bounded semantic model of the symmetric startup
 * receiver.  The firmware stores these fields in the DP=7 work page and
 * uses delayed calls through the callbacks at e43a/e460.  Keeping the
 * protocol state explicit makes the qualification rules testable without
 * pretending that the callback ABI is fully lifted yet. */
typedef struct {
    uint16_t state;       /* 0: run-in, 1: separator, 2: probe pairs */
    uint16_t run_count;
    uint16_t zero_count;
    uint16_t pair_index;
    uint16_t bitmap;
} server_training_rx;

/* Accept the receiver's documented low-bit tolerance. */
static bool server_training_match(uint16_t actual, uint16_t expected)
{
    return actual == expected || ((actual ^ expected) == 1u);
}

/* Consume one startup word. Returns 0 while acquiring, 1 on a complete
 * probe-pair step, 2 when all 128 pairs have qualified, and 0xffff when the
 * word forces a restart. The bitmap records the six-position phase for
 * tolerated low-bit errors; it is deliberately separate from pair_index. */
uint16_t server_training_receiver_step(server_training_rx *rx,
                                       uint16_t word)
{
    if (rx->state == 0) {
        if (!server_training_match(word, 0x7e)) {
            rx->run_count = 0;
            rx->zero_count = 0;
            rx->pair_index = 0;
            rx->bitmap = 0;
            return 0xffffu;
        }
        if (++rx->run_count == 7) {
            rx->state = 1;
            rx->zero_count = 0;
        }
        return 0;
    }
    if (rx->state == 1) {
        if (word > 1) {
            rx->state = 0;
            rx->run_count = server_training_match(word, 0x7e) ? 1 : 0;
            rx->zero_count = 0;
            rx->pair_index = 0;
            rx->bitmap = 0;
            return 0xffffu;
        }
        if (++rx->zero_count == 7) rx->state = 2;
        return 0;
    }
    uint16_t expected = rx->pair_index;
    uint16_t complement = (uint16_t)(0xffu - expected);
    if (!server_training_match(word, expected)) {
        rx->state = 0;
        rx->run_count = 0;
        rx->zero_count = 0;
        rx->pair_index = 0;
        rx->bitmap = 0;
        return 0xffffu;
    }
    /* The delayed callback consumes the complement separately; retain the
     * first word's low-bit phase until server_training_receiver_pair(). */
    rx->bitmap |= (uint16_t)(((word ^ expected) & 1u) << (expected % 6));
    rx->state = 3;
    (void)complement;
    return 1;
}

/* Complete the second half of a pair. Kept separate because the original
 * e438 state machine returns through a delayed callback between words. */
uint16_t server_training_receiver_pair(server_training_rx *rx, uint16_t word)
{
    if (rx->state != 3) return 0xffffu;
    uint16_t expected = (uint16_t)(0xffu - rx->pair_index);
    if (!server_training_match(word, expected)) {
        rx->state = 0; rx->run_count = rx->zero_count = rx->pair_index = 0;
        rx->bitmap = 0;
        return 0xffffu;
    }
    /* Record the complement's phase as well. This is diagnostic state only;
     * pair_index remains the protocol position and is not derived from it. */
    rx->bitmap |= (uint16_t)(((word ^ expected) & 1u)
                             << ((rx->pair_index * 2u + 1u) % 6u));
    if (++rx->pair_index == 128) {
        rx->state = 0; rx->run_count = 0; rx->zero_count = 0;
        rx->pair_index = 0;
        return 2;
    }
    rx->state = 2;
    return 1;
}

void server_lane_source(uint16_t d[65536], uint16_t io[65536], uint16_t page);
void server_lane_sink(uint16_t d[65536], uint16_t io[65536],
                      uint16_t output[65536], uint16_t page);

/* e6fe..e731: source selected by 039f bit 15. Normal DP=7 falls back
 * to PA6 after setting the empty sentinel. Other pages patch the IN operand
 * at e71c from [0987]. Data address 0057 aliases board status port 57;
 * successful transfers acknowledge its shifted mask in the RETD delay slot.
 * Scratch ST0 saves and self-modified program words are not modeled. */
void server_stream_source(uint16_t d[65536], uint16_t io[65536], uint16_t page)
{
    d[page] = 0xff00;
    if (page == 0x380) {
        server_lane_source(d, io, page);
        return;
    }
    uint16_t cursor = d[0x987];
    uint16_t mask = (uint16_t)(d[0x9fb] << (cursor & 15));
    if (io[0x57] & mask) {
        d[0x980] = io[cursor];
        d[0x987] = (cursor == 0x67) ? 0x62 : (uint16_t)(cursor + 1);
        io[0x57] &= (uint16_t)~mask;
    } else if (d[0x39f] & 0x4000u) {
        d[0x987] = 0x62;
    }
}

/* e732..e767: bit 1 at page+71 suppresses repeated ff00 ONLY. The
 * last word updates even on a full sink. Normal DP=6 falls back to PA6;
 * other pages patch the OUT operand at e75b from [09a7], but output the
 * word from [09a0]. Data [0057] again aliases the board acknowledgement. */
void server_stream_sink(uint16_t d[65536], uint16_t io[65536],
                       uint16_t output[65536], uint16_t page)
{
    if ((d[page+0x71] & 2u) && d[page+0x72] == 0xff00u &&
        d[page+0x20] == 0xff00u)
        return;
    d[page+0x72] = d[page+0x20];
    if (page == 0x300) {
        server_lane_sink(d, io, output, page);
        return;
    }
    uint16_t cursor = d[0x9a7];
    uint16_t mask = (uint16_t)(d[0x9fb] << ((cursor + 8) & 15));
    if (io[0x57] & mask) {
        output[cursor] = d[0x9a0];
        d[0x9a7] = (cursor == 0x67) ? 0x62 : (uint16_t)(cursor + 1);
        io[0x57] &= (uint16_t)~mask;
    }
}

/* 843e..8456: PA6 source. Empty lanes preserve the caller's sentinel;
 * flag 14 resets the cursor only on an empty read. PA6 is write-one-clear. */
void server_lane_source(uint16_t d[65536], uint16_t io[65536], uint16_t page)
{
    uint16_t cursor = d[page+7];
    uint16_t mask = (uint16_t)(d[page+0x7b] << (cursor & 7));
    if (io[0x56] & mask) {
        d[page] = io[cursor];
        d[page+7] = cursor + 1;
        io[0x56] &= (uint16_t)~mask;
    } else if (d[0x39f] & 0x4000u) d[page+7] = 0x58;
}

/* 84a0..84ae: local PA6 sink. High-byte PA6 bits mean host room; outgoing
 * lane storage is separate from incoming io[], as on the emulated board.
 * A full lane drops the word, leaves the cursor, and does not acknowledge.
 */
void server_lane_sink(uint16_t d[65536], uint16_t io[65536],
                      uint16_t output[65536], uint16_t page)
{
    uint16_t cursor = d[page+0x27];
    uint16_t mask = (uint16_t)(d[page+0x7b] << (cursor & 15));
    if (io[0x56] & mask) {
        output[cursor] = d[page+0x20];
        d[page+0x27] = cursor + 1;
        io[0x56] &= (uint16_t)~mask;
    }
}

/* 8483..8499: LSB-first width conversion into octets, local sink only.
 * Count starts 0..7; width 1..9. Firmware consumes every assembled octet
 * even when the sink is full. It does not retry or restore the reservoir.
 */
void server_receive_octets(uint16_t d[65536], uint16_t io[65536],
                           uint16_t output[65536], uint16_t page)
{
    uint32_t reservoir = d[page+0x24] |
        ((uint32_t)d[page+0x20] << d[page+0x25]);
    unsigned count = d[page+0x25] + d[page+0x22];
    d[page+0x24] = (uint16_t)reservoir;
    while (count >= 8) {
        count -= 8;
        d[page+0x25] = count;
        d[page+0x20] = reservoir & 0xffu;
        server_lane_sink(d, io, output, page);
        reservoir >>= 8;
        d[page+0x24] = (uint16_t)reservoir;
    }
    d[page+0x25] = count;
}

void server_tag70(uint16_t d[65536], uint16_t value) /* 91a1..91ad */
{
    d[0xffdb] = value & 0x3fffu;
    d[0xffd9] |= 0x8000u;
}
void server_tag71(uint16_t d[65536], uint16_t value) /* 91ae..91b0 */
{
    d[0xffda] = value;
}

/* e7e7..e7f1: reverse the low octet, discarding bits above bit 7. */
uint16_t server_reverse_octet(uint16_t value)
{
    uint16_t result = 0;
    for (unsigned bit = 0; bit < 8; ++bit)
        result |= ((value >> bit) & 1u) << (7 - bit);
    return result;
}

/* 927f..928b: choose the advertised capability and zero its work area.
 * Original then tail-calls the bitfield writer 9617 at offset 16.
 * Separate selection from that writer so its unresolved ABI stays visible.
 */
uint16_t server_select_capability(uint16_t d[65536])
{
    uint16_t value = d[(d[0x039f] & 0x1000u) ? 0xffdb : 0xffdc];
    d[0xfef0] = 0;
    d[0xfef1] = 0;
    return value;
}

/* 927f through tail-call 9617: actual two-word capability packing.
 * Entry DP=7, d[03fb]=1 (writer's unit mask); writes field at offset 16.
 * The word straddles the 17-bit INFO0 work buffer: low bit in fef1 bit 15,
 * remaining bits in fef0. With SXM=1, ADDT sign-extends the source; a base
 * capability with bit 15 set also sets the unused high bit of fef0.
 * This models data effects, not scratch registers.
 */
void server_pack_info0_capability(uint16_t d[65536])
{
    uint16_t value = server_select_capability(d);
    d[0xfef1] = (uint16_t)(value << 15);
    d[0xfef0] = (uint16_t)((int16_t)value >> 1);
}

/* e172..e179: actual control-flow destinations, not guessed protocol names.
 * A call to e822 is followed by e61d on return.
 */
uint16_t server_mode_family_target(uint16_t mode)
{
    if (mode & 4u) return 0xe60bu;
    if (mode & 2u) return 0xe822u;
    return 0xe61du;
}

/* e1d2..e202: asymmetric startup probe source. The state identifier is
 * the original function pointer at page+75; this preserves delayed RETD
 * writes. No claim is made about the receiver's interpretation or timing.
 */
uint16_t server_probe_word(uint16_t d[65536], uint16_t page)
{
    uint16_t old;
    switch (d[page+0x75]) {
    case 0xe1d2:
        if (--d[page+0x74] == 0) {
            d[page+0x74] = 7; d[page+0x75] = 0xe1dd;
        }
        return 0x7e;
    case 0xe1dd:
        if (--d[page+0x74] == 0) {
            d[page+0x73] = 0; d[page+0x74] = 0xff;
            d[page+0x75] = 0xe1ea;
        }
        return 0;
    case 0xe1ea:
        old = d[page+0x73]++;
        d[page+0x75] = 0xe1f2;
        return old;
    case 0xe1f2:
        old = d[page+0x74];
        if (--d[page+0x74] == 0x7f) {
            d[page+0x74] = 0x6d3; d[page+0x75] = 0xe1d2;
        } else d[page+0x75] = 0xe1ea;
        return old;
    default: return 0; /* outside the recovered four-state source */
    }
}

/* Equivalent recurrence of 8faa (GPC TX) and direct entry 8fe1 (GPC RX).
 * Each operates on its caller's DP page, not a fixed absolute state address.
 * Width 1..9; count determines a contiguous low-bit mask in these tests.
 */
static uint16_t shift_bits(uint32_t *history, uint16_t value,
                            unsigned count, unsigned tap, bool receive)
{
    uint32_t state = *history & 0x7fffffu;
    uint16_t result = 0;
    for (unsigned bit = 0; bit < count; ++bit) {
        unsigned incoming = (value >> bit) & 1u;
        unsigned output = incoming ^ ((state >> (23u - tap)) & 1u)
                                   ^ (state & 1u);
        result |= (uint16_t)(output << bit);
        state = (state >> 1) | ((receive ? incoming : output) << 22);
    }
    *history = state;
    return result;
}
void server_scramble(uint16_t d[65536], uint16_t page) /* 8faa */
{
    uint32_t state = ((uint32_t)d[page+0x58] << 16) | d[page+0x59];
    d[page] = shift_bits(&state, d[page], d[page+2], 18, false);
    d[page+0x58] = (uint16_t)(state >> 16);
    d[page+0x59] = (uint16_t)state;
}
void server_descramble(uint16_t d[65536], uint16_t page) /* 8fe1 */
{
    uint32_t state = ((uint32_t)d[page+0x1e] << 16) | d[page+0x1f];
    d[page+0x20] = shift_bits(&state, d[page+0x20], d[page+0x22], 18, true);
    d[page+0x1e] = (uint16_t)(state >> 16);
    d[page+0x1f] = (uint16_t)state;
}

/* e5e7..e60a: TX/RX width setup. Original LST restores two saved ST0
 * contexts; pass their DP bases explicitly (normal TX=0380, RX=0300).
 * Caller guarantees the saved pages and ARP context are valid.
 */
void server_width_setup(uint16_t d[65536], uint16_t tx, uint16_t rx)
{
    bool seven = (d[tx+0x60] & 1u) != 0;
    uint16_t width = seven ? 7 : 8;
    uint16_t mask = seven ? 0x7f : 0xff;
    d[tx+3] = 5;
    d[tx+4] = d[tx+5] = d[tx+0x58] = d[tx+0x59] = 0;
    d[tx+6] = 0x83c9;
    d[tx+1] = mask;
    d[tx+2] = width;
    d[rx+0x22] = width;
    d[rx+0x25] = d[rx+0x24] = d[rx+0x1e] = d[rx+0x1f] = 0;
    d[rx+0x71] = 0;
    d[rx+0x21] = mask;
    d[rx+0x26] = 0x84af;
}

/* e4d1..e4ef: fixed 7e training source with an LSB-first bit reservoir.
 * Valid states have width 7/8, buffered count <16 and reservoir consistent
 * with that count. Output includes upper reservoir bits, as the firmware
 * does; the transmit callback is responsible for masking the word.
 */
void server_training_word(uint16_t d[65536], uint16_t page)
{
    unsigned count = d[page+4];
    uint32_t reservoir = d[page+5];
    unsigned width = d[page+2];
    while (count < width) {
        reservoir |= 0x7eu << count;
        count += 8;
    }
    d[page+4] = (uint16_t)(count - width);
    d[page] = (uint16_t)reservoir;
    d[page+5] = (uint16_t)(reservoir >> width);
}

/* e65f..e67a: TX callback with the payload-source gate at [006f].2 CLOSED.
 * This makes 83c4 return immediately: the caller supplies d[0380] instead
 * of asking the supervisor's source state machine for new payload bits.
 * The following transform/write portion is original callback behavior.
 */
void server_transmit_preloaded(uint16_t d[65536], uint16_t sample_cell)
{
    uint16_t tx = 0x0380;
    d[tx] &= d[tx+1];
    if (d[tx+0x60] & 0x0200u) server_scramble(d, tx);
    if (d[0xffd9] & 0x8000u) d[tx] = server_reverse_octet(d[tx]);
    d[0xff01] = d[tx];
    d[0xff0c] = d[tx+2];
    d[sample_cell] = d[tx];
}

/* e67b..e691: RX callback with [006f].3 CLOSED so 847e does not dispatch
 * into the supervisor's byte-output buffer. Mask/reversal/descrambling are
 * verified here; delivery through the buffer state machine is separate.
 */
void server_receive_preloaded(uint16_t d[65536], uint16_t sample_cell)
{
    uint16_t value = d[sample_cell];
    d[0xff00] = value;
    if (d[0xffd9] & 0x8000u) value = server_reverse_octet(value);
    d[0x0320] = value & d[0x0321];
    if (d[0x03e0] & 0x0200u) server_descramble(d, 0x0300);
}
