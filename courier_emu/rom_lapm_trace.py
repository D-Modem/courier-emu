"""Passive, bounded, signature-checked original-firmware LAPM observations.

TX records are CPU-staged headers, not proof of transmission on wire. RX
records distinguish the firmware CRC gate from an independently checked ring.
No guest memory, registers, scheduling, or interrupt state is modified.
"""
from collections import Counter
from hashlib import sha256

from .v120 import crc16

SIGNATURES = {
    0x907b3: bytes.fromhex('813eaf02b8f0'),
    0x8c91e: bytes.fromhex('c606c60201'),
    0x8cb26: bytes.fromhex('c606c60201'),
    0x8c741: bytes.fromhex('e861fbb400c6067f0b01c606640b00b005'),
}
LAYOUTS = {
    '403': dict(signatures=SIGNATURES, rx_pc=0x907b3, tx_pcs=(0x8c91e, 0x8cb26), ram=0,
                state=0xb47, state_size=0x49, reload=0xaef, flow=0x231, auxiliary=0x3cf,
                rx_read=0x258, rx_write=0x256, queue=0x3be, length=0x3bc, alternate=0x2b3,
                crc=0x2af, starts=(0x25a, 0x262), rings=((0xb000, 0xc000), (0x1a80, 0x1b00)),
                tx_header=0xaf5, tx_length=0x2c1, payload_pointer=0x24e, payload_length=0x2c2,
                flow_states=(0xb64, 0xb7e, 0xb7f)),
    'imodem': dict(signatures={0xb5268: bytes.fromhex('813e2ecfb8f0'),
                              0xaed74: bytes.fromhex('c60640cf01'),
                              0xaef59: bytes.fromhex('c60640cf01'),
                              0xb4c2b: bytes.fromhex('c6069fe501c60663ca01')},
                   rx_pc=0xb5268, tx_pcs=(0xaed74, 0xaef59), ram=0x2600,
                   state=0xe57e, state_size=0x48, reload=0xe537, flow=0xca63, auxiliary=0xd083,
                   rx_read=0xcaa4, rx_write=0xcaa2, queue=0xd072, length=0xd070,
                   alternate=0xcf32, crc=0xcf2e, starts=(0xcaa6, 0xcaae),
                   rings=((0x8d00, 0xbf00), (0x80, 0x100)), tx_header=0xe53d,
                   tx_length=0xcf41, payload_pointer=0xca9a, payload_length=0xcf42,
                   flow_states=(0xe59f, 0xe5b2, 0xe5b3)),
}


def decode_header(data):
    """Decode extended LAPM controls, retaining raw address and control octets."""
    if len(data) < 2:
        return {'type': 'short'}
    address, control = data[:2]
    result = {'address': address, 'control': control}
    if address not in (1, 3):
        return {**result, 'type': 'unclassified-address'}
    if not control & 1:
        result.update(type='I', ns=control >> 1)
    elif control & 3 == 1:
        result['type'] = {0: 'RR', 1: 'RNR', 2: 'REJ', 3: 'SREJ'}[(control >> 2) & 3]
    else:
        result.update(type='U', u_control=control & ~0x10, pf=(control >> 4) & 1)
        return result
    if len(data) >= 3:
        result.update(nr=data[2] >> 1, pf=data[2] & 1)
    else:
        result['truncated_control'] = True
    return result


class RomLapmTrace:
    def __init__(self, machine, *, packet_limit=8192, state_limit=32768, window_frames=1500,
                 profile='403', line_getter=None, online_getter=None):
        if min(packet_limit, state_limit, window_frames) < 1:
            raise ValueError('trace limits must be positive')
        self.machine, self.profile = machine, profile
        self.layout = LAYOUTS[profile]
        self.line_getter = line_getter or (lambda: machine.dsp_bridge.line if machine.dsp_bridge else None)
        self.online_getter = online_getter or (lambda: machine.online_mode)
        self.packet_limit, self.state_limit, self.window_frames = packet_limit, state_limit, window_frames
        self.origin_frame = None
        self.packets, self.states = [], []
        self.counts = Counter()
        if machine.cpu_engine == 'interpreter':
            from . import x86_interpreter as api
            code, write = api.UC_HOOK_CODE, api.UC_HOOK_MEM_WRITE
        else:
            from unicorn import UC_HOOK_CODE as code, UC_HOOK_MEM_WRITE as write
            from unicorn import x86_const as api
        self.regs = {name: getattr(api, 'UC_X86_REG_' + name.upper())
                     for name in ('cs', 'ip', 'ds', 'es')}
        uc, layout = machine.uc, self.layout
        for pc, signature in layout['signatures'].items():
            if bytes(uc.mem_read(pc, len(signature))) != signature:
                raise ValueError(f'unsupported {profile} LAPM signature at {pc:05x}')
        self.hooks = [uc.hook_add(code, self.on_code, None, pc, pc)
                      for pc in (layout['rx_pc'], *layout['tx_pcs'])]
        base = layout['ram'] * 16
        ranges = [(layout['state'], layout['state'] + layout['state_size'] - 1)]
        ranges += [(layout[key], layout[key]) for key in ('flow', 'auxiliary', 'reload')]
        self.hooks += [uc.hook_add(write, self.on_write, None, base + low, base + high)
                       for low, high in ranges]

    def active(self):
        if not self.online_getter():
            return False
        line = self.line_getter()
        if line is None:
            return False
        frame = line.frames
        if self.origin_frame is None:
            self.origin_frame = frame
        return self.origin_frame <= frame < self.origin_frame + self.window_frames

    @staticmethod
    def word(uc, base, offset):
        return int.from_bytes(uc.mem_read(base + offset, 2), 'little')

    def context(self, uc):
        m, layout = self.machine, self.layout
        ds = uc.reg_read(self.regs['ds'])
        base = ds * 16
        # RAM semantics remain raw; N(S)/N(R) labels come from observed headers.
        return {'cpu_instructions': m.instructions, 'cpu_retired': getattr(uc, 'retired', None),
                'line_frame': self.line_getter().frames, 'ds': ds, 'es': uc.reg_read(self.regs['es']),
                'state_base': layout['state'],
                'state_hex': bytes(uc.mem_read(base + layout['state'], layout['state_size'])).hex(),
                'timer_reload': bytes(uc.mem_read(base + layout['reload'], 1))[0],
                'flow_flags': bytes(uc.mem_read(base + layout['flow'], 1))[0],
                'auxiliary_flags': bytes(uc.mem_read(base + layout['auxiliary'], 1))[0],
                'rx_read': self.word(uc, base, layout['rx_read']),
                'rx_write': self.word(uc, base, layout['rx_write']),
                'rx_queue_hex': bytes(uc.mem_read(base + layout['queue'], 2)).hex()}

    def on_code(self, uc, address, size, user_data):
        if not self.active():
            return
        layout = self.layout
        if uc.reg_read(self.regs['ds']) != layout['ram']:
            self.counts['unexpected_ds_packets_excluded'] += 1
            return
        kind = 'rx_crc_gate' if address == layout['rx_pc'] else 'tx_staged'
        self.counts[kind] += 1
        if len(self.packets) >= self.packet_limit:
            self.counts['packets_dropped_at_limit'] += 1
            return
        event = dict(kind=kind, pc=address, **self.context(uc))
        base, segment = event['ds'] * 16, event['es'] * 16
        if kind == 'rx_crc_gate':
            length = self.word(uc, base, layout['length'])
            alternate = bytes(uc.mem_read(base + layout['alternate'], 1))[0] & 1
            start = self.word(uc, base, layout['starts'][alternate])
            low, high = layout['rings'][alternate]
            residue = self.word(uc, base, layout['crc'])
            event.update(length_with_fcs=length, ring_start=start, alternate=bool(alternate),
                         firmware_crc=residue, firmware_crc_valid=residue == 0xf0b8)
            if low <= start < high and 3 <= length <= min(high - low, 4096):
                count = min(length, high - start)
                data = bytes(uc.mem_read(segment + start, count))
                if count < length:
                    data += bytes(uc.mem_read(segment + low, length - count))
                event.update(ring_crc=crc16(data), ring_crc_matches_firmware=crc16(data) == residue,
                             header_hex=data[:8].hex(), frame_sha256=sha256(data).hexdigest(),
                             decoded=decode_header(data[:-2]))
            else:
                event['invalid_ring_bounds'] = True
        else:
            length = bytes(uc.mem_read(base + layout['tx_length'], 1))[0]
            data = bytes(uc.mem_read(segment + layout['tx_header'], min(length, 32)))
            event.update(header_length=length, header_hex=data.hex(), decoded=decode_header(data),
                         payload_pointer=self.word(uc, base, layout['payload_pointer']),
                         payload_length=self.word(uc, base, layout['payload_length']))
        self.packets.append(event)

    def on_write(self, uc, access, address, size, value, user_data):
        if not self.active():
            return
        layout = self.layout
        if uc.reg_read(self.regs['ds']) != layout['ram']:
            self.counts['unexpected_ds_writes_excluded'] += 1
            return
        offset = address - layout['ram'] * 16
        old = int.from_bytes(uc.mem_read(address, size), 'little')
        if old == value:
            return
        self.counts['state_change'] += 1
        if len(self.states) >= self.state_limit:
            self.counts['states_dropped_at_limit'] += 1
            return
        pc = uc.reg_read(self.regs['cs']) * 16 + uc.reg_read(self.regs['ip'])
        self.states.append(dict(pc_observed=pc, address=address, offset=offset, size=size,
                                old=old, value=value, **self.context(uc)))

    def status(self):
        line = self.line_getter()
        return {'signature_verified': True, 'profile': self.profile,
                'origin_line_frame': self.origin_frame, 'window_line_frames': self.window_frames,
                'line_frame_samples': getattr(line, 'frame_samples', 160),
                'state_base': self.layout['state'], 'flow_offset': self.layout['flow'],
                'flow_state_offsets': list(self.layout['flow_states']),
                'packet_limit': self.packet_limit, 'state_limit': self.state_limit,
                'counts': dict(self.counts), 'packets': list(self.packets), 'states': list(self.states),
                'tx_semantics': 'CPU-staged header, not proof of wire transmission',
                'state_write_semantics': 'pre-write values; pc_observed may follow the writer instruction',
                'timestamp_semantics': 'service/line-frame observations, not interpolated physical event times'}
