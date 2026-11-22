from tools.probe_imodem_analog_pair import PROTOCOL_S58, analog_terminal_text, carrier_connected
from tools.probe_imodem_analog_pair import OverlayAudit, connection_rate_bps, traffic_stall_snapshot
from courier_emu.dsp import NativeC5x
from courier_emu.imodem_dsp import ImodemDsp
from courier_emu.isdn import IsdnMachine
from types import SimpleNamespace
import pytest
import struct


def test_analog_transmit_level_uses_at_without_rewriting_the_captured_profile():
    from tools.probe_imodem_analog_pair import analog_tx_settings, parser
    assert parser().parse_args([]).analog_tx_level == 'stored'
    assert analog_tx_settings('S27=1', 'stored') == 'S27=1'
    assert analog_tx_settings('S27=1', '8') == 'S39=8S27=1'
    assert analog_tx_settings('S39=9', '8') == 'S39=8S39=9'  # Later user setting wins.
    for level in ('0', '30', '-1', 'invalid'):
        with pytest.raises(SystemExit):
            parser().parse_args(['--analog-tx-level', level])
        with pytest.raises(ValueError):
            analog_tx_settings('', level)


def test_pcm_protocol_selection_disables_the_other_protocol_on_both_sides():
    assert PROTOCOL_S58["x2"] == 32
    assert PROTOCOL_S58["v90"] == 1
    assert PROTOCOL_S58["v34"] == 33
    assert PROTOCOL_S58["default"] is None


def test_carrier_detection_accepts_verbose_speed_result_but_not_isdn_events():
    assert carrier_connected("\r\nCONNECT 14400/ARQ\r\n")
    assert carrier_connected("\r\nCONNECT\r\n")
    assert carrier_connected("\r\nCONNECT 44000/ARQ/x2/LAPM\r\n", complete=True)
    assert not carrier_connected("BCH_ENABLED Detected\r\n")
    assert not carrier_connected("CONNECT call reference 1")
    assert not carrier_connected("\r\nNO CARRIER\r\n")


def test_payload_waits_for_connect_result_terminating_lf():
    assert not carrier_connected("\r\nCONNECT", complete=True)
    assert not carrier_connected("\r\nCONNECT\r", complete=True)
    assert carrier_connected("\r\nCONNECT\r\n", complete=True)
    assert carrier_connected("\r\nCONNECT 300\r\n", complete=True)


def test_rate_requires_a_complete_native_result_on_that_terminal():
    assert connection_rate_bps("\r\nCONNECT 37333/ARQ/x2/LAPM\r\n") == 37333
    assert connection_rate_bps("\r\nCONNECT 33333/ARQ/x2/LAPM\r\n") == 33333
    assert connection_rate_bps("\r\nCONNECT/ARQ\r\n") is None
    assert connection_rate_bps("\r\nCONNECT 44000") is None
    assert connection_rate_bps("payload CONNECT 64000\r\n") is None


@pytest.mark.parametrize('with_core', [False, True])
def test_first_stall_snapshot_preserves_partial_records_without_advancing_traffic(with_core):
    from tools.analog_traffic import AnalogTraffic
    from tools.imodem_traffic import record

    traffic = AnalogTraffic(20, 32)
    core = SimpleNamespace(state=lambda: {'pc': 0x1234}, stack=lambda: [1, 2],
                           io_port_stats=lambda ports: {'ports': list(ports)},
                           io=lambda port: port) if with_core else None
    current = SimpleNamespace(instructions=123, timer_ticks=45,
                              channels={'sio': SimpleNamespace(status=lambda: {'overruns': 0})},
                              mailbox=SimpleNamespace(core=core))
    for side in traffic.streams:
        traffic.receive(side, '\r\nCONNECT 53333\r\n', 10)
    traffic.next_record('imodem', 10)
    traffic.receive('analog', record('A', 0, 32)[:12], 11)
    traffic.progress.append({'frame': 11, 'timer_ticks': 40})
    traffic.update(60)
    assert traffic_stall_snapshot(traffic, 60, current, {}, {}) is None
    traffic.update(61)
    before = traffic.status(61)
    evidence = traffic_stall_snapshot(traffic, 61, current, {'native': {}}, {'active': True})
    assert evidence['frame'] == 61
    assert evidence['timer_ticks'] == 45
    assert evidence['traffic']['first_stall_frames'] == {'analog': 61, 'imodem': 61}
    assert evidence['traffic']['drain']['analog']['pending_bytes'] == 12
    assert evidence['preceding_progress'] == [{'frame': 11, 'timer_ticks': 40}]
    assert evidence['dsp'] == ({'pc': 0x1234} if with_core else None)
    assert evidence['serial']['sio']['overruns'] == 0
    assert traffic.status(61) == before
    assert not traffic.windows  # Evidence is not a completed or passing gate.
    assert not traffic.done(61)


def test_normal_mode_payload_is_decoded_as_the_terminal_7e1_frame():
    wire = bytes.fromhex("c94dcf44c54d2d36b7b83930")
    assert all(byte.bit_count() % 2 == 0 for byte in wire)
    assert analog_terminal_text({"serial_hex": wire.hex()}) == "IMODEM-67890"


@pytest.mark.parametrize('supervisor_turn', [False, True])
def test_fed_ahead_wallclock_pair_uses_native_advance_without_frame_callbacks(supervisor_turn):
    calls = []
    native = SimpleNamespace(
        live=True, wallclock=True,
        set_wall_target=lambda target: calls.append(('target', target)),
        advance_serve=lambda instructions, quantum, *, supervisor_turn: calls.append(
            ('advance', instructions, quantum, supervisor_turn)))
    mailbox = SimpleNamespace(
        _nb=object(), pcm_frame_service=object(), realtime_target=lambda: 123456)
    machine = SimpleNamespace(
        with_dsp=True, _ledger=SimpleNamespace(needs_service=False),
        _live_bearer=lambda: True, _native_io=native, mailbox=mailbox,
        bri=SimpleNamespace(media_peer=SimpleNamespace(feeds_ahead=True)),
        instructions=999)
    IsdnMachine._advance_dsp(machine, 100, supervisor_turn=supervisor_turn)
    assert mailbox.pcm_frame_service is None
    assert calls == [('target', 123456), ('advance', 999, 100, supervisor_turn)]


@pytest.mark.parametrize('corrupt', [False, True])
def test_overlay_audit_detects_program_corruption_without_repairing_it(corrupt):
    endpoint = ImodemDsp()
    endpoint.core = NativeC5x.from_program(0xa000, struct.pack('<4H', 11, 22, 33, 44))
    endpoint.reset_status = False
    try:
        audit = OverlayAudit(endpoint)
        endpoint.core.set_data(0x0bff, 0xa000)
        for port, value in zip((0x40, 0x44, 0x48, 0x4c), (11, 22, 33, 44)):
            endpoint.write(port, value)
            endpoint.write(port + 2, 0)
        audit.write(0x1e, 1)
        audit.write(0x1e, 2)
        # Simulate the loader's acknowledged pointer and a subsequent bad write.
        endpoint.core.set_io(0x57, 2)
        endpoint.core.set_data(0x0bff, 0xa004)
        if corrupt:
            endpoint.core.set_data(0xa002, 0xdead)
        audit.write(0x1e, 4)
        record, = audit.records
        assert record['mismatched_words'] == int(corrupt)
        assert record['first_mismatch_addresses'] == ([0xa002] if corrupt else [])
        assert record['destination_after'] == record['expected_destination_after'] == 0xa004
        assert endpoint.core.program(0xa002) == (0xdead if corrupt else 33)
        assert endpoint.core.io(0x57) == 0x0402  # original completion write still runs
    finally:
        endpoint.close()
