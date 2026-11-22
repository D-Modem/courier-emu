"""The x86 FMA specialization must preserve the compensated dot product."""
import ctypes
import math
from pathlib import Path
import random
import shutil
import struct
import subprocess
import sys

import pytest


@pytest.fixture(scope='module')
def dots(tmp_path_factory):
    compiler = shutil.which('c++')
    if compiler is None:
        pytest.skip('C++ compiler unavailable')
    directory = tmp_path_factory.mktemp('resample-dot')
    source = directory / 'dot.cpp'
    source.write_text(r'''
#include "resample.hpp"
using namespace courier::resample;
extern "C" double portable(const double *a, const double *b, long n) {
    return sumprod_portable(a, b, n);
}
extern "C" double dispatched(const double *a, const double *b, long n) {
    return sumprod(a, b, n);
}
extern "C" int has_fma() {
#if (defined(__x86_64__) || defined(__i386__)) && (defined(__GNUC__) || defined(__clang__))
    return bool(__builtin_cpu_supports("fma"));
#else
    return 0;
#endif
}
extern "C" double accelerated(const double *a, const double *b, long n) {
#if (defined(__x86_64__) || defined(__i386__)) && (defined(__GNUC__) || defined(__clang__))
    return sumprod_fma(a, b, n);
#else
    return sumprod_portable(a, b, n);
#endif
}
''')
    library = directory / ('dot.dylib' if sys.platform == 'darwin' else 'dot.so')
    subprocess.run([compiler, '-std=c++17', '-O3',
                    *(['-dynamiclib'] if sys.platform == 'darwin' else ['-shared', '-fPIC']),
                    '-I', str(Path(__file__).resolve().parents[1] / 'native'),
                    str(source), '-o', str(library)], check=True, capture_output=True)
    lib = ctypes.CDLL(str(library))
    for name in ('portable', 'dispatched', 'accelerated'):
        function = getattr(lib, name)
        function.argtypes = [ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
                             ctypes.c_long]
        function.restype = ctypes.c_double
    return lib


def bits(value):
    return struct.pack('d', value)


def check(dots, a, b):
    av = (ctypes.c_double * len(a))(*a)
    bv = (ctypes.c_double * len(b))(*b)
    reference = dots.portable(av, bv, len(a))
    assert bits(dots.dispatched(av, bv, len(a))) == bits(reference)
    if dots.has_fma():
        assert bits(dots.accelerated(av, bv, len(a))) == bits(reference)
    if hasattr(math, 'sumprod'):
        assert bits(reference) == bits(math.sumprod(a, b))


@pytest.mark.parametrize('count', [0, 1, 2, 3, 7, 63, 127, 128, 129, 257])
def test_pcm_kernels_and_cancellation_are_bit_exact(dots, count):
    rng = random.Random(186 + count)
    for _ in range(30):
        a = [rng.uniform(-1, 1) for _ in range(count)]
        b = [float(rng.randrange(-32768, 32768)) for _ in range(count)]
        check(dots, a, b)
    check(dots, [0.0] * count, [-0.0] * count)
    check(dots, [1.0] * count, [(-1.0)**k * 32767 for k in range(count)])


def test_compensation_not_replaced_with_a_plain_dot_product(dots):
    check(dots, [1.0, 1.0, 1.0], [1e16, 1.0, -1e16])
    check(dots, [math.nextafter(1.0, 2.0), -1.0],
          [math.nextafter(1.0, 0.0), 1.0])
    rng = random.Random(403)
    for _ in range(200):
        a = [math.ldexp(rng.uniform(-1, 1), rng.randint(-100, 100)) for _ in range(128)]
        b = [math.ldexp(rng.uniform(-1, 1), rng.randint(-100, 100)) for _ in range(128)]
        check(dots, a, b)
