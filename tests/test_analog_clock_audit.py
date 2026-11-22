from types import SimpleNamespace

import pytest

from courier_emu.analog_clock_audit import AnalogClockAudit
from courier_emu.rom_link_errors import SIGNATURES, BLER_COUNT
from courier_emu.rtp import RtpTransmitStats


class Core:
    def __init__(self):
        self.cycles = 100

    def codec_state(self):
        return dict(cycles=self.cycles, primary_frames=12, rx_empty_frames=2,
                    codec_rx_size=32, sample_rate=9600, frame_period=4200)

    def serial_state(self):
        return dict(codec_rx_queued=100, codec_rx_consumed=68, line_tx_writes=12,
                    drr_reads=11, dxr_writes=11)


def machine():
    reads = []
    def read(address, size):
        reads.append((address, size))
        if address == BLER_COUNT:
            return (7).to_bytes(4, 'little')
        return SIGNATURES[address]
    session = SimpleNamespace(_rtp_tx_stats=RtpTransmitStats(),
                              rtp_packets_received=50, rtp_packets_sent=48)
    line = SimpleNamespace(sip=session, _pending=[1, 2], active_underrun_samples=0)
    return SimpleNamespace(uc=SimpleNamespace(mem_read=read),
                           dsp_bridge=SimpleNamespace(core=Core(), _sip_line=line,
                                                      _line_service={'tx_consumed': 12}),
                           instructions=1000, online_mode=True), reads


def test_read_only_snapshot_retains_pre_reset_counter_evidence():
    m, reads = machine()
    audit = AnalogClockAudit(m)
    first = audit.sample(10)
    assert first['bler_raw_044c'] == 7
    assert first['codec']['rx_empty_frames'] == 2
    assert first['adapter_pending'] == 2
    assert first['epoch'] == 0
    assert len(reads) == len(SIGNATURES) + 1
    m.dsp_bridge.core.cycles = 200
    audit.sample(11)
    assert len(reads) == len(SIGNATURES) + 2
    m.dsp_bridge.core.cycles = 5
    assert audit.sample(12)['epoch'] == 1
    assert first['codec']['cycles'] == 100


def test_snapshot_copies_mutable_history_and_observes_phase_and_queue_under_lock():
    from threading import RLock
    m, _ = machine()
    session = m.dsp_bridge._sip_line.sip
    session._rtp_lock = RLock()
    session.state = 'connected'
    session.codewords = False
    session._tx_audio = [1, 2, 3]
    session._rtp_tx_stats.rebuffered(9, 0)
    line = m.dsp_bridge._sip_line
    line.paced_seconds = .25
    line.exchange = SimpleNamespace(state='connected')
    snapshot = AnalogClockAudit(m).sample(10)
    session._rtp_tx_stats.rebuffer_history[0]['queued_samples'] = 99
    session._rtp_tx_stats.rebuffered(11, 1)
    assert snapshot['rtp_tx']['rebuffer_history'][0]['queued_samples'] == 0
    assert len(snapshot['rtp_tx']['rebuffer_history']) == 1
    assert snapshot['rtp_tx_queue_samples'] == 3
    assert snapshot['sip_state'] == 'connected'
    assert snapshot['line_state'] == 'connected'
    assert snapshot['pacing']['paced_seconds'] == .25


def test_core_replacement_separates_epochs_even_when_cycles_increase():
    m, _ = machine()
    audit = AnalogClockAudit(m)
    audit.sample(10)
    m.dsp_bridge.core = Core()
    m.dsp_bridge.core.cycles = 500
    assert audit.sample(11)['epoch'] == 1


def test_unsupported_firmware_is_rejected_before_reading_counters():
    m, _ = machine()
    m.uc.mem_read = lambda address, size: b'\x00' * size
    with pytest.raises(ValueError, match='unsupported clock-audit ROM'):
        AnalogClockAudit(m).sample(10)
