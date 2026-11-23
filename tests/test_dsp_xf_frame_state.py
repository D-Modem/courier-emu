"""Combined frame observations preserve epochs without advancing the DSP."""
import ctypes
import struct

from courier_emu.dsp import NativeC5x


def test_snapshot_matches_getters_across_edges_and_resets():
    with NativeC5x.from_program(0x6000, struct.pack('<3H', 0xbe4c, 0xbe4d, 0xbe22)) as core:
        assert core._xf_frame_state_function is not None
        buffer = core._xf_frame_state_values
        for reset in (False, False, True, False):
            if reset:
                core.reset()
            core.set_pc(0x6000)
            core.step(2)
            before = core.state()
            expected = core.xf_falling_edges(), core.reset_generation()
            assert core.xf_frame_state() == expected
            assert core.xf_frame_state() == expected  # Read, not consume.
            assert core.state() == before
            assert core._xf_frame_state_values is buffer


def test_snapshot_falls_back_for_older_prebuilt_library():
    with NativeC5x.from_program(0, struct.pack('<H', 0x5500)) as core:
        core._xf_frame_state_function = None
        assert core.xf_frame_state() == (core.xf_falling_edges(), core.reset_generation())


def test_native_snapshot_handles_null_core_and_output():
    with NativeC5x.from_program(0, struct.pack('<H', 0x5500)) as core:
        function = core._xf_frame_state_function
        values = (ctypes.c_uint64 * 2)(123, 456)
        function(None, values)
        assert tuple(values) == (0, 0)
        function(core.handle, None)
