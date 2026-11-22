#!/usr/bin/env python3
"""Offline B/C 2.2.09 unchanged-peer trace; full CPU context stays private."""
from __future__ import annotations

import argparse
from collections import deque
import json
from pathlib import Path
import subprocess
import struct
import sys
import tempfile
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def trace_worker(args):
    from courier_emu.board3453 import Board3453
    from courier_emu.panel import DIP_PRESETS
    from courier_emu import worker
    from courier_emu.machine import CourierMachine

    events = deque(maxlen=128)
    reports_seen = set()
    channel_events = set()
    tx_words = []
    rx_words = []
    cpu_rx_words = []
    cpu_rx_bytes = []
    cpu_rx_events = []
    serial_events = []
    hook_events = []
    receiver_samples = []
    receiver_soft_words = []
    receiver_cycles = []
    framer_contexts = []
    framer_pending = None
    capture_addresses = [0x6d, 0x6e, 0x29d, *range(0x3a0, 0x3b0)]
    processing_addresses = [0x392, 0x39a, 0x39b, 0x3c7, 0x33e, 0x33f,
                            0x3e8, *range(0x3f0, 0x3f4)]
    original_init = Board3453.__init__
    original_write = Board3453.write
    original_read = Board3453.read
    original_commit = Board3453.overlay_commit
    original_run = CourierMachine.run
    active_machine = None
    import courier_emu.machine as machine_module
    machine_module.MEM_WATCH_EVENTS = 4096
    public = Path(__file__).resolve().parents[1] / 'dumps/3453bc-firmware-read-2.2.09/firmware.bin'
    iret_pcs = {0x40000 + i for i, value in enumerate(public.read_bytes()) if value == 0xcf}
    observed_returns = set()

    def run(machine, *values, **options):
        nonlocal active_machine
        active_machine = machine
        if machine._profile3453 is None or machine._profile3453.name != 'bc-normal-2.2.09':
            raise ValueError('download trace currently supports B/C normal 2.2.09 only')
        dtr_deadline = None
        dtr_deasserted_at = None
        serial_seen = 0
        hook_seen = None
        def observe(address):
            nonlocal dtr_deadline, dtr_deasserted_at, framer_pending, serial_seen, hook_seen
            hook = bool(machine.dsp_bridge.daa.off_hook)
            if hook != hook_seen:
                if len(hook_events) < 64:
                    hook_events.append({'instruction': machine.instructions, 'off_hook': hook})
                hook_seen = hook
            if len(machine.serial) > serial_seen:
                if len(serial_events) < 1024:
                    serial_events.append({'instruction': machine.instructions,
                                          'hex': bytes(machine.serial[serial_seen:]).hex()})
                serial_seen = len(machine.serial)
            if args.drop_dtr_after_connect_ms is not None:
                if machine.online_mode and dtr_deadline is None:
                    dtr_deadline = machine.instructions + args.drop_dtr_after_connect_ms * 4348
                if dtr_deadline is not None and machine.instructions >= dtr_deadline and machine.terminal_dtr is None:
                    machine.terminal_dtr = False
                    dtr_deasserted_at = machine.instructions
                    snapshot(machine.dsp_bridge.board3453, 'dtr-deasserted')
            if machine.online_mode and machine.data_rx_bytes:
                if args.framer_trace and address == 0x6ea94 and len(framer_contexts) < 16000:
                    framer_pending = {
                        'before': bytes(machine.uc.mem_read(0x1ecc, 8)).hex(),
                        'registers': {name: machine.uc.reg_read(getattr(machine._x86_const, 'UC_X86_REG_' + name.upper()))
                                      for name in ('ax', 'bx', 'cx', 'dx', 'si', 'di', 'bp', 'sp',
                                                   'cs', 'ds', 'es', 'ss', 'flags')},
                        'rx_pointers': bytes(machine.uc.mem_read(0x6c2, 4)).hex(),
                        'flags694': bytes(machine.uc.mem_read(0x694, 1))[0],
                    }
                if args.framer_trace and address == 0x6ea98 and framer_pending is not None:
                    framer_pending['after'] = bytes(machine.uc.mem_read(0x1ecc, 8)).hex()
                    framer_contexts.append(framer_pending)
                    framer_pending = None
                if address == 0x6ea94 and len(cpu_rx_words) < 16000:
                    cpu_rx_words.append(machine.uc.reg_read(machine._x86_const.UC_X86_REG_AX))
                    if args.rx_audio_trace and len(receiver_samples) < 64000:
                        core = machine.dsp_bridge.core
                        for row in core.pc_captures():
                            receiver_cycles.append(row[1])
                            sample = row[5]
                            receiver_samples.append(sample - 0x10000 if sample & 0x8000 else sample)
                            receiver_soft_words.append(row[6])
                        core.clear_pc_captures()
                if address == 0x6878a and len(cpu_rx_bytes) < 1024:
                    byte = machine.uc.reg_read(machine._x86_const.UC_X86_REG_AX) & 0xff
                    cpu_rx_bytes.append(byte)
                    cpu_rx_events.append({'instruction': machine.instructions, 'byte': byte})
            if machine._timer_in_handler and address in iret_pcs and address not in observed_returns:
                observed_returns.add(address)
                snapshot(machine.dsp_bridge.board3453, 'mailbox-iret',
                         return_pc=f'{address:05x}',
                         vector=bytes(machine.uc.mem_read(0x30, 4)).hex())
        machine._code_observer = observe
        result = original_run(machine, *values, **options)
        report = result.to_dict()
        if receiver_samples:
            with wave.open(str(args.output.with_name(args.side + '-receiver-input.wav')), 'wb') as wav:
                wav.setparams((1, 2, 7200, 0, 'NONE', 'not compressed'))
                wav.writeframes(struct.pack('<' + 'h' * len(receiver_samples), *receiver_samples))
        args.output.with_name(args.side + '-summary.json').write_text(json.dumps({
            k: report[k] for k in ('status', 'error', 'instructions', 'serial_text',
                                   'mem_watch', 'data_rx_bytes', 'data_tx_bytes',
                                   'serial_input_remaining')
        } | {'dsp_messages': report['dsp_bridge']['runtime_message_counts'],
             'tx_peak': report['dsp_bridge']['line_service']['tx_peak_line'],
             'rx_peak': report['dsp_bridge']['line']['rx_peak'],
             'tx_words': tx_words, 'rx_words': rx_words,
             'cpu_rx_words': cpu_rx_words, 'cpu_rx_bytes': cpu_rx_bytes,
             'cpu_rx_events': cpu_rx_events, 'serial_events': serial_events,
             'hook_events': hook_events,
             'receiver_soft_words': receiver_soft_words,
             'receiver_cycles': receiver_cycles,
             'framer_contexts': framer_contexts,
             'dtr_deasserted_at': dtr_deasserted_at}, indent=2) + '\n')
        return result

    CourierMachine.run = run

    def snapshot(board, kind, **extra):
        core = board.core
        cpu = {}
        if active_machine is not None:
            machine = active_machine
            cpu = {
                'registers': {name: f'{machine.uc.reg_read(getattr(machine._x86_const, "UC_X86_REG_" + name.upper())):04x}'
                              for name in ('ax', 'bx', 'cx', 'si', 'cs', 'es', 'ip')},
                'profile': machine._profile3453.name,
                'transfer_flags': bytes(machine.uc.mem_read(0x1fe3, 3)).hex(),
                'download_table': bytes(machine.uc.mem_read(0x6683e, 66)).hex(),
                'off_hook': bool(board.bridge.daa.off_hook),
                'serial_in_handler': machine._serial_in_handler,
                'timer_in_handler': machine._timer_in_handler,
                'mailbox_watchdog': int.from_bytes(machine.uc.mem_read(0x176, 1), 'little'),
                'call_flags': bytes(machine.uc.mem_read(0x693, 2)).hex(),
                'dte_tx_pointers': bytes(machine.uc.mem_read(0x6b8, 4)).hex(),
                'dte_rx_pointers': bytes(machine.uc.mem_read(0x6c2, 4)).hex(),
                'rx_callbacks': bytes(machine.uc.mem_read(0x714, 10)).hex(),
                'rx_framer': bytes(machine.uc.mem_read(0x1ecc, 8)).hex(),
                'tx_pump': machine._serial_tx_pump,
                'tx_callback': machine._serial_tx_callback,
                'dtr_option': bytes(machine.uc.mem_read(0x979, 1)).hex(),
                'p1_gpio': bytes(machine.uc.mem_read(0xff58, 4)).hex(),
                'queue_drop_counts': {k: v for k, v in machine.pc_watch_counts.items()
                                      if k in ('packet-drop', 'word-drop')},
                'channel_watch_counts': {k: v for k, v in machine.pc_watch_counts.items()
                                         if k in ('rx-word', 'rx-byte')},
                'queue_drops': [{k: row[k] for k in ('name', 'pc', 'instructions', 'ax', 'bx', 'cx')}
                                for row in machine.pc_watch_events
                                if row['name'] in ('packet-drop', 'word-drop')][-24:],
            }
        events.append({
            'cpu': cpu,
            'kind': kind, 'cpu_instruction': board.bridge._instructions,
            'bootstrap_epoch': board.bridge.bootstraps,
            'groups': board.overlay_groups, 'pending': board.overlay_pending,
            'status': f'{core.io(0x57):04x}',
            'pa6': f'{core.io(0x56):04x}',
            'host_data_status': f'{core.data_channel_status():04x}',
            'data_io': core.io_port_stats([0x56, *range(0x58, 0x5e)]),
            'channel_program': {f'{a:04x}': f'{core.program(a):04x}'
                                for a in (0xb4, 0xb9, 0x113, 0x11f, 0x121,
                                          0x18a, 0x193, 0x19c)},
            'header': f'{board.header:04x}', 'word': f'{board.word:04x}',
            'core': core.state(),
            'registers': {f'{a:02x}': f'{core.register(a):04x}'
                          for a in (7, 0x10, 0x11, 0x12, 0x13, 0x14,
                                    0x15, 0x16, 0x17, 0x1f)},
            'data': {f'{a:04x}': f'{core.data(a):04x}'
                     for a in (0x69, 0x6a, 0x6b, 0x6c, 0x6d, 0x6e, 0x6f,
                               0x7f53, 0x7f60, 0x7f61, 0x7f62,
                               0x3d2, 0x3d3, 0x3d4, 0x3d5, 0x3d6, 0x3d7,
                               0x322, 0x324, 0x325, 0x326, 0x327,
                               0x352, 0x354, 0x355, 0x356, 0x357, 0x37b, 0x3fb,
                               0x3e3, 0x3e9, 0x3eb,
                               *capture_addresses, *processing_addresses)},
            'serial': {k: v for k, v in core.serial_state().items()
                       if k in ('dxr', 'dxr_writes', 'last_dxr_pc',
                                'line_tx_writes', 'line_tx_nonzero',
                                'codec_rx_peak', 'line_tx_last_pc')},
            'codec': {k: v for k, v in core.codec_state().items()
                      if k in ('sample_rate', 'primary_frames', 'registers')},

            **({'capture_addresses': [f'{a:04x}' for a in capture_addresses],
                'originate_captures': core.pc_captures()[-64:]}
               if args.processing_trace else {}),
            'destination_writes': core.data_write_count(0x7f62),
            **extra,
        })

    def init(board, *values, **options):
        original_init(board, *values, **options)
        board.core.set_pc_trace_range(0x112a, 0x1171)
        board.core.trace_data_writes()
        board.core.set_data_trace_range(0x7f60, 0x7f63)
        board.core.set_data_event_limit(20000)
        original_close = board.core.close

        def close():
            if not board.core.closed:
                snapshot(board, 'core-close')
            return original_close()

        board.core.close = close
        if args.processing_trace:
            board.core.set_pc_capture(0x1e45, capture_addresses)
            original_reset = board.core.reset

            def reset(*values, **options):
                snapshot(board, 'core-reset')
                return original_reset(*values, **options)

            board.core.reset = reset
        elif args.rx_audio_trace:
            board.core.set_pc_capture(0x4538, [0x38f, 0x3ea])

    def write(board, port, size, value, pc=None):
        runtime_lane = (board.finished and port in (0x58, 0x5a, 0x5c, 0x5e)
                        and (board.header == 2 or (port == 0x58 and value == 2)))
        if board.finished:
            if port == 0x1e and value == 4:
                snapshot(board, 'strobe4', cpu_pc=f'{pc:05x}' if pc else None)
            elif port == 0x1c and value & 1 and board.header == 2:
                snapshot(board, 'request2', cpu_pc=f'{pc:05x}' if pc else None)
        result = original_write(board, port, size, value, pc)
        if active_machine and active_machine.online_mode and active_machine.data_rx_bytes:
            if port == 0x18:
                for channel in range(6):
                    if value & (1 << channel) and len(tx_words) < 16000:
                        tx_words.append(board.core.io(0x58 + channel))
            key = ('write', port, size, value)
            if (0x40 <= port <= 0x56 and value not in (0, 7)
                    and key not in channel_events and len(channel_events) < 100):
                channel_events.add(key)
                snapshot(board, 'channel-word', port=f'{port:02x}', size=size,
                         value=f'{value:04x}', cpu_pc=f'{pc:05x}' if pc else None)
            if port in (0x18, 0x1a) and key not in channel_events:
                channel_events.add(key)
                snapshot(board, 'channel-post', port=f'{port:02x}', value=f'{value:04x}')
        if runtime_lane:
            snapshot(board, 'runtime-lane', port=f'{port:02x}', size=size,
                     value=f'{value:04x}', cpu_pc=f'{pc:05x}' if pc else None)
        return result

    def read(board, port, size):
        pending = board.overlay_pending
        result = original_read(board, port, size)
        if port == 0x1e and pending and not board.overlay_pending:
            snapshot(board, 'ready')
        if active_machine and active_machine.online_mode and active_machine.data_rx_bytes:
            if 0x40 <= port <= 0x54 and port % 4 == 0 and len(rx_words) < 16000:
                rx_words.append(board.core.io_output(0x58 + (port - 0x40) // 4))
            key = ('read', port, result)
            if port in (0x18, 0x1a) and key not in channel_events:
                channel_events.add(key)
                snapshot(board, 'channel-status', port=f'{port:02x}', size=size, value=result)
        if args.processing_trace and port in (0x58, 0x5c) and board.finished:
            tag, word = ((board.bridge._runtime_inbound[0])
                         if board.bridge._runtime_inbound else
                         (board.core.io_output(0x5e), board.core.io_output(0x5f)))
            key = (board.bridge.bootstraps, tag, word)
            if tag in (4, 8, 0x28, 0x3d) and key not in reports_seen:
                reports_seen.add(key)
                snapshot(board, 'dsp-report', report_tag=f'{tag:04x}',
                         report_word=f'{word:04x}')
        return result

    def commit(board):
        if board.overlay_groups < 2:
            snapshot(board, 'commit-before', payload=bytes(board.bridge.window).hex())
        try:
            result = original_commit(board)
        except Exception as error:
            snapshot(board, 'commit-error', error=str(error),
                     payload=bytes(board.bridge.window).hex(),
                     pc_trace=board.core.pc_trace()[-96:],
                     destination_trace=board.core.data_events()[-48:],
                     loader_program={f'{a:04x}': f'{board.core.program(a):04x}'
                                     for a in range(0x112a, 0x1172)})
            raise
        if board.overlay_groups <= 2:
            snapshot(board, 'commit-after')
        return result

    Board3453.__init__ = init
    Board3453.write = write
    Board3453.read = read
    Board3453.overlay_commit = commit
    preset = 'dedicated-line' if args.side == 'a' else 'dedicated-line-originate'
    sys.argv = [sys.argv[0], str(args.image), '--with-dsp', '--tick-source', 'dsp',
                '--tick-ms', '5', '--daa-codec',
                '--trace-pc', '0x67d89=packet-drop',
                '--trace-pc', '0x67d5a=word-drop',
                '--trace-pc', '0x6ea94=rx-word',
                '--trace-pc', '0x6878a=rx-byte',
                '--mem-watch', '0x693:0x695',
                '--instructions', str(args.instructions), '--line-link', args.socket,
                '--line-audio-only', '--line-frames', str(args.frames),
                '--daa-line', 'quiet', '--serial-input-hex',
                (args.setup + '\rAT&L1\r').encode('latin-1').hex()]
    if args.framer_trace:
        sys.argv.extend(['--trace-pc', '0x6ea98=rx-word-return'])
    if args.send:
        data = args.send.encode('latin-1').hex()
        if args.send_at_instruction is None:
            sys.argv.extend(['--serial-after-connect-hex', data])
        else:
            sys.argv.extend(['--serial-schedule', f'{args.send_at_instruction}:{data}'])
    if args.side == 'a':
        sys.argv.append('--line-listen')
    for switch in sorted(DIP_PRESETS[preset]):
        if switch == 'dtr-override' and args.respect_dtr:
            continue
        sys.argv.extend(('--dip', switch))
    try:
        return worker.main()
    finally:
        args.output.write_text(json.dumps(list(events), indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    parser.add_argument('--instructions', type=int, default=24_000_000)
    parser.add_argument('--frames', type=int, default=70)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--side', choices=('a', 'b'))
    parser.add_argument('--socket')
    parser.add_argument('--processing-trace', action='store_true')
    parser.add_argument('--framer-trace', action='store_true',
                        help='private CPU-context differential trace; do not publish raw')
    parser.add_argument('--rx-audio-trace', action='store_true',
                        help='capture only receiver input PCM, soft decisions and cycle cadence')
    parser.add_argument('--send', default='', help='DTE bytes queued only after genuine CONNECT')
    parser.add_argument('--setup', default='AT&N1&U1')
    parser.add_argument('--a-send')
    parser.add_argument('--b-send')
    parser.add_argument('--send-at-instruction', type=int,
                        help='explicit later DTE stimulus, not a runtime readiness workaround')
    parser.add_argument('--respect-dtr', action='store_true',
                        help='leave the physical DTR-override DIP open on both peers')
    parser.add_argument('--drop-dtr-side', choices=['a', 'b', 'both'], default='a',
                        help='parent probe: which terminal drops DTR')
    parser.add_argument('--drop-dtr-after-connect-ms', type=int,
                        help='deassert only peer A DTR; no guest RAM/callback edits')
    args = parser.parse_args()
    if args.rx_audio_trace and args.processing_trace:
        parser.error('choose one PC capture mode')
    if args.side:
        return trace_worker(args)
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='courier-download-') as directory:
        socket = str(Path(directory) / 'line.sock')
        children = []
        for side in ('a', 'b'):
            # Full worker reports can contain non-whitelisted diagnostics.
            # Discard stdout rather than publishing those reports.
            error = (args.output / f'{side}-stderr.txt').open('w')
            command = [sys.executable, str(Path(__file__).resolve()), str(args.image),
                       '--side', side, '--socket', socket, '--instructions',
                       str(args.instructions), '--frames', str(args.frames),
                       '--output', str(args.output / f'{side}-transport.json'),
                       '--setup', args.setup]
            if (args.drop_dtr_after_connect_ms is not None
                    and args.drop_dtr_side in ('both', side)):
                command.extend(['--drop-dtr-after-connect-ms', str(args.drop_dtr_after_connect_ms)])
            if args.respect_dtr:
                command.append('--respect-dtr')
            if args.processing_trace:
                command.append('--processing-trace')
            if args.rx_audio_trace:
                command.append('--rx-audio-trace')
            if args.framer_trace:
                command.append('--framer-trace')
            payload = args.a_send if side == 'a' else args.b_send
            if payload is None:
                payload = args.send
            if payload:
                command.extend(['--send', payload])
            if args.send_at_instruction is not None:
                command.extend(['--send-at-instruction', str(args.send_at_instruction)])
            children.append((subprocess.Popen(command, stdout=subprocess.DEVNULL,
                                              stderr=error), error))
        codes = []
        for child, error in children:
            codes.append(child.wait())
            error.close()
        print(json.dumps({'exit_codes': codes, 'output': str(args.output)}))
        return int(any(codes))


if __name__ == '__main__':
    raise SystemExit(main())
