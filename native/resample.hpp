// The part of resample.BandLimitedResampler._convert_retuned that is the same
// for every output sample: pick the window around the output instant, take the
// kernel phase nearest it and dot the two. Done the way the Python is, so the
// answers are the same bit for bit - including the dot product, which is
// CPython's math.sumprod for floats (a triple-length accumulation), not a
// plain loop.
#pragma once
#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <vector>

namespace courier {
namespace resample {

constexpr long HALF_TAPS = 64, TAPS = 2 * HALF_TAPS, PHASES = 1024;

struct DoubleLength { double hi, lo; };
inline DoubleLength dl_sum(double a, double b)
{
    const double x = a + b, z = x - a;
    return {x, (a - (x - z)) + (b - z)};
}
inline DoubleLength dl_mul(double x, double y)
{
    const double z = x * y;
    return {z, std::fma(x, y, -z)};
}
struct TripleLength { double hi, lo, tiny; };
inline TripleLength tl_fma(double x, double y, TripleLength total)
{
    const DoubleLength product = dl_mul(x, y);
    const DoubleLength sum = dl_sum(total.hi, product.hi);
    const DoubleLength r1 = dl_sum(total.lo, product.lo);
    const DoubleLength r2 = dl_sum(r1.hi, sum.lo);
    return {sum.hi, r2.hi, total.tiny + r1.lo + r2.lo};
}
inline double tl_to_d(TripleLength total)
{
    const DoubleLength last = dl_sum(total.lo, total.hi);
    return total.tiny + last.lo + last.hi;
}

// math.sumprod(a, b) for `count` floats.
inline double sumprod_portable(const double *a, const double *b, long count)
{
    TripleLength total{0.0, 0.0, 0.0};
    for (long index = 0; index < count; ++index) total = tl_fma(a[index], b[index], total);
    return tl_to_d(total);
}

#if (defined(__x86_64__) || defined(__i386__)) && (defined(__GNUC__) || defined(__clang__))
// The portable x86-64 ABI does not include FMA. Without a targeted version,
// every tap's explicit std::fma is a libm call, even on CPUs with hardware
// FMA. Specialize only this exact compensated dot product: -march=native or
// fast-math for the whole library could change the audio's rounding elsewhere.
__attribute__((target("fma"))) inline double sumprod_fma(
    const double *a, const double *b, long count)
{
    TripleLength total{0.0, 0.0, 0.0};
    for (long index = 0; index < count; ++index) total = tl_fma(a[index], b[index], total);
    return tl_to_d(total);
}
#endif

inline double sumprod(const double *a, const double *b, long count)
{
#if (defined(__x86_64__) || defined(__i386__)) && (defined(__GNUC__) || defined(__clang__))
    // Select once, not once per tap. The fallback remains safe on older CPUs.
    static const auto dot = __builtin_cpu_supports("fma") ? sumprod_fma : sumprod_portable;
    return dot(a, b, count);
#else
    return sumprod_portable(a, b, count);
#endif
}

// Match separate Python multiply/add operations, including on FMA targets.
inline double sumprod_sequential(const double *a, const double *b, long count)
{
    double total = 0.0;
    for (long k = 0; k < count; ++k) {
        volatile double product = a[k] * b[k];
        total += product;
    }
    return total;
}

inline int16_t pcm16_even(double value)
{
    if (value >= 32767.0) return 32767;
    if (value <= -32768.0) return -32768;
    double rounded = std::floor(value);
    const double fraction = value - rounded;
    if (fraction > 0.5 || (fraction == 0.5 && std::fmod(rounded, 2.0) != 0.0))
        rounded += 1.0;
    return static_cast<int16_t>(rounded);
}

// Stateless block kernels. Status 0: complete, 1: decline to Python, 2: output
// scratch full (resume at the returned position). No stream state is committed.
inline std::size_t fixed(const double *history, std::size_t length,
    const double *kernel, std::size_t kernel_length, double step, double position,
    int16_t *out, std::size_t capacity, double *position_out, int *status, unsigned mode)
{
    if (!status) return 0;
    *status = 1;
    constexpr double limit_exact = 4503599627370496.0;
    if (!history || !kernel || !position_out || (!out && capacity)
        || length < TAPS || uint64_t(length) > UINT64_C(4503599627370496)
        || kernel_length != PHASES * TAPS || mode > 1
        || !std::isfinite(position) || position < 0 || position > limit_exact
        || !std::isfinite(step) || step <= 0) return 0;
    const double limit = double(length - TAPS);
    std::size_t written = 0;
    *status = 0;
    while (position <= limit) {
        auto base = static_cast<std::size_t>(position);
        auto phase = static_cast<long>((position - double(base)) * PHASES + 0.5);
        if (phase == PHASES) {
            ++base; phase = 0;
            if (double(base) > limit) break;
        }
        if (written == capacity) { *status = 2; break; }
        const double *taps = kernel + phase * TAPS;
        const double value = mode ? sumprod(taps, history + base, TAPS)
                                  : sumprod_sequential(taps, history + base, TAPS);
        if (!std::isfinite(value)) { *status = 1; return 0; }
        out[written++] = pcm16_even(value);
        position += step;
    }
    *position_out = position;
    return written;
}

inline std::size_t polyphase(const double *history, std::size_t length,
    const double *kernel, std::size_t kernel_length, uint64_t up, uint64_t down,
    uint64_t taps, int64_t half, int64_t origin, int64_t output,
    int16_t *out, std::size_t capacity, int64_t *output_out, int *status)
{
    if (!status) return 0;
    *status = 1;
    constexpr int64_t limit = INT64_C(4503599627370496);
    if ((!history && length) || !kernel || !output_out || (!out && capacity)
        || !up || up > 1024 || !down || down > (1u << 20)
        || !taps || taps > 4096 || half < 0 || uint64_t(half) > taps
        || kernel_length != up * taps || uint64_t(length) > uint64_t(limit)
        || origin < -limit || origin > limit || output < 0
        || output > limit / int64_t(down)) return 0;
    const int64_t newest = origin + int64_t(length) - 1;
    std::size_t written = 0;
    *status = 0;
    while (true) {
        if (output > limit / int64_t(down)) { *status = 1; return 0; }
        const int64_t position = output * int64_t(down);
        const int64_t base = position / int64_t(up);
        if (base + half > newest) break;
        if (written == capacity) { *status = 2; break; }
        const double *row = kernel + (position % int64_t(up)) * int64_t(taps);
        double total = 0.0;
        for (uint64_t k = 0; k < taps; ++k) {
            const int64_t sample = base + half - int64_t(k) - origin;
            if (sample >= 0 && uint64_t(sample) < length) {
                volatile double product = row[k] * history[sample];
                total += product;
            }
        }
        if (!std::isfinite(total)) { *status = 1; return 0; }
        out[written++] = pcm16_even(total);
        ++output;
    }
    *output_out = output;
    return written;
}

constexpr double KAISER_BETA = 8.0;

// resample._bessel_i0, operation for operation. The square is libm's pow, as
// CPython's float ** int is, not a multiplication the compiler may choose.
inline double bessel_i0(double x)
{
    volatile double two = 2.0;
    double total = 1.0, term = 1.0;
    long k = 1;
    while (term > 1e-12 * total) {
        term *= std::pow(x / double(2 * k), two);
        total += term;
        ++k;
    }
    return total;
}

// resample._windows(), operation for operation. Build the immutable Kaiser
// table outside Python's 131,072-tap loop; do not change its coefficients.
inline void windows(double *out, double norm)
{
#pragma clang fp contract(off)
    static_assert((PHASES & (PHASES - 1)) == 0);
    static_assert((HALF_TAPS & (HALF_TAPS - 1)) == 0);
    for (long phase = 0; phase <= PHASES / 2; ++phase) {
        const double fraction = double(phase) / PHASES;
        for (long k = 0; k < TAPS; ++k) {
            const double t = double(k - (HALF_TAPS - 1)) - fraction;
            const double ratio = t / HALF_TAPS;
            const double value = std::abs(ratio) < 1
                ? bessel_i0(KAISER_BETA * std::sqrt(1 - ratio * ratio)) / norm : 0.0;
            out[phase * TAPS + k] = value;
            // The paired row has exactly -t at the reversed tap. Both t
            // and ratio are exact binary fractions on this power-of-two
            // grid, so the squared argument (and every output bit) agrees.
            // Phase zero has no PHASES row; compute it independently.
            if (phase != 0)
                out[(PHASES - phase) * TAPS + (TAPS - 1 - k)] = value;
        }
    }
}

// The sample whose window crosses a clock edge: Kaiser-windowed sinc weights
// at the samples' own times (resample.py's else branch).
inline double nonuniform(const double *history, const double *times,
    std::size_t times_length, double instant, double support, double cutoff,
    double norm)
{
    const double pi = 3.141592653589793;
    const long first = std::max(1L, long(std::lower_bound(times, times + times_length,
        instant - support) - times));
    const long last = std::min(long(times_length) - 1, long(std::upper_bound(
        times, times + times_length, instant + support) - times));
    double value = 0.0, total = 0.0;
    for (long k = first; k < last; ++k) {
        const double delta = times[k] - instant;
        const double x = 2 * cutoff * delta;
        const double sinc = x == 0 ? 1.0 : std::sin(pi * x) / (pi * x);
        const double ratio = delta / support;
        const double window = bessel_i0(KAISER_BETA
            * std::sqrt(std::max(0.0, 1 - ratio * ratio))) / norm;
        const double width = (times[k + 1] - times[k - 1]) / 2;
        const double weight = 2 * cutoff * sinc * window * width;
        value += history[k] * weight;
        total += weight;
    }
    return total != 0.0 ? value / total : 0.0;
}

// Returns the samples written. *status: 0 the input is used up, 2 `out` is full.
inline std::size_t retuned(const double *history, std::size_t history_length,
    const double *times, std::size_t times_length, const double *kernel,
    double input_rate, double output_rate, double instant, double support,
    double cutoff, double norm,
    int16_t *out, std::size_t capacity, double *instant_out, int *status)
{
    std::size_t written = 0;
    *status = 0;
    const double last = times[times_length - 1];
    while (instant + support <= last + 1e-12) {
        if (written == capacity) { *status = 2; break; }
        const long center = long(std::upper_bound(times, times + times_length, instant) - times) - 1;
        long base = center - (HALF_TAPS - 1);
        const long end = base + TAPS;
        double value;
        if (base >= 0 && end <= long(times_length)
            && std::fabs(times[end - 1] - times[base] - double(TAPS - 1) / input_rate) < 1e-10) {
            long phase = long(std::nearbyint((instant - times[center]) * input_rate * double(PHASES)));
            if (phase == PHASES) { base += 1; phase = 0; }
            (void)history_length;
            value = sumprod(kernel + phase * TAPS, history + base, TAPS);
        } else {
            value = nonuniform(history, times, times_length, instant, support, cutoff, norm);
        }
        double rounded = std::nearbyint(value);
        rounded = std::max(-32768.0, std::min(32767.0, rounded));
        out[written++] = int16_t(rounded);
        instant += 1 / output_rate;
    }
    *instant_out = instant;
    return written;
}

// BandLimitedResampler's state once it has retuned (_timed_samples,
// _timed_times and the scalars beside them), and _convert_retuned on it. A
// conversion can be taken back (rollback) before it is committed, which is
// what lets the worker's native line service find out whether a line frame
// falls due before it changes anything.
struct Timed {
    std::vector<double> history, times;
    double input_time = 0, next_time = 0, input_rate = 0, output_rate = 0, norm = 0;
    uint64_t converted = 0;
    const double *kernel = nullptr;    // the flat kernel for the rates, owned by Python
    std::vector<int16_t> out;          // the last conversion's samples
    std::size_t mark_history = 0, mark_times = 0;
    double mark_input_time = 0, mark_next_time = 0, mark_input = 0, mark_output = 0;
    const double *mark_kernel = nullptr;

    // _convert_retuned up to (not including) its trim.
    void run(const int16_t *samples, std::size_t count, double input, double output,
             const double *flat_kernel)
    {
#pragma clang fp contract(off)
        mark_history = history.size();
        mark_times = times.size();
        mark_input_time = input_time;
        mark_next_time = next_time;
        mark_input = input_rate;
        mark_output = output_rate;
        mark_kernel = kernel;
        for (std::size_t k = 0; k < count; ++k) history.push_back(double(samples[k]));
        for (std::size_t k = 0; k < count; ++k) times.push_back(input_time + double(k) / input);
        input_time += double(count) / input;
        input_rate = input;
        output_rate = output;
        kernel = flat_kernel;
        out.clear();
        double instant = next_time;
        const double support = double(HALF_TAPS) / input;
        const double cutoff = 0.98 * std::min(input, output) / 2;
        int16_t buffer[1024];
        while (instant + support <= times.back() + 1e-12) {
            double moved = instant;
            int status = 0;
            const std::size_t written = retuned(history.data(), history.size(),
                times.data(), times.size(), kernel, input, output, instant, support,
                cutoff, norm, buffer, 1024, &moved, &status);
            out.insert(out.end(), buffer, buffer + written);
            instant = moved;
        }
        next_time = instant;
    }

    void rollback()
    {
        history.resize(mark_history);
        times.resize(mark_times);
        input_time = mark_input_time;
        next_time = mark_next_time;
        input_rate = mark_input;
        output_rate = mark_output;
        kernel = mark_kernel;
        out.clear();
    }

    // The rest of _convert_retuned: keep enough past input for a retune.
    void commit()
    {
#pragma clang fp contract(off)
        const double horizon = next_time - double(2 * TAPS) / std::min(input_rate, output_rate);
        const long found = long(std::lower_bound(times.begin(), times.end(), horizon) - times.begin());
        const long keep = std::max(0L, found - 1);
        history.erase(history.begin(), history.begin() + keep);
        times.erase(times.begin(), times.begin() + keep);
        converted += out.size();
    }
};

} // namespace resample
} // namespace courier
