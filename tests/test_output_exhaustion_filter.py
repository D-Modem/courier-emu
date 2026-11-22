import struct

from courier_emu.dsp import LaneHostIo, NativeC5x
from tests.test_output_exhaustion_trace import configure


def test_idle_wrong_caller_and_unrelated_full_status_reads_do_not_consume_trigger():
    # CALL 8010; helper LAMM PA6; RET. The return address is 8002.
    program = [0x7a80, 0x8010] + [0x8b00] * 14 + [0x0856, 0xef00]
    with NativeC5x.from_program(0x8000, struct.pack('<18H', *program)) as dsp:
        model = LaneHostIo()
        try:
            configure(model, dsp)
            model.set_recent()
            model.arm_bank_trace(pc=0x8010, caller=0x8002, address=0x0320, idle_word=0xff00)
            dsp.set_io(0x56, 0x003f)
            dsp.set_data(0x0320, 0xff00)
            dsp.set_pc(0x8000)
            dsp.step(2)
            assert model.bank_trace()['full_status_reads'] == 1
            assert model.bank_trace()['rows'] == []
            dsp.step(1)  # RET consumes the original caller.
            dsp.set_data(0x0320, 0x0042)
            dsp.set_pc(0x8010)  # Same helper, not called by the output path.
            dsp.step(1)
            assert model.bank_trace()['full_status_reads'] == 2
            assert model.bank_trace()['rows'] == []
            dsp.set_pc(0x8000)
            dsp.step(2)
            trace = model.bank_trace()
            assert trace['full_status_reads'] == 3
            i = trace['trigger_index']
            assert trace['rows'][i]['kind'] == 8
            assert trace['rows'][i]['value'] == 0x003f
            assert trace['rows'][i - 1]['kind'] == 11
            assert trace['rows'][i - 1]['port_or_vector'] == 0x0320
            assert trace['rows'][i - 1]['value'] == 0x0042
            assert dsp.data(0x0320) == 0x0042
            assert dsp.io(0x56) == 0x003f
        finally:
            model.close()
