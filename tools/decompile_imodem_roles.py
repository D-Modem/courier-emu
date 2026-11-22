"""Audit Ie030002 S58 packing and the original asymmetric INFO0 gate.

These are isolated executions of original instructions with controlled inputs.
They do not patch a live call or demonstrate a complete client datapump.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct

from courier_emu import x86_interpreter as x86
from courier_emu.dsp import NativeC5x
from courier_emu.nac import NacImage
from tools.imodem_x2_map import V90_IMAGES


ROOT = Path(__file__).resolve().parents[1]
IMAGE = ROOT / 'Ie030002.nac'


def capability_matrix(image=IMAGE):
    base, blob = NacImage.load(image).flatten()
    core = x86.Uc(x86.UC_ARCH_X86, x86.UC_MODE_16)
    core.mem_map(0, 0x100000)
    core.mem_write(base, blob)
    core.reg_write(x86.UC_X86_REG_DS, 0x2600)
    core.reg_write(x86.UC_X86_REG_CS, 0xA400)
    reached = []

    def stop_at_send(uc, address, size, user):
        reached.append(address)
        uc.emu_stop()

    core.hook_add(x86.UC_HOOK_CODE, stop_at_send, begin=0xB2833, end=0xB2833)
    results = []
    for s58 in range(256):
        reached.clear()
        core.mem_write(0x331B5, bytes([s58]))
        # Output of the common S54/S56 builder in the full-rate context.
        core.reg_write(x86.UC_X86_REG_BX, 0x21FF)
        core.reg_write(x86.UC_X86_REG_IP, 0xE7FD)
        core.emu_start(0xB27FD, 0, count=100)
        if not reached:
            raise RuntimeError('S58 builder did not reach its original tag-70 send')
        payload = core.reg_read(x86.UC_X86_REG_BX)
        results.append({'s58': s58, 'tag70': f'{payload:04x}',
                        'server_capability': bool(payload & 0x1000),
                        'symmetric_capability': bool(payload & 0x0800)})
    return results


def info0_gate_matrix(image=IMAGE):
    _, blob = NacImage.load(image).flatten()
    # Original packed INFO0 words. The requested-client pair matches the
    # live caller/answerer INFO0 direction; the other contexts isolate gates.
    contexts = [('client/server', 0x12FF, 0x18FE),
                ('server/client', 0x1AFE, 0x10FF),
                ('server/server', 0x1AFE, 0x18FE),
                ('both symmetric', 0x1EFE, 0x1EFF)]
    destinations = {0x95CA: 'asymmetric receiver setup',
                    0x965C: 'drop x2', 0x958F: 'symmetric setup'}
    results = []
    for name, local, remote in contexts:
        for answer_role in (0, 1):
            off, count, origin = V90_IMAGES[5]
            with NativeC5x.from_program(origin, blob[off:off + 2 * count]) as core:
                for index in (6, 11):
                    off, count, origin = V90_IMAGES[index]
                    core.load_program(blob[off:off + 2 * count], origin)
                for address, value in {0x039F: 0x8462, 0x006F: 0x41 | answer_role * 2,
                                       0xFEF0: local, 0xF6A0: remote, 0xFFDC: 0,
                                       0xFFDE: 7, 0x78: 0xBD0, 0x79: 0xBD0}.items():
                    core.set_data(address, value)
                core.load_program(struct.pack('<5H', 0xBC07, 0x8B89, 0x7A80,
                                              0x9596, 0x8B00), 0x7C00)
                core.set_pc(0x7C00)
                for _ in range(1000):
                    if core.pc() in destinations:
                        break
                    core.step(1)
                else:
                    raise RuntimeError(f'INFO0 gate did not terminate: {core.state()}')
                results.append({'context': name, 'answer_role': answer_role,
                                'local_info0': f'{local:04x}', 'remote_info0': f'{remote:04x}',
                                'pc': f'{core.pc():04x}', 'branch': destinations[core.pc()],
                                'ffde': f'{core.data(0xFFDE):04x}'})
    return results


def asymmetric_setup_matrix(image=IMAGE):
    """Execute both scheduled continuations, including their real POP/RET.

    8cbb installs the CALL return address as the next scheduler callback;
    treating it as an ordinary returning function incorrectly runs through
    the receiver wait and makes timeout recovery look immediate.
    """
    _, blob = NacImage.load(image).flatten()
    results = []
    for orientation, local, remote in [('client/server', 0x12FF, 0x18FE),
                                       ('server/client', 0x1AFE, 0x10FF)]:
        for answer_role in (0, 1):
            off, count, origin = V90_IMAGES[5]
            with NativeC5x.from_program(origin, blob[off:off + 2 * count]) as core:
                for index in (6, 11):
                    off, count, origin = V90_IMAGES[index]
                    core.load_program(blob[off:off + 2 * count], origin)
                for address, value in {0x039F: 0x8462, 0x006F: 0x41 | answer_role * 2,
                                       0xFEF0: local, 0xF6A0: remote,
                                       0x78: 0xBD0, 0x79: 0xBD0, 0x032B: 0x0200,
                                       0x03CB: 0x55AA}.items():
                    core.set_data(address, value)

                def run_driver(words, stop):
                    core.load_program(struct.pack(f'<{len(words)}H', *words), 0x7C00)
                    core.set_pc(0x7C00)
                    for _ in range(200):
                        if core.pc() == stop:
                            return
                        core.step(1)
                    raise RuntimeError(f'Asymmetric setup did not yield: {core.state()}')

                # 95ca POP belongs to the outer INFO0 caller, already audited
                # by info0_gate_matrix. Start at its following instruction.
                run_driver([0xBC07, 0x8B89, 0xBF09, 0xFEF0,
                            0x7A80, 0x95CB, 0x8B00], 0x7C06)
                first_callback = core.data(0x6D)
                delay = core.data(0x6E)
                if first_callback != 0x95DD:
                    raise RuntimeError('Unexpected first asymmetric continuation')
                run_driver([0xBC07, 0x7A80, first_callback, 0x8B00], 0x7C03)
                results.append({'context': orientation, 'answer_role': answer_role,
                                'initial_callback': f'{first_callback:04x}',
                                'initial_delay': delay,
                                'wait_callback': f'{core.data(0x6D):04x}',
                                'receiver_bits': core.data(0x0322),
                                'receiver_buffer': f'{core.data(0x0324):04x}',
                                'tone_callback': f'{core.data(0x039A):04x}',
                                'transmit_script_before': '55aa',
                                'transmit_script_after': f'{core.data(0x03CB):04x}',
                                'classifier': f'{core.data(0x039F):04x}'})
    return results


def asymmetric_wait_matrix(image=IMAGE):
    """Audit the computed return that skips the fallback branch while waiting."""
    _, blob = NacImage.load(image).flatten()
    results = []
    for counter in (0, 0x11C0, 0xBB80, 0xBB81, 0xFFFF):
        off, count, origin = V90_IMAGES[5]
        with NativeC5x.from_program(origin, blob[off:off + 2 * count]) as core:
            off, count, origin = V90_IMAGES[11]
            core.load_program(blob[off:off + 2 * count], origin)
            core.set_data(0x031A, counter)
            core.load_program(struct.pack('<5H', 0xBC07, 0x8B89, 0x7A80,
                                          0x95ED, 0x8B00), 0x7C00)
            core.set_pc(0x7C00)
            for _ in range(30):
                if core.pc() in (0x95EF, 0x95F1):
                    break
                core.step(1)
            else:
                raise RuntimeError(f'Unexpected asymmetric wait return: {core.state()}')
            results.append({'counter': counter, 'pc': f'{core.pc():04x}',
                            'action': 'fallback' if core.pc() == 0x95EF else 'receive marker'})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    image = NacImage.load(IMAGE)
    base, blob = image.flatten()
    import capstone
    dis = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_16)
    (args.output / 's58-builder.asm').write_text('\n'.join(
        f'{i.address:05x}  {i.bytes.hex():20} {i.mnemonic:8} {i.op_str}'
        for start, end in [(0xB27C5, 0xB2841), (0xB2841, 0xB287B)]
        for i in dis.disasm(blob[start-base:end-base], start)) + '\n')
    _, blob = image.flatten()
    from tools.c5x_disasm import disassemble
    program = [0] * 65536
    for index in (5, 6, 11):
        off, count, origin = V90_IMAGES[index]
        program[origin:origin + count] = struct.unpack_from(f'<{count}H', blob, off)
    # Ie030002's resident uses (tag - 75h) + 894Ah. The older
    # IM020104 table is relocated; do not reuse its 882Bh base here.
    dispatch = {f'{tag:02x}': f'{program[0x88D5 + tag]:04x}' for tag in (0x70, 0x71, 0x72)}
    if dispatch != {'70': '926d', '71': '9299', '72': '9283'}:
        raise RuntimeError(f'Unexpected command dispatch for this image: {dispatch}')
    (args.output / 'tag70-handler.asm').write_text('\n'.join(
        f'{i.pc:04x}  {" ".join(f"{w:04x}" for w in i.words):14} {i.text}'
        for i in disassemble(program, 0x926D, 0x9283)) + '\n')
    (args.output / 'asymmetric-gate.asm').write_text('\n'.join(
        f'{i.pc:04x}  {" ".join(f"{w:04x}" for w in i.words):14} {i.text}'
        for i in disassemble(program, 0x9596, 0x95F1)) + '\n')
    report = {'image': IMAGE.name, 'nac_sha256': hashlib.sha256(IMAGE.read_bytes()).hexdigest(),
              'controlled_v34_base': '21ff', 's58_cases': capability_matrix(),
              'dispatch_table_base': '88d5', 'host_dispatch': dispatch,
              'info0_cases': info0_gate_matrix(),
              'asymmetric_setup_cases': asymmetric_setup_matrix(),
              'asymmetric_wait_cases': asymmetric_wait_matrix(),
              'scope': 'S58 packing, INFO0 gate and scheduled receiver setup; no full client-mode claim.'}
    (args.output / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Executed 256 S58 builders, 8 INFO0 gates, 4 scheduled setups and 5 wait boundaries.')


if __name__ == '__main__':
    main()
