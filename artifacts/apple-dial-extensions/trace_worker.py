"""Capture codec PCM across every DSP generation during this dial experiment."""
import atexit
import json
import os
from pathlib import Path
import runpy
import struct
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from courier_emu.apple_line import AppleLine
from courier_emu.machine import CourierMachine

prefix = os.environ['APPLE_CALL_TRACE']
tx = open(prefix + '-tx.s16', 'wb')
rx = open(prefix + '-rx.s16', 'wb')
events = open(prefix + '-frames.jsonl', 'w')
hw_tx = open(prefix + '-hardware-tx.s16', 'wb')
hw_rx = open(prefix + '-hardware-rx.s16', 'wb')
hw_events = open(prefix + '-hardware-frames.jsonl', 'w')
# Diagnostic A/B only: restore preconverted RX without changing guest state.
if os.environ.get('APPLE_RX_GRID', 'hardware') == 'codec':
    delattr(AppleLine, 'enable_native_receive')
diagnostics = os.environ.get('APPLE_CALL_DIAGNOSTICS') == '1'
stop_after = float(os.environ.get('APPLE_STOP_AFTER_CONNECT_SECONDS', '0'))
post_dial_value = os.environ.get('APPLE_POST_DIAL_GAIN', '')
post_dial_gain = float(post_dial_value) if post_dial_value else None
if post_dial_gain is not None and not 0 <= post_dial_gain <= 1:
    raise ValueError('post-dial gain must be between 0 and 1')
post_dial_applied = [False]
states = open(prefix + '-state.jsonl', 'w') if diagnostics else None
for stream in (tx, rx, events, hw_tx, hw_rx, hw_events, states):
    if stream is not None:
        atexit.register(stream.close)
original = AppleLine.service_codec
original_exchange = AppleLine._exchange
mailbox_recorder = None
if diagnostics:
    from courier_emu.dsp import NativeC5x
    from tools.apple_mailbox_trace import MailboxRecorder, install
    if os.environ.get('APPLE_V90_PROBE') == '1':
        from tools.apple_v90_trace import V90MailboxRecorder
        mailbox_recorder = V90MailboxRecorder(prefix)
    else:
        mailbox_recorder = MailboxRecorder(prefix)
    install(mailbox_recorder, NativeC5x)
    from courier_emu.bridge import CourierDspBridge
    original_runtime_message = CourierDspBridge._record_runtime_message

    def traced_runtime_message(self, words, pc):
        original_runtime_message(self, words, pc)
        mailbox_recorder.safe(mailbox_recorder.host_command, words, pc, self._instructions)

    CourierDspBridge._record_runtime_message = traced_runtime_message
    atexit.register(mailbox_recorder.close)
position = [0, 0]
hw_position = [0, 0]


def hardware_exchange(self, payload, off_hook, resetting=False):
    event = dict(time=time.monotonic(), rate=self.rate, off_hook=off_hook,
                 resetting=resetting, tx_start=hw_position[0], tx_count=len(payload),
                 rx_start=hw_position[1])
    hw_tx.write(struct.pack(f'<{len(payload)}h', *payload))
    hw_position[0] += len(payload)
    try:
        raw = original_exchange(self, payload, off_hook, resetting)
    except BaseException:
        event['failed'] = True
        hw_events.write(json.dumps(event)+'\n')
        raise
    hw_rx.write(raw)
    event['rx_count'] = len(raw)//2
    hw_position[1] += len(raw)//2
    hw_events.write(json.dumps(event)+'\n')
    return raw


AppleLine._exchange = hardware_exchange
machine_ref = [None]
last_snapshot = [0.0]
connected_at = [None]
if diagnostics or stop_after or post_dial_gain is not None:
    original_init = CourierMachine.__init__

    def observed_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        machine_ref[0] = self

    CourierMachine.__init__ = observed_init


def observe(now, line):
    machine = machine_ref[0]
    if machine is None:
        return
    bridge = machine.dsp_bridge
    if (post_dial_gain is not None and not post_dial_applied[0] and bridge is not None
            and line._off_hook and any(k.startswith('0017:') for k in bridge.runtime_message_counts)):
        line.tx_gain = post_dial_gain
        post_dial_applied[0] = True
        print(f'[trace] diagnostic TX gain {post_dial_gain} after native command 17', file=sys.stderr)
    if stop_after and b'\r\nCONNECT' in bytes(machine.serial):
        if connected_at[0] is None:
            connected_at[0] = now
        elif now - connected_at[0] >= stop_after:
            machine.request_stop()
    if states is None or now - last_snapshot[0] < 1:
        return
    last_snapshot[0] = now
    bridge = machine.dsp_bridge
    if bridge is None:
        return
    core = bridge.core
    if mailbox_recorder is not None:
        mailbox_recorder.safe(mailbox_recorder.collect, core)
    # Only state accessors / RAM cells: never reads an emulated DRR or a
    # peripheral with consume-on-read semantics, and never patches guest state.
    snapshot = {'time': now, 'instructions': machine.instructions,
        'serial': bytes(machine.serial).decode('ascii', 'backslashreplace'),
        'dsp': core.state(), 'codec': core.codec_state(), 'serial_port': core.serial_state(),
        'host_io_input': {f'{p:04x}': core.io(p) for p in (0x56, 0x57)},
        'host_io_output': {f'{p:04x}': core.io_output(p) for p in (0x5e, 0x5f, 0x60)},
        'active': bridge.active, 'launched': bridge.launched,
        'tx_gain': line.tx_gain, 'post_dial_gain_applied': post_dial_applied[0],
        'overlay_id': bridge.overlay_id, 'overlay_destinations': bridge.overlay_destinations,
        'dsp_tags': dict(bridge.dsp_originated_tags),
        'host_tags': dict(bridge.runtime_message_counts),
        'ram': {f'{a:04x}': core.data(a) for a in (0x006d,0x006e,0x006f,0x0304,0x0306,0x031a,0x031b,0x0337,
                                                   0x038f,0x0393,0x0394,0x039f,0x03cb,0x03e1,0x03e2,
                                                   0x069c,0xa51b,0xd2a8,0xff00,0xff01,0xff18,0xff19,
                                                   0xfff1,0xfff2,0xfff4,0xfff6,0xfff7)}}
    states.write(json.dumps(snapshot) + '\n')


def traced(self, samples, rate, hook):
    tx.write(struct.pack(f'<{len(samples)}h', *samples))
    event = {'time': time.monotonic(), 'cpu_time': time.process_time(),
             'rate': rate, 'off_hook': hook, 'tx_gain': self.tx_gain,
             'rx_rate': self.rate if self.native_receive else rate,
             'tx_start': position[0], 'tx_count': len(samples), 'rx_start': position[1]}
    position[0] += len(samples)
    try:
        incoming = original(self, samples, rate, hook)
    except BaseException:
        event['failed'] = True
        events.write(json.dumps(event) + '\n')
        raise
    rx.write(struct.pack(f'<{len(incoming)}h', *incoming))
    event['rx_count'] = len(incoming)
    position[1] += len(incoming)
    events.write(json.dumps(event) + '\n')
    observe(time.monotonic(), self)
    return incoming


AppleLine.service_codec = traced
sys.argv = ['courier_emu.worker', *sys.argv[1:]]
runpy.run_module('courier_emu.worker', run_name='__main__')
