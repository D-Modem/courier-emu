"""Optional bulk G.711 on an already loaded native core; no implicit build.

Return None to decline unsupported inputs/libraries. Callers retain their
scalar codec, including clipping/conversion semantics for non-PCM16 inputs.
"""
from array import array
import ctypes
import os

_binding = None  # Atomically published (library, functions-or-None).


def _functions():
    global _binding
    if os.environ.get('COURIER_NATIVE_G711', '1') == '0':
        return None
    from .dsp import loaded_library
    library = loaded_library()
    if library is None:
        return None
    if _binding is not None and _binding[0] is library:
        return _binding[1]
    try:
        encode = library.courier_g711_encode
        decode = library.courier_g711_decode
    except AttributeError:
        _binding = (library, None)
        return None
    # These tiny packet kernels replace Python work that held the GIL. Keep
    # it held rather than surrendering it to the CPU worker and waiting for
    # another thread's switch interval after a short native codec call.
    prototype = ctypes.PYFUNCTYPE(ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t,
                                 ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint)
    encode = prototype(ctypes.cast(encode, ctypes.c_void_p).value)
    decode = prototype(ctypes.cast(decode, ctypes.c_void_p).value)
    _binding = (library, (encode, decode))
    return _binding[1]


def available():
    """Whether bulk codecs exist on the already loaded core (never build one)."""
    return _functions() is not None


def encode_pcm16(samples, law):
    """Encode ordinary signed-16-bit ints; otherwise decline without mutation."""
    if law not in (0, 1) or not isinstance(samples, (list, tuple)):
        return None
    # Do not let array's __index__ coercion change a custom object's __int__
    # behavior, or consume one-shot iterators before declining to Python.
    if any(type(value) is not int for value in samples):
        return None
    functions = _functions()
    if functions is None:
        return None
    try:
        values = array('h', samples)
    except OverflowError:
        return None
    if not values:
        return b''
    out = array('B', [0]) * len(values)
    count = functions[0](values.buffer_info()[0], len(values), out.buffer_info()[0],
                         len(out), law)
    if count != len(values):
        raise RuntimeError('native G.711 encoding failed')
    return out.tobytes()


def decode_octets(octets, law):
    """Decode a bytes/bytearray block into PCM16, or decline to the scalar path."""
    if law not in (0, 1) or not isinstance(octets, (bytes, bytearray)):
        return None
    if not octets:
        return []
    functions = _functions()
    if functions is None:
        return None
    values = bytes(octets)
    out = array('h', [0]) * len(values)
    # c_char_p retains the immutable bytes for the whole native call, including
    # embedded NULs; the explicit count, not a terminator, bounds the input.
    source = ctypes.c_char_p(values)
    count = functions[1](source, len(values), out.buffer_info()[0], len(out), law)
    if count != len(values):
        raise RuntimeError('native G.711 decoding failed')
    return out.tolist()
