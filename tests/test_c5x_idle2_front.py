"""IDLE2 must participate in the fast front test, independently of IDLE."""
import struct
import pytest
from courier_emu.dsp import NativeC5x


@pytest.mark.parametrize('threaded',[False,True])
def test_idle2_stops_fetch_and_masked_peripheral_edge_wakes_it(threaded):
    code=struct.pack('<4H',0xbe23,0xb9ab,0x7980,2)  # IDLE2; LACL #ab; B 2
    with NativeC5x.from_program(0,code) as core:
        if threaded:core.step_cycles(64)
        else:core.step(64)
        asleep=core.state()
        assert asleep['idle']
        assert asleep['pc']==1
        assert asleep['acc']==0
        # Reset leaves INTM set and IMR zero. IDLE2 wakes on the latched
        # peripheral edge anyway; masking prevents vectoring, not waking.
        core.interrupt(3)
        if threaded:core.step_cycles(64)
        else:core.step(16)
        awake=core.state()
        assert not awake['idle']
        assert awake['acc']==0xab
        assert awake['pc'] in (2,3)
