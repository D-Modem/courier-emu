// SPDX-License-Identifier: BSD-3-Clause
// Bit-exact counterparts of sip.py's scalar G.711 functions, on PCM16 input.
#pragma once
#include <algorithm>
#include <cstddef>
#include <cstdint>

namespace courier::g711 {
inline uint8_t encode_ulaw(int16_t pcm)
{
    int sample = pcm;
    const unsigned sign = sample < 0 ? 0x80 : 0;
    if (sign) sample = -sample;
    sample = std::min(sample, 32635) + 0x84;
    unsigned exponent = 7, mask = 0x4000;
    while (exponent && !(unsigned(sample) & mask)) { --exponent; mask >>= 1; }
    const unsigned mantissa = (unsigned(sample) >> (exponent + 3)) & 15;
    return uint8_t(~(sign | (exponent << 4) | mantissa));
}

inline uint8_t encode_alaw(int16_t pcm)
{
    // Express the Python negative right shift without relying on C++17's
    // implementation-defined signed shift: -(pcm >> 3)-1 == (-pcm-1)/8.
    const unsigned mask = pcm >= 0 ? 0xd5 : 0x55;
    const unsigned sample = pcm >= 0 ? unsigned(pcm) / 8 : unsigned(-int(pcm) - 1) / 8;
    constexpr unsigned ends[] = {0x1f, 0x3f, 0x7f, 0xff, 0x1ff, 0x3ff, 0x7ff, 0xfff};
    unsigned segment = 0;
    while (segment < 8 && sample > ends[segment]) ++segment;
    if (segment == 8) return uint8_t(0x7f ^ mask);
    const unsigned shift = segment < 2 ? 1 : segment;
    return uint8_t(((segment << 4) | ((sample >> shift) & 15)) ^ mask);
}

inline int16_t decode_ulaw(uint8_t octet)
{
    const unsigned value = unsigned(~octet) & 255;
    const int sample = int((((value & 15) << 3) + 0x84) << ((value & 0x70) >> 4)) - 0x84;
    return int16_t(value & 0x80 ? -sample : sample);
}

inline int16_t decode_alaw(uint8_t octet)
{
    const unsigned value = octet ^ 0x55;
    const unsigned segment = (value & 0x70) >> 4;
    const int sample = segment == 0 ? int((value & 15) << 4) + 8
        : int((((value & 15) << 4) + 0x108) << (segment - 1));
    return int16_t(value & 0x80 ? sample : -sample);
}

inline std::size_t encode(const int16_t *in, std::size_t count, uint8_t *out,
                          std::size_t capacity, unsigned law)
{
    if (law > 1 || count > capacity || (count && (!in || !out))) return 0;
    if (law == 0) for (std::size_t k = 0; k < count; ++k) out[k] = encode_ulaw(in[k]);
    else for (std::size_t k = 0; k < count; ++k) out[k] = encode_alaw(in[k]);
    return count;
}

inline std::size_t decode(const uint8_t *in, std::size_t count, int16_t *out,
                          std::size_t capacity, unsigned law)
{
    if (law > 1 || count > capacity || (count && (!in || !out))) return 0;
    if (law == 0) for (std::size_t k = 0; k < count; ++k) out[k] = decode_ulaw(in[k]);
    else for (std::size_t k = 0; k < count; ++k) out[k] = decode_alaw(in[k]);
    return count;
}
} // namespace courier::g711
