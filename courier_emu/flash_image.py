"""Captured 3453 1 MiB flash and split ATXMODEM bootmodem images.

Flash offsets are not always CPU addresses: bootmodem reads its low flash
through the 80000..BFFFF alias while keeping working RAM at address zero.
"""
from dataclasses import dataclass, replace
from pathlib import Path
from hashlib import sha256
import struct

from .xmf import XmfImage, XmfFormatError

FLASH_SIZE = 0x100000
BOOT_TRANSFER_SIZE = 0x44000
MAIN_START, MAIN_END = 0x40000, 0xF8000
SETTINGS_START, SETTINGS_END = 0xF8000, 0xFC000
BOOT_SUPERVISOR = 0x17BA0
RESET_LOADER_SHA256 = '497fa0bcc86a816d9c52bd93ebc8e340c8750c0910cfbb7034798373e1f5674d'


def assemble_flash(boot: bytes, normal: bytes, settings: bytes) -> bytes:
    if len(boot) != BOOT_TRANSFER_SIZE:
        raise ValueError('bootmodem transfer must be 272 KiB')
    if len(normal) != MAIN_END - MAIN_START:
        raise ValueError('normal firmware must be 736 KiB')
    if len(settings) != SETTINGS_END - SETTINGS_START:
        raise ValueError('settings must be 16 KiB')
    data = boot[:0x40000] + normal + settings + boot[0x40000:]
    if not data.startswith(b'Courier V.Everything') or not normal.startswith(b'Courier V.Everything'):
        raise ValueError('missing Courier image headers')
    return data


@dataclass(frozen=True)
class CourierFlashImage(XmfImage):
    firmware_mode: str = 'normal'
    complete_flash: bool = True
    power_on: bool = False
    emulates_interrupts = True

    @classmethod
    def load(cls, path, mode=None, *, power_on=False):
        if power_on and mode is not None:
            raise XmfFormatError('power-on mode is selected by the guest loader, not --firmware-mode')
        source = Path(path)
        raw = source.read_bytes()
        complete = len(raw) == FLASH_SIZE
        if len(raw) == BOOT_TRANSFER_SIZE:
            if mode not in (None, 'bootmodem'):
                raise XmfFormatError('a bootmodem-only capture has no normal image')
            mode = 'bootmodem'
            raw = raw[:0x40000] + bytes([255]) * 0xBC000 + raw[0x40000:]
        elif not complete:
            raise XmfFormatError('expected a 272 KiB bootmodem transfer or 1 MiB flash')
        # Prepare the known recovery ABI while the loader runs. Normal flash
        # may be corrupt: only the guest CRC and ensuing bank entry select it.
        mode = 'bootmodem' if power_on else mode or 'normal'
        if mode not in ('normal', 'bootmodem'):
            raise XmfFormatError('unknown firmware mode')
        if not raw.startswith(b'Courier V.Everything'):
            raise XmfFormatError('missing low-flash bootmodem header')
        if raw[0x3FFF0:0x3FFF5] != bytes.fromhex('ea0f04ba17'):
            raise XmfFormatError('unrecognized bootmodem entry vector')
        if raw[0xFFFF0:0xFFFF8] != bytes.fromhex('fabaa4ffb80080ef'):
            raise XmfFormatError('unrecognized 3453 reset stub')
        if power_on and sha256(raw[0xFC000:]).hexdigest() != RESET_LOADER_SHA256:
            raise XmfFormatError('no verified power-on profile for this reset loader')
        if mode == 'bootmodem':
            supervisor = BOOT_SUPERVISOR
        else:
            if not raw[MAIN_START:].startswith(b'Courier V.Everything'):
                raise XmfFormatError('missing normal firmware header')
            entry = raw[0x402E0:0x402E5]
            if entry[0] != 0xEA or entry[1:3] != b'\x0f\x04':
                raise XmfFormatError('unrecognized normal supervisor entry vector')
            supervisor = struct.unpack_from('<H', entry, 3)[0] << 4
        if not raw[supervisor:supervisor+4].startswith(b'\xbd\x0b\x00\xe9'):
            raise XmfFormatError('missing supervisor entry signature')
        return cls(source.resolve(), raw, supervisor, 0x40F, mode, complete, power_on)

    @property
    def load_base(self):
        return 0

    @property
    def entry_segment(self):
        return 0xFFFF if self.power_on else self.supervisor_offset >> 4

    @property
    def entry_offset(self):
        return 0 if self.power_on else self.entry_offset_value

    @property
    def header(self):
        start = MAIN_START if self.firmware_mode == 'normal' else 0
        return self.data[start:start+0x200]

    @property
    def dsp(self):
        start = MAIN_START + 0x200 if self.firmware_mode == 'normal' else 0x200
        return self.data[start:self.supervisor_offset]

    def file_to_physical(self, offset):
        if not 0 <= offset < len(self.data):
            raise ValueError('file offset outside flash')
        return offset

    def physical_to_file(self, address):
        offset = self._source_offset(address)
        if not 0 <= offset < len(self.data):
            raise ValueError('address outside flash')
        return offset

    def _source_offset(self, physical):
        if self.firmware_mode == 'bootmodem' and 0x80000 <= physical < 0xC0000:
            return physical - 0x80000
        return physical

    def _valid_source_range(self, offset, length):
        if self.firmware_mode == 'normal':
            return MAIN_START + 0x200 <= offset and offset + length <= MAIN_END
        return 0x200 <= offset and offset + length <= BOOT_SUPERVISOR

    def select_mode(self, mode):
        if mode == 'normal':
            if not self.complete_flash:
                raise ValueError('bootmodem-only capture cannot switch to missing normal firmware')
            supervisor = struct.unpack_from('<H', self.data, 0x402E3)[0] << 4
        elif mode == 'bootmodem':
            supervisor = BOOT_SUPERVISOR
        else:
            raise ValueError('unknown firmware mode')
        return replace(self, supervisor_offset=supervisor, firmware_mode=mode, power_on=False)

    def memory_image(self):
        data = bytearray(self.data)
        # The bus, not the selected supervisor, controls flash aliases.
        # Low working RAM remains distinct from the immutable flash array.
        data[:0x10000] = bytes(0x10000)
        return bytes(data)

    def describe(self):
        return {'format': '3453-flash', 'path': str(self.path), 'sha256': self.digest,
                'firmware_mode': self.firmware_mode, 'complete_flash': self.complete_flash,
                'power_on': self.power_on,
                'entry': f'{self.entry_segment:04x}:{self.entry_offset:04x}',
                'dsp_program_segments': [s.describe() for s in self.dsp_segments()]}
