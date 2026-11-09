"""The C5x core's arithmetic against a reference written from SPRU056D.

Each case loads ACC, ACCB, PREG, TREG0/1/2 and ST0/ST1 from random values,
runs one instruction on a random data word, and compares ACC, ACCB, PREG,
OV, C, TC and any word stored with the reference model below. The model
follows the Execution and Status Bits sections of SPRU056D chapter 6.
"""
import random
import struct

import pytest

from courier_emu.dsp import NativeC5x

M32 = 0xFFFFFFFF

# Data words (DP 0).
ACC_HI, ACC_LO, TREG, PREG_HI, PREG_LO, ACCB_HI, ACCB_LO = range(0x60, 0x67)
ST0_IN, ST1_IN, OPERAND, OUT, ST0_OUT, ST1_OUT = 0x67, 0x68, 0x69, 0x6B, 0x70, 0x71


def s32(v):
    v &= M32
    return v - (1 << 32) if v & 0x80000000 else v


def s16(v):
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


class Model:
    def __init__(self, acc, accb, preg, treg, sxm, ovm, c, pm, data):
        self.acc, self.accb, self.preg = acc & M32, accb & M32, preg & M32
        self.treg0 = self.treg1 = treg & 0xFFFF
        self.sxm, self.ovm, self.c, self.pm = sxm, ovm, c, pm
        self.ov = 0
        self.tc = 0
        self.data = data & 0xFFFF
        self.out = None

    def ext(self, v):
        return (s16(v) if self.sxm else v & 0xFFFF) & M32

    def shifted_preg(self):
        p = s32(self.preg)
        return ((p, p << 1, p << 4, p >> 6)[self.pm]) & M32

    # The ALU: a 32-bit add or subtract with carry/borrow, OV, OVM.
    def add(self, a, b, carry_only_set=False):
        a, b = a & M32, b & M32
        full = a + b
        res = full & M32
        if carry_only_set:
            if full >> 32:
                self.c = 1
        else:
            self.c = full >> 32
        if (s32(a) + s32(b)) != s32(res):
            self.ov = 1
            if self.ovm:
                res = 0x7FFFFFFF if s32(a) + s32(b) > 0 else 0x80000000
        return res

    def sub(self, a, b, borrow_only_clear=False):
        a, b = a & M32, b & M32
        res = (a - b) & M32
        borrow = a < b
        if borrow_only_clear:
            if borrow:
                self.c = 0
        else:
            self.c = 0 if borrow else 1
        if (s32(a) - s32(b)) != s32(res):
            self.ov = 1
            if self.ovm:
                res = 0x7FFFFFFF if s32(a) - s32(b) > 0 else 0x80000000
        return res


def ref(name, m, k=0):
    d = m.data
    if name == "ADD":
        m.acc = m.add(m.acc, m.ext(d) << k)
    elif name == "ADD16":
        m.acc = m.add(m.acc, d << 16, True)
    elif name == "SUB":
        m.acc = m.sub(m.acc, m.ext(d) << k)
    elif name == "SUB16":
        m.acc = m.sub(m.acc, d << 16, True)
    elif name == "ADDC":
        # One sum: dma + C cannot wrap 32 bits.
        m.acc = m.add(m.acc, d + m.c)
    elif name == "SUBB":
        m.acc = m.sub(m.acc, d + (1 - m.c))
    elif name == "ADDS":
        m.acc = m.add(m.acc, d)
    elif name == "SUBS":
        m.acc = m.sub(m.acc, d)
    elif name == "ADDT":
        m.acc = m.add(m.acc, m.ext(d) << (m.treg1 & 15))
    elif name == "SUBT":
        m.acc = m.sub(m.acc, m.ext(d) << (m.treg1 & 15))
    elif name == "SUBC":
        alu = (m.acc - (d << 15)) & M32
        m.c = 0 if m.acc < (d << 15) else 1
        if (s32(m.acc) - (d << 15)) != s32(alu):
            m.ov = 1
        m.acc = ((alu << 1) | 1) & M32 if not alu & 0x80000000 else (m.acc << 1) & M32
    elif name == "LACC":
        m.acc = (m.ext(d) << k) & M32
    elif name == "LACT":
        m.acc = (m.ext(d) << (m.treg1 & 15)) & M32
    elif name == "LACL":
        m.acc = d
    elif name == "ZALR":
        m.acc = (d << 16) | 0x8000
    elif name == "AND":
        m.acc &= d
    elif name == "OR":
        m.acc |= d
    elif name == "XOR":
        m.acc ^= d
    elif name == "NORM":
        a = m.acc
        if a == 0:
            m.tc = 1
        elif ((a >> 31) ^ (a >> 30)) & 1 == 0:
            m.tc = 0
            m.acc = (a << 1) & M32
        else:
            m.tc = 1
    elif name == "SFL":
        m.c = m.acc >> 31
        m.acc = (m.acc << 1) & M32
    elif name == "SFR":
        m.c = m.acc & 1
        m.acc = ((s32(m.acc) >> 1) if m.sxm else (m.acc >> 1)) & M32
    elif name == "NEG":
        if m.acc == 0x80000000:
            m.ov = 1
            m.c = 0
            if m.ovm:
                m.acc = 0x7FFFFFFF
        else:
            m.acc = (-m.acc) & M32
            m.c = 1 if m.acc == 0 else 0
    elif name == "ABS":
        m.c = 0
        if m.acc == 0x80000000:
            m.ov = 1
            if m.ovm:
                m.acc = 0x7FFFFFFF
        elif m.acc & 0x80000000:
            m.acc = (-s32(m.acc)) & M32
    elif name == "ROL":
        c = m.c
        m.c = m.acc >> 31
        m.acc = ((m.acc << 1) | c) & M32
    elif name == "ROR":
        c = m.c
        m.c = m.acc & 1
        m.acc = (m.acc >> 1) | (c << 31)
    elif name == "CMPL":
        m.acc ^= M32
    elif name == "BSAR":
        m.acc = ((s32(m.acc) >> k) if m.sxm else (m.acc >> k)) & M32
    elif name == "SATL":
        n = m.treg1 & 15
        m.acc = ((s32(m.acc) >> n) if m.sxm else (m.acc >> n)) & M32
    elif name == "SATH":
        n = 16 * ((m.treg1 >> 4) & 1)
        m.acc = ((s32(m.acc) >> n) if m.sxm else (m.acc >> n)) & M32
    elif name == "ADDB":
        m.acc = m.add(m.acc, m.accb)
    elif name == "SBB":
        # SPRU056D 6-232: affects C only.
        m.c = 0 if m.acc < m.accb else 1
        m.acc = (m.acc - m.accb) & M32
    elif name == "CRGT":
        if s32(m.acc) > s32(m.accb):
            m.accb, m.c = m.acc, 1
        elif s32(m.acc) < s32(m.accb):
            m.acc, m.c = m.accb, 0
        else:
            m.c = 1
    elif name == "CRLT":
        if s32(m.acc) < s32(m.accb):
            m.accb, m.c = m.acc, 1
        elif s32(m.acc) > s32(m.accb):
            m.acc, m.c = m.accb, 0
        else:
            m.c = 0
    elif name == "SACH":
        m.out = ((m.acc << k) >> 16) & 0xFFFF
    elif name == "SACL":
        m.out = (m.acc << k) & 0xFFFF
    elif name == "MPY":
        m.preg = (s16(m.treg0) * s16(d)) & M32
    elif name == "MPYU":
        m.preg = (m.treg0 * d) & M32
    elif name == "MPYA":
        m.acc = m.add(m.acc, m.shifted_preg())
        m.preg = (s16(m.treg0) * s16(d)) & M32
    elif name == "MPYS":
        m.acc = m.sub(m.acc, m.shifted_preg())
        m.preg = (s16(m.treg0) * s16(d)) & M32
    elif name == "SQRA":
        m.acc = m.add(m.acc, m.shifted_preg())
        m.treg0 = d
        m.preg = (s16(d) * s16(d)) & M32
    elif name == "SQRS":
        m.acc = m.sub(m.acc, m.shifted_preg())
        m.treg0 = d
        m.preg = (s16(d) * s16(d)) & M32
    elif name == "PAC":
        m.acc = m.shifted_preg()
    elif name == "APAC":
        m.acc = m.add(m.acc, m.shifted_preg())
    elif name == "SPAC":
        m.acc = m.sub(m.acc, m.shifted_preg())
    elif name == "LTA":
        m.acc = m.add(m.acc, m.shifted_preg())
        m.treg0 = d
    elif name == "LTS":
        m.acc = m.sub(m.acc, m.shifted_preg())
        m.treg0 = d
    elif name == "LTP":
        m.acc = m.shifted_preg()
        m.treg0 = d
    elif name == "LTD":
        m.acc = m.add(m.acc, m.shifted_preg())
        m.treg0 = d
    elif name == "SPH":
        m.out = m.shifted_preg() >> 16
    elif name == "SPL":
        m.out = m.shifted_preg() & 0xFFFF
    else:
        raise KeyError(name)


# Opcodes (SPRU056D Tables 6-4 to 6-9); k is a shift or BSAR's count.
def opcode(name, k):
    simple = {
        "ADD16": 0x6100, "SUB16": 0x6500, "ADDC": 0x6000, "SUBB": 0x6400,
        "ADDS": 0x6200, "SUBS": 0x6600, "ADDT": 0x6300, "SUBT": 0x6700,
        "SUBC": 0x0A00, "LACT": 0x6B00, "LACL": 0x6900, "ZALR": 0x6800,
        "AND": 0x6E00, "OR": 0x6D00, "XOR": 0x6C00,
        "MPY": 0x5400, "MPYU": 0x5500, "MPYA": 0x5000, "MPYS": 0x5100,
        "SQRA": 0x5200, "SQRS": 0x5300, "LTA": 0x7000, "LTS": 0x7400,
        "LTP": 0x7100, "LTD": 0x7200,
    }
    acc_only = {
        "SFL": 0xBE09, "SFR": 0xBE0A, "NEG": 0xBE02, "ABS": 0xBE00,
        "ROL": 0xBE0C, "ROR": 0xBE0D, "CMPL": 0xBE01, "SATL": 0xBE5B,
        "SATH": 0xBE5A, "ADDB": 0xBE10, "SBB": 0xBE18, "CRGT": 0xBE1B,
        "CRLT": 0xBE1C, "PAC": 0xBE03, "APAC": 0xBE04, "SPAC": 0xBE05,
    }
    if name in simple:
        return [simple[name] | OPERAND]
    if name in acc_only:
        return [acc_only[name]]
    if name == "ADD":
        return [0x2000 | k << 8 | OPERAND]
    if name == "SUB":
        return [0x3000 | k << 8 | OPERAND]
    if name == "LACC":
        return [0x1000 | k << 8 | OPERAND]
    if name == "BSAR":
        return [0xBFE0 | (k - 1)]
    if name == "SACH":
        return [0x9800 | k << 8 | OUT]
    if name == "SACL":
        return [0x9000 | k << 8 | OUT]
    if name == "SPH":
        return [0x8D00 | OUT]
    if name == "SPL":
        return [0x8C00 | OUT]
    if name == "NORM":
        return [0xA0A0]          # NORM *+ (AR0)
    raise KeyError(name)


SETUP = [
    0xBC00,                      # LDP #0
    0x7300 | PREG_LO,            # LT PREG_LO
    0xC001,                      # MPY #1: PREG = sign-extended low word
    0x7500 | PREG_HI,            # LPH PREG_HI
    0x6A00 | ACCB_HI,            # LACC ACCB_HI,16
    0x6200 | ACCB_LO,            # ADDS ACCB_LO
    0xBE1E,                      # SACB
    0x6A00 | ACC_HI,             # LACC ACC_HI,16
    0x6200 | ACC_LO,             # ADDS ACC_LO
    0x7300 | TREG,               # LT TREG
    0x0E00 | ST0_IN,             # LST #0
    0x0F00 | ST1_IN,             # LST #1
]
TAIL = [0x8E00 | ST0_OUT, 0x8F00 | ST1_OUT]   # SST #0, SST #1


def run_case(name, k, acc, accb, preg, treg, sxm, ovm, c, pm, data):
    words = SETUP + opcode(name, k) + TAIL
    program = struct.pack(f"<{len(words)}H", *words)
    with NativeC5x.from_program(0, program, rebuild=False) as core:
        cells = {
            ACC_HI: acc >> 16, ACC_LO: acc & 0xFFFF, TREG: treg,
            PREG_HI: preg >> 16, PREG_LO: preg & 0xFFFF,
            ACCB_HI: accb >> 16, ACCB_LO: accb & 0xFFFF,
            # ST0: ARP 0, OV 0, OVM, bit 10 set, INTM 1, DP 0.
            ST0_IN: ovm << 11 | 1 << 10 | 1 << 9,
            # ST1: ARB 0, TC 0, SXM, C, ones in 8-5 and 3-2, PM.
            ST1_IN: sxm << 10 | c << 9 | 0x01E0 | 0x000C | pm,
            OPERAND: data, OUT: 0,
        }
        for address, value in cells.items():
            core.set_data(address, value & 0xFFFF)
        core.step(len(SETUP) + 1 + len(TAIL))
        state = core.state()
        st0, st1 = core.data(ST0_OUT), core.data(ST1_OUT)
        got = {
            "acc": state["acc"] & M32, "accb": state["accb"] & M32,
            "preg": state["preg"] & M32, "ov": st0 >> 12 & 1,
            "c": st1 >> 9 & 1, "tc": st1 >> 11 & 1,
        }
        out = core.data(OUT)
    m = Model(acc, accb, preg, treg, sxm, ovm, c, pm, data)
    ref(name, m, k)
    want = {"acc": m.acc, "accb": m.accb, "preg": m.preg, "ov": m.ov,
            "c": m.c, "tc": m.tc}
    if name != "NORM":
        got.pop("tc"), want.pop("tc")
    if m.out is not None:
        got["out"], want["out"] = out, m.out
    return got, want


NAMES = ["ADD", "ADD16", "SUB", "SUB16", "ADDC", "SUBB", "ADDS", "SUBS",
         "ADDT", "SUBT", "SUBC", "LACC", "LACT", "LACL", "ZALR", "AND", "OR",
         "XOR", "NORM", "SFL", "SFR", "NEG", "ABS", "ROL", "ROR", "CMPL",
         "BSAR", "SATL", "SATH", "ADDB", "SBB", "CRGT", "CRLT", "SACH",
         "SACL", "MPY", "MPYU", "MPYA", "MPYS", "SQRA", "SQRS", "PAC",
         "APAC", "SPAC", "LTA", "LTS", "LTP", "LTD", "SPH", "SPL"]

EDGES = [0, 1, 0x7FFF, 0x8000, 0xFFFF, 0x0001, 0x4000, 0xC000]
EDGES32 = [0, 1, 0x7FFFFFFF, 0x80000000, M32, 0x40000000, 0xC0000000,
           0x00008000, 0xFFFF8000, 0x3FFFFFFF]


def cases(name, n, seed):
    rnd = random.Random(f"{name}-{seed}")
    for _ in range(n):
        def w32():
            return rnd.choice(EDGES32) if rnd.random() < 0.3 else rnd.getrandbits(32)

        def w16():
            return rnd.choice(EDGES) if rnd.random() < 0.3 else rnd.getrandbits(16)
        k = rnd.randrange(1, 17) if name == "BSAR" else rnd.randrange(8 if name in ("SACH", "SACL") else 16)
        yield (name, k, w32(), w32(), w32(), w16(), rnd.getrandbits(1),
               rnd.getrandbits(1), rnd.getrandbits(1), rnd.randrange(4), w16())


@pytest.fixture(scope="module", autouse=True)
def built():
    from courier_emu.dsp import build_library
    build_library()


@pytest.mark.parametrize("name", NAMES)
def test_matches_spru056d(name):
    bad = []
    for case in cases(name, 150, 1):
        got, want = run_case(*case)
        if got != want:
            bad.append((case, got, want))
    assert not bad, f"{len(bad)} of 150 differ; first: {bad[0]}"
