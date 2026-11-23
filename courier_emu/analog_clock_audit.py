"""Read-only live clock/queue snapshots for the signature-checked 403 ROM.

No hooks, injected interrupts, buffer changes, or protocol decisions. Call at
low frequency from the run thread, before the DSP is closed/reset, so final
post-hangup counters do not erase the evidence of a preceding data stall.
"""
import time
from contextlib import nullcontext

from .rom_link_errors import SIGNATURES, BLER_COUNT


class AnalogClockAudit:
    def __init__(self, machine):
        self.machine = machine
        self.verified = False
        self.epoch = 0
        self.last_cycles = None
        self.last_core = None

    def sample(self, now):
        m = self.machine
        if not self.verified:
            for address, expected in SIGNATURES.items():
                if bytes(m.uc.mem_read(address, len(expected))) != expected:
                    raise ValueError(f'unsupported clock-audit ROM at {address:05x}')
            self.verified = True
        bridge = m.dsp_bridge
        core = bridge.core
        codec = core.codec_state()
        cycles = codec['cycles']
        if self.last_core is not None and (core is not self.last_core or cycles < self.last_cycles):
            self.epoch += 1
        self.last_core, self.last_cycles = core, cycles
        serial = core.serial_state()
        line = bridge._sip_line
        session = line.sip
        # Globals in the 403's physical low RAM. Retain raw values; unlike
        # the write observer this does not claim an ISR/DS-context sample.
        bler = int.from_bytes(m.uc.mem_read(BLER_COUNT, 4), 'little')
        # The media worker mutates counters and queues independently. Copy a
        # coherent observation while holding its existing lock; never do ROM
        # reads or output I/O under that lock. Older test/session adapters have
        # no worker and need no lock.
        with getattr(session, '_rtp_lock', nullcontext()):
            tx = session._rtp_tx_stats.status()
            tx['rebuffer_history'] = [dict(event) for event in tx['rebuffer_history']]
            source = getattr(session, '_tx_codewords' if getattr(session, 'codewords', False)
                             else '_tx_audio', None)
            queued = None if source is None else len(source)
            rx_packets = session.rtp_packets_received
            tx_packets = session.rtp_packets_sent
            sip_state = getattr(session, 'state', None)
        return {
            'monotonic_seconds': now, 'epoch': self.epoch,
            'thread_cpu_seconds': time.thread_time(),
            'process_cpu_seconds': time.process_time(),
            'cpu_instructions': m.instructions,
            'online_mode': m.online_mode, 'bler_raw_044c': bler,
            'codec': {key: codec[key] for key in (
                'cycles', 'primary_frames', 'rx_empty_frames', 'codec_rx_size',
                'sample_rate', 'frame_period')},
            'serial': {key: serial[key] for key in (
                'codec_rx_queued', 'codec_rx_consumed', 'line_tx_writes',
                'drr_reads', 'dxr_writes')},
            'bridge_tx_consumed': bridge._line_service['tx_consumed'],
            'adapter_pending': len(line._pending),
            'adapter_active_underrun_samples': line.active_underrun_samples,
            'sip_state': sip_state,
            'line_state': getattr(line.exchange, 'state', None) if hasattr(line, 'exchange') else None,
            'pacing': {key: getattr(line, key, None) for key in (
                'paced_seconds', 'late_seconds', 'peak_late_seconds', 'frames', 'late_frames')},
            'rtp_tx_queue_samples': queued,
            'rtp_tx': tx,
            'rtp_rx_packets': rx_packets,
            'rtp_tx_packets': tx_packets,
        }
