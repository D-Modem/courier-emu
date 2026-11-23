"""Optional stateless FIR block kernels on an already loaded core library.

Results are transactional: None declines to the Python loop without committing
stream state. Scratch chunks bound allocation, not audio or output retention.
"""
from array import array
import ctypes as c
import math
import os

_binding = None


def _function(kind):
    if (os.environ.get('COURIER_NATIVE_RESAMPLE', '1') == '0' or
            os.environ.get('COURIER_NATIVE_' + ('FIXED_RESAMPLE' if kind == 'fixed' else 'POLYPHASE'), '1') == '0'):
        return None
    from .dsp import loaded_library
    library = loaded_library()
    if library is None:
        return None
    global _binding
    if _binding is None or _binding[0] is not library:
        functions = {}
        signatures = {
            'fixed': [c.c_void_p, c.c_size_t, c.c_void_p, c.c_size_t,
                      c.c_double, c.c_double, c.c_void_p, c.c_size_t,
                      c.c_void_p, c.c_void_p, c.c_uint],
            'polyphase': [c.c_void_p, c.c_size_t, c.c_void_p, c.c_size_t,
                          c.c_uint64, c.c_uint64, c.c_uint64, c.c_int64,
                          c.c_int64, c.c_int64, c.c_void_p, c.c_size_t,
                          c.c_void_p, c.c_void_p],
        }
        for name, signature in signatures.items():
            function = getattr(library, 'courier_resample_' + name, None)
            if function is not None:
                # Packet-sized kernels must not surrender the GIL to a busy
                # emulator thread and then wait a switch interval to return.
                function = c.PYFUNCTYPE(c.c_size_t, *signature)(
                    c.cast(function, c.c_void_p).value)
                function._library_owner = library
            functions[name] = function
        _binding = (library, functions)
    return _binding[1][kind]


def fixed_available():
    return _function('fixed') is not None


def polyphase_available():
    return _function('polyphase') is not None


def _collect(function, args, cursor, capacity):
    out = array('h', [0]) * capacity
    status = c.c_int()
    result = []
    while True:
        before = cursor.value
        count = function(*args(before), out.buffer_info()[0], capacity,
                         c.byref(cursor), c.byref(status))
        if status.value == 1:
            return None
        if status.value not in (0, 2) or count > capacity:
            raise RuntimeError('invalid native resampler result')
        result.extend(out[:count].tolist())
        if status.value == 0:
            return result, cursor.value
        if count == 0:
            raise RuntimeError('native resampler made no progress')
        if cursor.value == before:
            # A positive but sub-ulp step must retain the reference behavior.
            return None


def fixed(history, kernel, step, position, mode):
    function = _function('fixed')
    if (function is None or type(step) is not float or type(position) is not float
            or not (math.isfinite(step) and step > 0 and
                                math.isfinite(position) and 0 <= position <= 2**52)):
        return None
    values = array('d', history)
    estimate = (len(values) - 128 - position) / step
    if not math.isfinite(estimate):
        return None
    capacity = min(1024, max(1, math.ceil(estimate) + 2))
    cursor = c.c_double(position)
    # The mode is the last C argument; adapt the shared chunk collector.
    def invoke(*args):
        return function(*args, mode)
    return _collect(invoke, lambda pos: (values.buffer_info()[0], len(values),
                    kernel.buffer_info()[0], len(kernel), step, pos), cursor, capacity)


def polyphase(history, kernel, up, down, taps, half, origin, output):
    function = _function('polyphase')
    if (function is None or any(type(v) is not int for v in
            (up, down, taps, half, origin, output))
            or not (0 < up <= 1024 and 0 < down <= 2**20 and
            0 < taps <= 4096 and 0 <= half <= taps and abs(origin) <= 2**52 and
            0 <= output <= 2**52 // down)):
        return None
    values = array('d', history)
    newest = origin + len(values) - 1
    last = ((newest - half + 1) * up - 1) // down
    capacity = min(1024, max(1, last - output + 1))
    return _collect(function, lambda index: (values.buffer_info()[0], len(values),
                    kernel.buffer_info()[0], len(kernel), up, down, taps, half,
                    origin, index), c.c_int64(output), capacity)
