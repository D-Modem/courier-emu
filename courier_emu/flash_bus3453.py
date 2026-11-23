"""Read-only 3453 flash bus, including EB chip selects and autoselect.

GCS2 drives flash A19: its active-low output replaces the CPU's A19.
800A selects the lower half; 000E ignores the stop address and exposes
low flash through the upper-half alias used by the DSP downloader.
No captured image is ever programmed by this model.
"""
from dataclasses import dataclass, field


@dataclass
class FlashBus3453:
    contents: bytes
    manufacturer: int
    device: int
    registers: dict = field(default_factory=dict)
    mode: str = 'array'
    unlock: int = 0
    autoselects: int = 0
    bank_changes: int = 0

    def __post_init__(self):
        if len(self.contents) != 0x100000:
            raise ValueError('3453 flash bus requires one MiB')
        defaults = {0xFF88: 0, 0xFF8A: 0x800A,
                    0xFFA0: 0, 0xFFA2: 0x400A,
                    0xFFA4: 0x4000, 0xFFA6: 0xFFCE}
        defaults.update(self.registers)
        self.registers = defaults

    def selected(self, address, start_register):
        start = self.registers[start_register]
        stop = self.registers[start_register + 2]
        return (bool(stop & 8) and bool(stop & 2)
                and address >= (start & 0xFFC0) << 4
                and (bool(stop & 4) or address < (stop & 0xFFC0) << 4))

    def offset(self, address):
        if not 0 <= address < 0x100000:
            return None
        if 0xFF00 <= address <= 0xFFFF:  # Relocated peripheral block wins.
            return None
        if self.selected(address, 0xFFA0) or not self.selected(address, 0xFFA4):
            return None
        high = 0 if self.selected(address, 0xFF88) else 0x80000
        return (address & 0x7FFFF) | high

    def write_register(self, address, size, value):
        register = address & ~1
        if register not in self.registers or size not in (1, 2):
            return False
        old = self.registers[register]
        if size == 1:
            shift = (address & 1) * 8
            value = (old & ~(0xFF << shift)) | ((value & 0xFF) << shift)
        value &= 0xFFFF
        if value == old:
            return False
        self.registers[register] = value
        self.bank_changes += 1
        return True

    def read_register(self, address, size):
        register = address & ~1
        if register not in self.registers or size not in (1, 2):
            return None
        return (self.registers[register] >> (8 * (address & 1))) & ((1 << (size * 8)) - 1)

    def read(self, address, size):
        offset = self.offset(address)
        if offset is None:
            return None
        if self.mode == 'autoselect':
            result = bytearray()
            for index in range(size):
                at = (offset + index) & 0xFFFF
                word = self.manufacturer if at < 2 else self.device if at < 4 else 0
                result.append((word >> (8 * (at & 1))) & 0xFF)
            return bytes(result)
        # A word straddling the half-bank boundary must decode both cycles.
        if (address & 0x7FFFF) + size > 0x80000:
            offsets = [self.offset(address + index) for index in range(size)]
            if any(value is None for value in offsets):
                return None
            return bytes(self.contents[value] for value in offsets)
        return self.contents[offset:offset + size]

    def write(self, address, size, value):
        offset = self.offset(address)
        if offset is None:
            return False
        command = value & 0xFF
        at = offset & 0xFFFF
        if command in (0xF0, 0xFF):
            self.mode = 'array'
            self.unlock = 0
        elif self.unlock == 2:
            self.unlock = 0
            if command == 0x90:
                self.mode = 'autoselect'
                self.autoselects += 1
            else:
                raise ValueError('3453 flash programming/erase is not supported (read-only image)')
        elif at == 0xAAAA and command == 0xAA:
            self.unlock = 1
        elif at == 0x5554 and command == 0x55 and self.unlock == 1:
            self.unlock = 2
        else:
            # RAM-size probes write ordinary patterns into non-RAM addresses.
            # An unarmed flash part ignores them, rather than programming.
            self.unlock = 0
        return True

    def array_views(self):
        """Executable flash spans; RAM content must survive select changes."""
        start = (self.registers[0xFFA4] & 0xFFC0) << 4
        # Captured firmware selects on 64 KiB boundaries. Iterate at the EB's
        # actual 1 KiB granularity so copy/update windows work as well.
        for address in range(start, 0x100000, 0x400):
            offset = self.offset(address)
            if offset is not None:
                yield address, self.contents[offset:offset+0x400]

    def status(self):
        return {'manufacturer': f'{self.manufacturer:02X}', 'device': f'{self.device:04X}',
                'mode': self.mode, 'autoselects': self.autoselects,
                'bank_changes': self.bank_changes, 'read_only': True,
                'registers': {f'{k:04X}': f'{v:04X}' for k, v in self.registers.items()}}
