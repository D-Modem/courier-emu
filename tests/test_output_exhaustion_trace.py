"""The first-full-bank observer must never become a flow-control mechanism."""
import struct

from courier_emu.dsp import LaneHostIo, NativeC5x
from tests.test_board_service_trace import access


def configure(model, dsp):
    model.configure(dsp.handle, True, command_port=0x18, ack_port=0x1a,
                    lane_first=0x40, banks=6, dsp_first=0x58, dsp_status=0x56)


def test_combined_trace_freezes_at_first_full_read_and_keeps_cpu_status_and_ack():
    # LAMM PA6 twice; inspection via io() alone is not a DSP bus read.
    with NativeC5x.from_program(0x8000, struct.pack('<2H', 0x0856, 0x0856)) as dsp:
        model = LaneHostIo()
        try:
            configure(model, dsp)
            model.set_recent()
            model.arm_bank_trace()
            dsp.set_io(0x56, 0x003f)
            assert dsp.io(0x56) == 0x003f
            assert model.bank_trace()['rows'] == []
            model.record_irq(10, 6, 12, 0, 0x93a34, 0x202)
            dsp.set_pc(0x8000)
            dsp.step(1)
            at_trigger = dsp.state()
            report = model.bank_trace()
            assert report['full_status_reads'] == 1
            assert report['post_events_remaining'] == 256
            assert [r['kind'] for r in report['rows']] == [6, 8]
            trigger = report['rows'][-1]
            assert trigger['cpu_instructions'] == 0  # Unknown, not interpolated.
            assert trigger['pc'] == 0x8000
            assert trigger['port_or_vector'] == 0x56
            assert trigger['value'] == 0x003f
            assert access(model, 1, 0x1a, now=20)
            assert access(model, 2, 0x1a, value=1, now=21)
            assert dsp.state() == at_trigger
            assert dsp.io(0x56) == 0x013f  # Only the real host ACK frees a slot.
            report = model.bank_trace()
            assert [r['kind'] for r in report['rows']] == [6, 8, 10, 2]
            assert report['rows'][-2]['value'] == 0xff
            assert report['rows'][-1]['value'] == 1
            assert model.bank_trace() == report  # Inspection never drains.
            assert [r['kind'] for r in model.recent_events()] == [6, 2]
            dsp.step(1)
            assert model.bank_trace()['full_status_reads'] == 1
            assert model.bank_trace()['rows'][-1]['value'] == 0x013f
        finally:
            model.close()


def test_trace_is_opt_in_and_arms_only_at_the_requested_boundary():
    with NativeC5x.from_program(0x8000, struct.pack('<4H', *([0x0856] * 4))) as dsp:
        model = LaneHostIo()
        try:
            configure(model, dsp)
            dsp.set_io(0x56, 0)
            model.arm_bank_trace()  # Cannot implicitly enable diagnostics.
            dsp.set_pc(0x8000)
            dsp.step(1)
            assert model.bank_trace() == {'armed': False, 'full_status_reads': 0,
                                          'post_events_remaining': 0, 'epoch': 0,
                                          'trigger_index': None, 'rows': []}
            model.set_recent()
            dsp.step(1)  # Pre-CONNECT reads must not consume the trigger.
            assert model.bank_trace()['rows'] == []
            model.arm_bank_trace()
            dsp.step(1)
            assert model.bank_trace()['rows'][0]['pc'] == 0x8002
            model.set_recent(False)
            dsp.step(1)
            assert not model.bank_trace()['armed']
        finally:
            model.close()


def test_bounded_pre_and_post_context_do_not_replace_the_first_trigger():
    with NativeC5x.from_program(0x8000, struct.pack('<2H', 0x0856, 0x0856)) as dsp:
        model = LaneHostIo()
        try:
            configure(model, dsp)
            model.set_recent()
            model.arm_bank_trace()
            dsp.set_io(0x56, 0)
            for i in range(3000):
                model.record_irq(i, 6, 12, 0, 0x93a34, 0x202)
            dsp.set_pc(0x8000)
            dsp.step(1)
            report = model.bank_trace()
            assert len(report['rows']) == 2048
            assert report['rows'][0]['cpu_instructions'] == 953
            for i in range(4000):
                model.record_irq(3000 + i, 7, 12, 0x8000, 0x80000, 0x202)
            frozen = model.bank_trace()
            assert len(frozen['rows']) == 2304
            assert frozen['post_events_remaining'] == 0
            dsp.step(1)
            assert model.bank_trace()['rows'] == frozen['rows']
            assert model.bank_trace()['full_status_reads'] == 2
            model.arm_bank_trace()
            assert model.bank_trace()['rows'] == []
            assert model.bank_trace()['full_status_reads'] == 0
        finally:
            model.close()


def test_observation_does_not_change_dsp_execution_or_bus_history():
    results = []
    # LAMM PA6; LACL #42; SAMM PA8; LAMM PA6.
    for enabled in (False, True):
        with NativeC5x.from_program(0x8000, struct.pack('<4H', 0x0856, 0xb942, 0x8858, 0x0856)) as dsp:
            model = LaneHostIo()
            try:
                configure(model, dsp)
                if enabled:
                    model.set_recent()
                    model.arm_bank_trace()
                dsp.set_io(0x56, 0)
                dsp.set_pc(0x8000)
                dsp.step(4)
                results.append((dsp.state(), dsp.io_events(), dsp.io(0x56), dsp.io_output(0x58)))
            finally:
                model.close()
    assert results[0] == results[1]


def test_trace_lifetime_does_not_require_processors_to_outlive_each_other():
    dsp = NativeC5x.from_program(0x8000, struct.pack('<2H', 0x0856, 0x0856))
    model = LaneHostIo()
    configure(model, dsp)
    model.set_recent()
    model.arm_bank_trace()
    model.close()
    dsp.set_pc(0x8000)
    dsp.step(1)  # Shared diagnostic state is disabled, never a dangling pointer.
    dsp.close()


def test_new_core_starts_a_fresh_capture_instead_of_mixing_instruction_epochs():
    model = LaneHostIo()
    try:
        model.set_recent()
        model.arm_bank_trace()
        for _ in range(2):
            with NativeC5x.from_program(0x8000, struct.pack('<H', 0x0856)) as dsp:
                # Explicitly withdraw the old core before freeing it, as a rebuild does.
                configure(model, dsp)
                assert model.bank_trace()['rows'] == []
                dsp.set_io(0x56, 0)
                dsp.set_pc(0x8000)
                dsp.step(1)
                assert len(model.bank_trace()['rows']) == 1
                model.configure(None, False, command_port=0x18, ack_port=0x1a,
                                lane_first=0x40, banks=6, dsp_first=0x58, dsp_status=0x56)
    finally:
        model.close()
