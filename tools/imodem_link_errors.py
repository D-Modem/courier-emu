"""Read-only, bounded observers for Ie030002's LAPM receive-error path.

Addresses are tied to checked original instruction signatures. Memory hooks
observe the pending-error flag and the low word of the 32-bit ATI6 BLER count;
they do not replace instructions or write guest state.
"""
from collections import Counter

RAM_SEGMENT = 0x2600
ERROR_FLAG = 0x330b5
BLER_COUNT = 0x33110
SIGNATURES = {
    0xa9881: bytes.fromhex('830610d101831612d100'),
    0xb4c8a: bytes.fromhex('c606b5d001'),
    0xb4cb2: bytes.fromhex('c606b5d001'),
    0xb5268: bytes.fromhex('813e2ecfb8f0'),
}
CELLS = (0xca66, 0xca68, 0xcaa2, 0xcaa6, 0xcaaa, 0xcaae,
         0xcf26, 0xcf2a, 0xcf2e, 0xcf32, 0xd070, 0xd0a3, 0xd0a5, 0xd0b5)


def crc16_lapm(data):
    """Raw reflected CCITT register; a complete good HDLC frame gives F0B8."""
    crc = 0xffff
    for value in data:
        crc ^= value
        for _ in range(8):
            crc = (crc >> 1) ^ (0x8408 if crc & 1 else 0)
    return crc


class LinkErrorObserver:
    def __init__(self, machine, context, limit=4):
        if getattr(machine, 'cpu_engine', 'unicorn') == 'interpreter':
            from courier_emu import x86_interpreter as api
            hook_kind = api.UC_HOOK_MEM_WRITE
        else:
            from unicorn import UC_HOOK_MEM_WRITE as hook_kind
            from unicorn import x86_const as api

        if limit < 1:
            raise ValueError('observer limit must be positive')
        self.machine = machine
        self.context = context
        self.limit = limit
        self.events = []
        self.counts = Counter()
        self.registers = {name: getattr(api, 'UC_X86_REG_' + name.upper())
                          for name in ('ax', 'bx', 'cx', 'dx', 'si', 'di',
                                       'cs', 'ds', 'es', 'ss', 'sp', 'ip', 'flags')}
        uc = machine.uc
        for address, expected in SIGNATURES.items():
            if bytes(uc.mem_read(address, len(expected))) != expected:
                raise ValueError(f'unsupported I-modem firmware signature at {address:05x}')
        self.hooks = [uc.hook_add(hook_kind, self.on_write, None, address, address)
                      for address in (ERROR_FLAG, BLER_COUNT)]

    def on_write(self, uc, access, address, size, value, user_data):
        if address not in (ERROR_FLAG, BLER_COUNT):
            return
        value &= (1 << (8 * size)) - 1
        if not value:
            # A zero low word can also be a real FFFF -> 0000 increment.
            pc = (uc.reg_read(self.registers['cs']) * 16
                  + uc.reg_read(self.registers['ip']))
            if getattr(self.machine, 'cpu_engine', 'unicorn') == 'interpreter':
                pc -= 5
            if address != BLER_COUNT or pc != 0xa9881:
                return  # Ignore initialization/reset and flag-consume writes.
        kind = 'pending_error' if address == ERROR_FLAG else 'bler_increment'
        context = self.context()
        phase = context['phase']
        key = f'{phase}:{kind}'
        self.counts[key] += 1
        if self.counts[key] > self.limit:
            return
        registers = {name: uc.reg_read(reg) for name, reg in self.registers.items()}
        raw_pc = registers['cs'] * 16 + registers['ip']
        # The interpreter has decoded the operand before _store invokes a
        # hook; Unicorn instead reports the start of the writing instruction.
        writer_pc = raw_pc - 5 if getattr(self.machine, 'cpu_engine', 'unicorn') == 'interpreter' else raw_pc
        verified_writer = writer_pc in (0xb4c8a, 0xb4cb2, 0xa9881)
        ds = registers['ds'] * 16
        cells = {f'{offset:04x}': int.from_bytes(uc.mem_read(ds + offset, 2), 'little')
                 for offset in CELLS}
        core = self.machine.mailbox.core
        event = {
            **context, 'kind': kind, 'write_address': address, 'write_size': size,
            'write_value': value, 'instructions': self.machine.instructions,
            'cpu_retired': getattr(uc, 'retired', None),
            'timer_ticks': self.machine.timer_ticks, 'registers': registers,
            'pc': writer_pc if verified_writer else raw_pc,
            'hook_pc': raw_pc, 'writer_pc_verified': verified_writer, 'cells': cells,
            'bler_before_write': int.from_bytes(uc.mem_read(BLER_COUNT, 4), 'little'),
            'stack_hex': bytes(uc.mem_read(registers['ss'] * 16 + registers['sp'], 32)).hex(),
            'native_clock': (self.machine._native_io.clock_stats()
                             if getattr(self.machine, '_native_io', None) else None),
            'dsp': core.state() if core else None,
            'dsp_lanes': core.io_port_stats(range(0x58, 0x5e)) if core else None,
        }
        # Save the already-emitted DSP bank history at the first rejection
        # of each phase. It is bounded by the native 8192-event ring and does
        # not enable per-instruction tracing or advance either processor.
        if kind == 'pending_error' and self.counts[key] == 1 and core and hasattr(core, 'io_events'):
            event['dsp_bank_history'] = core.io_events(limit=2048, ports=tuple(range(0x58, 0x5e)))
            event['dsp_io_event_total'] = core.io_event_total()
            event['dsp_data_history'] = core.data_events()[-2048:]
            event['dsp_hdlc_cells'] = {f'{a:04x}': core.data(a) for a in range(0x320, 0x32a)}
            if getattr(core, '_link_bit_capture', False):
                event['dsp_bit_capture'] = {
                    'pc': 0x9096, 'fields': ['instructions', 'cycles', 'acc', 'dp', 'carry', 'bit_count'],
                    'rows': core.pc_captures(),
                }
        # At rejection the ring pointers have not yet been reset. Preserve
        # the bytes exactly as the guest sees them, including received FCS.
        # The alternate reject branch has already cleared CF32 before
        # publishing D0B5; its writer PC, not that cleared bit, selects the ring.
        alternate = (writer_pc == 0xb4cb2 if kind == 'pending_error'
                     else bool(cells['cf32'] & 1))
        start = cells['caae' if alternate else 'caa6']
        length = cells['d070']
        low, high = (0x80, 0x100) if alternate else (0x8d00, 0xbf00)
        if low <= start < high and 0 < length <= min(high - low, 4096):
            count = min(length, high - start)
            es = registers['es'] * 16
            data = bytes(uc.mem_read(es + start, count))
            if count < length:
                data += bytes(uc.mem_read(es + low, length - count))
            event['receive_ring'] = {
                'segment': registers['es'], 'start': start,
                'length': length, 'hex': data.hex(),
                'crc16_raw': crc16_lapm(data),
                'crc_matches_firmware': crc16_lapm(data) == cells['cf2e'],
            }
        self.events.append(event)

    def status(self):
        return {'counts': dict(self.counts), 'events': list(self.events),
                'bler_count': int.from_bytes(self.machine.uc.mem_read(BLER_COUNT, 4), 'little'),
                'limit_per_phase_and_kind': self.limit}
