"""Signature-checked, bounded, read-only 403 LAPM receive-error snapshots."""
from collections import Counter

from .v120 import crc16

ERROR_FLAG = 0x03f7
BLER_COUNT = 0x044c
SIGNATURES = {
    0x854c8: bytes.fromhex('83064c040183164e0400'),
    0x90137: bytes.fromhex('c606f70301'),
    0x9015f: bytes.fromhex('c606f70301'),
    0x907b3: bytes.fromhex('813eaf02b8f0'),
}
OUTPUT_SIGNATURE = [0x8b8e, 0x7327, 0xbe41, 0x7e80, 0x80e8, 0xb656,
                    0xbe40, 0x907d, 0x6b7b, 0x6e7d, 0xe388, 0x8333]
CELLS = (0x0256, 0x025a, 0x025e, 0x0262, 0x02a7, 0x02af, 0x02b3,
         0x03bc, 0x03e5, 0x03e7, 0x03f7, 0x044c, 0x044e, 0x04b5)


class RomLinkErrorObserver:
    def __init__(self, machine, limit=4, *, trace_lapm=False):
        if limit < 1:
            raise ValueError('observer limit must be positive')
        if machine.cpu_engine == 'interpreter':
            from . import x86_interpreter as api
            hook = api.UC_HOOK_MEM_WRITE
        else:
            from unicorn import UC_HOOK_MEM_WRITE as hook
            from unicorn import x86_const as api
        self.machine, self.limit = machine, limit
        self.counts, self.events = Counter(), []
        self.output_signature_words = []
        self.output_signature_epoch = None
        self.registers = {name: getattr(api, 'UC_X86_REG_' + name.upper())
                          for name in ('ax', 'bx', 'cx', 'dx', 'si', 'di', 'cs',
                                       'ds', 'es', 'ss', 'sp', 'ip', 'flags')}
        uc = machine.uc
        for address, expected in SIGNATURES.items():
            if bytes(uc.mem_read(address, len(expected))) != expected:
                raise ValueError(f'unsupported analog ROM link-error signature at {address:05x}')
        self.hooks = [uc.hook_add(hook, self.on_write, None, address, address)
                      for address in (ERROR_FLAG, BLER_COUNT)]
        self.lapm_trace = None
        if trace_lapm:
            from .rom_lapm_trace import RomLapmTrace
            self.lapm_trace = RomLapmTrace(machine)

    def arm_bank_trace(self):
        # run() closes the DSP before constructing its final result. Verify the
        # resident while live at CONNECT, never touch a closed core in status().
        bridge = self.machine.dsp_bridge
        core = bridge.core if bridge else None
        self.output_signature_words = [core.program(0x8320 + i)
                                       for i in range(len(OUTPUT_SIGNATURE))] if core else []
        lane = getattr(self.machine, '_lane_io', None)
        if lane is not None and self.output_signature_words == OUTPUT_SIGNATURE:
            # CAL LD at 8323 returns at 8327 after its two delay slots. The
            # shared LAMM helper also services input/mailbox reads; exclude
            # those and idle FF00 output attempts from the freeze trigger.
            lane.arm_bank_trace(pc=0x80e8, caller=0x8327, address=0x0320, idle_word=0xff00)
            self.output_signature_epoch = lane.bank_trace()['epoch']

    def output_exhaustion(self):
        lane = getattr(self.machine, '_lane_io', None)
        if lane is None:
            return None
        report = lane.bank_trace()
        report['output_signature_verified'] = (
            self.output_signature_words == OUTPUT_SIGNATURE
            and report['epoch'] == self.output_signature_epoch)
        report['signature_epoch_at_connect'] = self.output_signature_epoch
        report['trigger_filter'] = {'pc': 0x80e8, 'caller': 0x8327,
                                    'data_address': 0x0320, 'excluded_word': 0xff00}
        report['output_signature_words'] = list(self.output_signature_words)
        return report

    def record_irq(self, kind, vector, value=0):
        lane = getattr(self.machine, '_lane_io', None)
        if lane is None:
            return
        uc = self.machine.uc
        poll = getattr(self.machine, '_worker_poll', None)
        base = poll.state.instruction_base if poll else 0
        lane.record_irq(base + uc.retired, kind, vector, value,
                        uc.reg_read(self.registers['cs']) * 16 + uc.reg_read(self.registers['ip']),
                        uc.reg_read(self.registers['flags']))

    def on_write(self, uc, access, address, size, value, user_data):
        if address not in (ERROR_FLAG, BLER_COUNT):
            return
        kind = 'pending_error' if address == ERROR_FLAG else 'bler_increment'
        regs = {name: uc.reg_read(reg) for name, reg in self.registers.items()}
        pc = regs['cs'] * 16 + regs['ip']
        if self.machine.cpu_engine == 'interpreter':
            pc -= 5
        if not value and not (address == BLER_COUNT and pc == 0x854c8):
            return
        if pc not in ((0x90137, 0x9015f) if address == ERROR_FLAG else (0x854c8,)):
            kind = 'other_write'
        phase = 'online' if self.machine.online_mode else 'pre-online'
        key = f'{phase}:{kind}'
        self.counts[key] += 1
        if kind == 'other_write' or self.counts[key] > self.limit:
            return
        cells = {f'{a:04x}': int.from_bytes(uc.mem_read(regs['ds'] * 16 + a, 2), 'little')
                 for a in CELLS}
        bridge = self.machine.dsp_bridge
        core = bridge.core if bridge else None
        event = {'kind': kind, 'phase': phase, 'pc': pc,
                 'writer_pc_verified': pc in (0x854c8, 0x90137, 0x9015f),
                 'instructions': self.machine.instructions,
                 'line_frame': bridge.line.frames if bridge and bridge.line else None,
                 'registers': regs, 'cells': cells,
                 'write_address': address, 'write_size': size, 'write_value': value,
                 'bler_before_write': int.from_bytes(uc.mem_read(BLER_COUNT, 4), 'little'),
                 'stack_hex': bytes(uc.mem_read(regs['ss'] * 16 + regs['sp'], 32)).hex(),
                 'dsp': core.state() if core else None}
        if kind == 'pending_error':
            alternate = pc == 0x9015f
            start = cells['0262' if alternate else '025a']
            low, high = (0x1a80, 0x1b00) if alternate else (0xb000, 0xc000)
            length = cells['03bc']
            if low <= start < high and 0 < length <= high - low:
                count = min(length, high - start)
                base = regs['es'] * 16
                data = bytes(uc.mem_read(base + start, count))
                if count < length:
                    data += bytes(uc.mem_read(base + low, length - count))
                event['receive_ring'] = {'start': start, 'segment': regs['es'],
                                         'length': length, 'hex': data.hex(),
                                         'crc16_raw': crc16(data),
                                         'crc_matches_firmware': crc16(data) == cells['02af']}
            if core and self.counts[key] == 1:
                lane = getattr(self.machine, '_lane_io', None)
                if lane is not None:
                    event['cpu_dsp_timeline'] = lane.recent_events()
                    event['clock_timeline'] = lane.clock_trace(limit=256)
                    event['output_exhaustion'] = self.output_exhaustion()
                    event['cpu_frame_service'] = {
                        'last_frame': self.machine._last_frame,
                        'frame_instructions': self.machine.frame_instructions,
                        'int0_in_service': self.machine._int0_in_service,
                        'timer_poll_owed': self.machine._timer_poll_owed,
                        'stack': list(self.machine._interrupt_stack)}
                poll = getattr(self.machine, '_worker_poll', None)
                if poll:
                    state = poll.state
                    event['native_frame_service'] = {
                        'last_service': state.last_service, 'last_frame': state.last_frame,
                        'frame_instructions': state.frame_instructions,
                        'int0_in_service': bool(state.int0_in_service),
                        'stack': list(state.stack[:state.stack_depth]),
                        'dirty': bool(state.dirty), 'polls': state.polls}
                event['dsp_bank_history'] = core.io_events(limit=2048, ports=tuple(range(0x56, 0x60)))
                event['dsp_xf_falling_edges'] = core.xf_falling_edges()
                event['dsp_codec'] = core.codec_state()
                event['dsp_cells'] = {f'{a:04x}': core.data(a) for a in
                                      (0x6f, 0x31c, 0x320, 0x322, 0x326, 0x340,
                                       0x341, 0x351, 0x364, 0x37d, 0x398, 0x399, 0x39f, 0x3c0,
                                       0x3c2, 0x3c3, 0x3c4, 0x3c8, 0x3ca, 0x3e4,
                                       0x3e7, 0x3f5, 0x3fb, 0x3ff)}
                expected = [0xb16f, 0x4c80, 0xee00, 0x1026, 0xbe20]
                actual = [core.program(0x8304 + i) for i in range(len(expected))]
                event['dsp_bit_capture'] = {
                    'pc': 0x8304, 'addresses': [0x320, 0x322],
                    'signature_words': actual, 'signature_verified': actual == expected,
                    'rows': core.pc_captures() if actual == expected else []}
                event['dsp_data_history'] = core.data_events()[-2048:]
        self.events.append(event)

    def status(self):
        return {**({'lapm_trace': self.lapm_trace.status()} if self.lapm_trace is not None else {}),
                'counts': dict(self.counts), 'events': list(self.events),
                'bler_count': int.from_bytes(self.machine.uc.mem_read(BLER_COUNT, 4), 'little'),
                'limit_per_phase_and_kind': self.limit,
                'output_exhaustion': self.output_exhaustion(),
                'clock_timeline': (self.machine._lane_io.clock_trace()
                                   if getattr(self.machine, '_lane_io', None) else [])}
