#!/usr/bin/env python3
"""Read-only offline dial/calibration probe; emits only whitelisted evidence.

An executed mailbox command is not proof of analog calibration. No serial
hardware is opened and flash writes remain unsupported.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from courier_emu.daa import CourierDaa
from courier_emu.exchange import LineExchange
from courier_emu.images import load_image
from courier_emu.machine import CourierMachine


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    parser.add_argument('--instructions', type=int, default=24_000_000)
    parser.add_argument('--real-delays', action='store_true')
    parser.add_argument('--board-id', type=int, default=7)
    parser.add_argument('--dial-command', default='ATD5551212')
    parser.add_argument('--processing-trace', action='store_true',
                        help='Trace resident output callbacks/gain; DSP data only')
    args = parser.parse_args()
    exchange = LineExchange()
    machine = CourierMachine(load_image(args.image), with_dsp=True,
                             exchange=exchange, fast_delays=not args.real_delays,
                             tick_source='dsp', daa=CourierDaa('quiet'),
                             board_id=args.board_id,
                             serial_input=('ATX3S7=3\r' + args.dial_command + '\r').encode('ascii'))
    bridge = machine.dsp_bridge
    events = []
    serial_controls = []
    ring_summary = {}
    ring_epochs = []
    processing_epochs = []
    download_events = []
    from courier_emu.board3453 import Board3453
    original_board_write = Board3453.write

    def board_write_with_trace(board, port, size, value, pc=None):
        mark = (args.processing_trace and board.finished and port == 0x1e
                and (value == 4 or (value == 2 and (
                    board.overlay_groups < 4 or board.overlay_groups % 100 == 0
                    or board.core.data(0x7f62) == 0x410))))
        if mark:
            download_events.append({
                'cpu_instruction': machine.instructions, 'pc': f'{pc:05x}' if pc else None,
                'strobe': value, 'groups_before': board.overlay_groups,
                'saved_destination': f'{board.core.data(0x7f62):04x}',
                'payload': bytes(board.bridge.window).hex() if value == 2 else None,
                'overlay_words_verified': board.bridge.overlay_words_verified,
                'cpu_registers': {name: machine.uc.reg_read(
                    getattr(machine._x86_const, 'UC_X86_REG_' + name.upper()))
                                  for name in ('ax', 'bx', 'cx', 'si', 'es')},
                'bc_transfer_flags': bytes(machine.uc.mem_read(0x1fe3, 3)).hex()
                    if machine._profile3453.name.startswith('bc-normal') else None,
            })
        return original_board_write(board, port, size, value, pc)

    if args.processing_trace:
        Board3453.write = board_write_with_trace
    processing_addresses = [0x392, 0x39a, 0x39b, 0x3c7, 0x3fb,
                            0x60, 0x61, 0x62, 0x63, 0x64, 0x65,
                            0x69, 0x6a, 0x6b, 0x6c, 0x6d, 0x6e, 0x6f]
    if args.processing_trace:
        bridge.core.set_pc_trace_range(0x10ed, 0x111f)
        bridge.core.set_pc_capture(0x1111, processing_addresses)
    bridge.core.trace_codec_controls()
    bridge.core.trace_data_writes()
    bridge.core.set_data_trace_range(0x7f80, 0x7fdf)
    bridge.core.set_data_event_limit(200000)
    original_status = bridge.status
    original_reset = bridge.core.reset

    def snapshot_diagnostics():
        if not bridge.core.closed:
            serial_controls[:] = [
                {'dsp_cycle': cycle, 'event_pc': f'{pc:04x}',
                 'word': f'{word:04x}', 'register': (word >> 8) & 31,
                 'read': bool(word & 0x2000), 'data': word & 255}
                for cycle, pc, word in bridge.core.register_trace()]
            rows = bridge.core.data_events()
            ring_summary.clear()
            for row in rows:
                key = f"{row['pc']:04x}"
                entry = ring_summary.setdefault(key, {'writes': 0, 'nonzero': 0, 'peak': 0})
                entry['writes'] += 1
                entry['nonzero'] += bool(row['value'])
                signed = row['value'] if row['value'] < 32768 else row['value'] - 65536
                entry['peak'] = max(entry['peak'], abs(signed))

    def snapshot_processing(reason='status'):
        if not args.processing_trace or bridge.core.closed:
            return
        counts = {}
        for row in bridge.core.pc_trace():
            key = f"{row['pc']:04x}"
            entry = counts.setdefault(key, {'hits': 0, 'nonzero_acc': 0})
            entry['hits'] += 1
            entry['nonzero_acc'] += bool(row['acc'])
        processing_epochs.append({
            'cpu_instruction': machine.instructions,
            'reason': reason,
            'capture_pc': '1111',
            'data_addresses': [f'{address:04x}' for address in processing_addresses],
            'captures': bridge.core.pc_captures(),
            'core_state': bridge.core.state(),
            'pmst': f'{bridge.core.register(7):04x}',
            'low_library_data': {f'{address:04x}': f'{bridge.core.data(address):04x}'
                                 for address in (0x15, 0x18, 0x413, 0x417)},
            'program_words': {f'{address:04x}': f'{bridge.core.program(address):04x}'
                              for address in (0x15, 0x18, 0x413, 0x417, 0x1304,
                                              0x130d, 0x1317, 0x1320)},
            'recent_pc_summary': counts,
        })

    def snapshot_status():
        snapshot_processing()
        snapshot_diagnostics()
        return original_status()

    bridge.status = snapshot_status

    def reset_with_snapshot(*values, **options):
        snapshot_processing('reset')
        snapshot_diagnostics()
        ring_epochs.append({'before_reset_cpu_instruction': machine.instructions,
                            'writes_by_pc': dict(ring_summary),
                            'serial': bridge.core.serial_state()})
        result = original_reset(*values, **options)
        if args.processing_trace:
            bridge.core.clear_pc_trace()
        return result

    bridge.core.reset = reset_with_snapshot
    original = bridge._record_runtime_message

    def record(message, pc=None):
        if args.processing_trace and message[0] in (0x13, 0x16):
            snapshot_processing(f'before host command {message[0]:04x}:{message[1]:04x}')
        if message[0] in (0x7d, 0x81, 0x82, 0x84):
            state = bridge.core.codec_state()
            events.append({'cpu_instruction': machine.instructions,
                           'cpu_pc': f'{pc:05x}' if pc is not None else None,
                           'tag': f'{message[0]:04x}', 'word': f'{message[1]:04x}',
                           'primary_frames_before_delivery': state['primary_frames'],
                           'reg17_before_delivery': f"{state['registers'][17]:02x}"})
        original(message, pc)

    bridge._record_runtime_message = record
    try:
        result = machine.run(args.instructions).to_dict()
        # run() owns/closes the DSP; diagnostics are captured in its result.
        state = result['dsp_bridge']['core_codec']
        print(json.dumps({'image': str(args.image), 'real_delays': args.real_delays,
                          'status': result['status'], 'error': result['error'],
                          'instructions': result['instructions'],
                          'serial_text': result['serial_text'], 'ticks': machine.ticks,
                          'codec_controls': events,
                          'accepted_serial_controls': serial_controls,
                          'audio_ring_writes_by_dsp_pc': ring_summary,
                          'audio_ring_reset_epochs': ring_epochs,
                          'processing_trace_epochs': processing_epochs,
                          'download_trace_events': download_events,
                          'cpu_pc': f"{result['registers']['cs'] * 16 + result['registers']['ip']:05x}",
                          'line_audio': result['dsp_bridge']['line_service'],
                          'dsp_serial': result['dsp_bridge']['serial_port'],
                          'codec_final': state,
                          'exchange': exchange.status(),
                          'overlay_downloads': result['dsp_bridge']['overlay_downloads'],
                          'codec_register_history': result['dsp_bridge'].get('codec_register_history'),
                          'calibration_fidelity': 'registers only; ADC calibration not modeled'},
                         indent=2))
    finally:
        Board3453.write = original_board_write
        bridge.core.close()


if __name__ == '__main__':
    main()
