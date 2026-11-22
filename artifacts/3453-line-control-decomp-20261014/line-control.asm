; B/C 2.2.09 line-control disassembly
; DSP stage: resident + origin-zero library; later overlays excluded.
; BIT operands below are LSB-based indices emitted by c5x_disasm,
; not TI assembler BIT numbering. Interpret as (word >> index) & 1.
; Branches beyond a listed range are not decompiled here.

; DSP 1d6d..1d92: line-mode configuration; following words are a jump table
1d6d: ldp     #007
1d6e: lar     ar1, #7ea1
1d70: call    49d7, *
1d72: retd
1d73: lacb
1d74: sacl    @27
1d75: splk    @7c, #1d93
1d77: b       1d7b, *
1d79: splk    @7c, #1d9c
1d7b: smmr    @7a, #03a6
1d7d: call    1d6d, *
1d7f: call    1da5, *
1d81: retc    ntc
1d82: ldp     #000
1d83: opl     @6f, #4040
1d85: add     @7c
1d86: tblr    @7d
1d87: lacl    @7d
1d88: bacc
1d89: lacc    #00008047
1d8b: call    12ca, *
1d8d: lacl    #06
1d8e: call    12ca, *
1d90: ldp     #000
1d91: b       1dc9, *

; DSP 1da5..1dc8: capability selection
1da5: bit     1, @27
1da6: lacc    #00000000
1da8: retc    tc
1da9: bit     3, @27
1daa: lacl    #02
1dab: retc    tc
1dac: bit     5, @26
1dad: lacl    #03
1dae: retc    tc
1daf: bit     3, @26
1db0: lacl    #04
1db1: retc    tc
1db2: bit     2, @26
1db3: lacl    #05
1db4: retc    tc
1db5: bit     10, @27
1db6: lacl    #06
1db7: retc    tc
1db8: bit     12, @27
1db9: lacl    #07
1dba: retc    tc
1dbb: bit     6, @26
1dbc: lacl    #08
1dbd: ret
1dbe: smmr    @7a, #03ae
1dc0: ret
1dc1: apl     @6f, #efff
1dc3: lacl    @7a
1dc4: and     #00001000
1dc6: or      @6f
1dc7: sacl    @6f
1dc8: ret

; DSP 1de4..1f63: originate setup, detection qualification and protocol branches
1de4: lar     ar1, #77b7
1de6: bit     7, *
1de7: lar     ar1, #77b2
1de9: splk    *, #0000
1deb: xc      2, ntc
1dec: splk    *, #0001
1dee: lar     ar1, #7fe9
1df0: apl     *, #ffbf
1df2: smmr    @7a, #03a6
1df4: lacl    @7a
1df5: and     #00003200
1df7: or      #00000040
1df9: sacl    @6f
1dfa: bit     1, @7a
1dfb: splk    @6d, #1e45
1dfd: xc      2, tc
1dfe: splk    @6d, #1e02
1e00: b       1d6d, *
1e02: call    47db, *
1e04: call    4653, *
1e06: splk    @28, #01ed
1e08: splk    @2b, #0050
1e0a: call    14ab, *
1e0c: call    1e1a, *
1e0e: call    4670, *
1e10: splk    @2b, #0028
1e12: call    14ab, *
1e14: call    1e1a, *
1e16: call    4664, *
1e18: b       1e08, *
1e1a: popd    @7d
1e1b: bit     2, @2f
1e1c: bcnd    1e38, tc
1e1e: bit     4, @2f
1e1f: bcnd    1f0b, tc
1e21: bit     6, @2f
1e22: bcnd    1ece, tc
1e24: bit     3, @2f
1e25: bcnd    1e2d, tc
1e27: lacc    @2b
1e28: sub     #01
1e29: sacl    @2b
1e2a: retc    gt
1e2b: lacl    @7d
1e2c: bacc
1e2d: lacl    @22
1e2e: call    20e1, *
1e30: add     #01
1e31: sacl    @22
1e32: sub     #08
1e33: retc    lt
1e34: apl     @27, #fff7
1e36: b       1e3f, *
1e38: lacl    @20
1e39: call    20e1, *
1e3b: add     #01
1e3c: sacl    @20
1e3d: sub     #04
1e3e: retc    lt
1e3f: splk    @1a, #1173
1e41: splk    @28, #038f
1e43: call    14ab, *
1e45: bit     2, @2f
1e46: bcnd    1e5c, tc
1e48: bit     4, @2f
1e49: bcnd    1f0b, tc
1e4b: bit     5, @2f
1e4c: bcnd    1f17, tc
1e4e: bit     6, @2f
1e4f: bcnd    1ece, tc
1e51: bit     3, @2f
1e52: bcnd    1ee6, tc
1e54: bit     7, @2f
1e55: bcnd    1f23, tc
1e57: lacl    #00
1e58: sacl    @25
1e59: sacl    @21
1e5a: sacl    @23
1e5b: ret
1e5c: lacl    @20
1e5d: call    20e1, *
1e5f: add     #01
1e60: sacl    @20
1e61: sub     #3c
1e62: retc    lt
1e63: bit     0, @26
1e64: nop
1e65: xc      1, tc
1e66: bit     12, @2f
1e67: bcnd    1e78, tc
1e69: apl     @26, #fffe
1e6b: bit     5, @26
1e6c: bcnd    1e75, tc
1e6e: bit     8, @26
1e6f: bcnd    1e8b, tc
1e71: bit     3, @27
1e72: bcnd    1ea4, tc
1e74: ret
1e75: pop
1e76: b       61a3, *
1e78: opl     @2f, #4000
1e7a: call    4677, *
1e7c: call    47ed, *
1e7e: lar     ar1, #77b3
1e80: bit     0, *
1e81: cc      47e6, tc
1e83: call    4653, *
1e85: splk    @28, #01ed
1e87: lacc    #00001e4e
1e89: samm    @6d
1e8a: ret
1e8b: lacc    #00000d55
1e8d: call    0407, *
1e8f: splk    @28, #0199
1e91: lacl    #05
1e92: sacl    @24
1e93: call    14ab, *
1e95: call    1f3e, *
1e97: lacc    @24
1e98: sub     #01
1e99: sacl    @24
1e9a: retc    neq
1e9b: bit     15, @1f
1e9c: bcnd    1f01, tc
1e9e: bit     5, @26
1e9f: bcnd    1e75, tc
1ea1: bit     3, @27
1ea2: bcnd    1f01, ntc
1ea4: call    2c29, *
1ea6: splk    @4d, #2fca
1ea8: splk    @28, #0360
1eaa: call    14ab, *
1eac: call    1f3e, *
1eae: bit     15, @1f
1eaf: retc    ntc
1eb0: bit     6, @2f
1eb1: bcnd    1eca, tc
1eb3: bit     4, @2f
1eb4: bcnd    1f0b, tc
1eb6: bit     5, @2f
1eb7: bcnd    1f17, tc
1eb9: bit     3, @2f
1eba: retc    ntc
1ebb: lacc    @2b
1ebc: sub     #01
1ebd: sacl    @2b
1ebe: retc    neq
1ebf: bit     9, @2f
1ec0: bcnd    1ec5, tc
1ec2: lacl    #17
1ec3: call    14aa, *
1ec5: lacl    #3a
1ec6: call    12ca, *
1ec8: b       1ef6, *
1eca: lacl    #03
1ecb: samm    @6e
1ecc: b       1edd, *
1ece: lacl    @25
1ecf: call    20e1, *
1ed1: add     #01
1ed2: sacl    @25
1ed3: sub     #06
1ed4: retc    lt
1ed5: bit     3, @27
1ed6: retc    ntc
1ed7: call    2c29, *
1ed9: splk    @4d, #2fca
1edb: lacl    #10
1edc: samm    @6e
1edd: lar     ar1, #0288
1edf: lacl    *+
1ee0: sacl    @08
1ee1: lacl    *-
1ee2: sacl    @09
1ee3: pop
1ee4: b       2623, *
1ee6: lar     ar1, #029d
1ee8: lacl    @22
1ee9: call    20e1, *
1eeb: add     #01
1eec: sacl    @22
1eed: sub     #9b
1eee: bit     3, @27
1eef: bcnd    1ef4, ntc
1ef1: bit     8, @26
1ef2: bcnd    1ef5, ntc
1ef4: sub     *
1ef5: retc    lt
1ef6: pop
1ef7: bit     3, @26
1ef8: bcnd    3c37, tc
1efa: bit     2, @26
1efb: bcnd    3c66, tc
1efd: bit     6, @26
1efe: bcnd    4486, tc
1f00: push
1f01: splk    @1a, #1173
1f03: splk    @28, #038f
1f05: lacl    #00
1f06: sacl    @22
1f07: lacc    #00001e48
1f09: samm    @6d
1f0a: ret
1f0b: lacl    @21
1f0c: call    20e1, *
1f0e: add     #01
1f0f: sacl    @21
1f10: sub     #08
1f11: retc    lt
1f12: bit     12, @27
1f13: retc    ntc
1f14: pop
1f15: b       449c, *
1f17: lacl    @23
1f18: call    20e1, *
1f1a: add     #01
1f1b: sacl    @23
1f1c: sub     #08
1f1d: retc    lt
1f1e: bit     10, @27
1f1f: retc    ntc
1f20: pop
1f21: b       4a12, *
1f23: lacl    @0a
1f24: call    20e1, *
1f26: add     #01
1f27: sacl    @0a
1f28: sub     #4b
1f29: retc    lt
1f2a: bit     7, @26
1f2b: retc    ntc
1f2c: pop
1f2d: bit     9, @1f
1f2e: bcnd    4d30, ntc
1f30: push
1f31: call    14ab, *
1f33: lacl    @0a
1f34: sach    @0a
1f35: bit     7, @2f
1f36: retc    tc
1f37: add     #01
1f38: sacl    @0a
1f39: sub     #03
1f3a: retc    lt
1f3b: pop
1f3c: b       4d08, *
1f3e: bit     15, @1f
1f3f: retc    tc
1f40: lacl    @20
1f41: add     #01
1f42: sacl    @20
1f43: lacl    @2f
1f44: and     #00000048
1f46: bcnd    1f4c, neq
1f48: lacl    @2f
1f49: and     #00002004
1f4b: retc    neq
1f4c: opl     @1f, #8000
1f4e: splk    @2b, #0007
1f50: bit     8, @26
1f51: retc    tc
1f52: lacl    @20
1f53: sub     #61
1f54: retc    geq
1f55: splk    @2b, #009b
1f57: retd
1f58: opl     @2f, #0200
1f5a: ldp     #000
1f5b: splk    @6d, #1fa4
1f5d: ldp     #007
1f5e: splk    @26, #4000
1f60: splk    @27, #0008
1f62: b       21d7, *

; DSP 1f64..20e8: answer setup and handshake state machine
1f64: splk    @6d, #1f7c
1f66: lar     ar1, #7fe9
1f68: apl     *, #ffbf
1f6a: smmr    @7a, #03a6
1f6c: lacl    @7a
1f6d: and     #00003200
1f6f: or      #00000003
1f71: sacl    @6f
1f72: call    4673, *
1f74: call    1d6d, *
1f76: b       21d7, *
1f78: bit     13, @2f
1f79: bcnd    1fa0, tc
1f7b: ret
1f7c: bit     13, @2f
1f7d: bcnd    1fa4, tc
1f7f: bit     9, @2f
1f80: bcnd    1f93, tc
1f82: call    1f86, *
1f84: b       1fa0, *
1f86: bit     8, @2f
1f87: bcnd    20e1, ntc
1f89: lacl    @21
1f8a: call    20e1, *
1f8c: add     #01
1f8d: sacl    @21
1f8e: sub     #0a
1f8f: retc    neq
1f90: lacl    #4c
1f91: b       12ca, *
1f93: lacl    @23
1f94: call    20e1, *
1f96: add     #01
1f97: sacl    @23
1f98: sub     #0a
1f99: bcnd    1fa0, lt
1f9b: lacl    #4b
1f9c: call    12ca, *
1f9e: b       1fa4, *
1fa0: lacc    @2b
1fa1: sub     #01
1fa2: sacl    @2b
1fa3: retc    gt
1fa4: lacc    #00004aab
1fa6: call    0407, *
1fa8: splk    @28, #01d7
1faa: splk    @75, #0ca7
1fac: lacl    @27
1fad: and     #0000000a
1faf: xc      2, neq
1fb0: splk    @1a, #2595
1fb2: splk    @2b, #0064
1fb4: bit     0, @26
1fb5: bcnd    1fc0, ntc
1fb7: splk    @1a, #2572
1fb9: xc      2, eq
1fba: splk    @1a, #256e
1fbc: splk    @73, #06cf
1fbe: splk    @2b, #00fa
1fc0: lacl    @26
1fc1: and     #00004020
1fc3: bcnd    1fd0, neq
1fc5: bit     3, @27
1fc6: bcnd    206b, tc
1fc8: lacl    @26
1fc9: and     #0000004c
1fcb: bcnd    2027, neq
1fcd: bit     7, @26
1fce: bcnd    20c9, tc
1fd0: lacl    @2b
1fd1: sub     #32
1fd2: sacl    @0a
1fd3: call    14ab, *
1fd5: lacl    @2b
1fd6: subs    @0a
1fd7: bcnd    1feb, gt
1fd9: bit     0, @26
1fda: cc      46a4, tc
1fdc: lacc    #00001fdf
1fde: samm    @6d
1fdf: bit     5, @26
1fe0: bcnd    2015, tc
1fe2: bit     7, @2f
1fe3: bcnd    200b, tc
1fe5: bit     12, @2f
1fe6: cc      1fff, tc
1fe8: bit     6, @2f
1fe9: bcnd    1fef, tc
1feb: call    1f86, *
1fed: b       2015, *
1fef: lacl    @25
1ff0: add     #01
1ff1: sacl    @25
1ff2: sub     #05
1ff3: bcnd    2015, lt
1ff5: bit     3, @27
1ff6: bcnd    2015, ntc
1ff8: splk    @1a, #1173
1ffa: lacl    #03
1ffb: call    14aa, *
1ffd: b       204c, *
1fff: apl     @2f, #efff
2001: lacl    @24
2002: sub     #0a
2003: retc    geq
2004: bit     8, @26
2005: retc    ntc
2006: apl     @27, #fff7
2008: splk    @2b, #0001
200a: ret
200b: lacl    @24
200c: call    20e1, *
200e: add     #01
200f: sacl    @24
2010: sub     #02
2011: nop
2012: xc      2, eq
2013: opl     @2f, #1000
2015: lacc    @2b
2016: sub     #01
2017: sacl    @2b
2018: xc      2, eq
2019: splk    @1a, #1173
201b: add     #04
201c: retc    neq
201d: pop
201e: bit     5, @26
201f: bcnd    5ed0, tc
2021: push
2022: lacl    @26
2023: and     #0000004c
2025: bcnd    2068, eq
2027: splk    @2b, #0096
2029: call    424c, *
202b: splk    @28, #01dc
202d: lacl    #00
202e: call    14aa, *
2030: bit     4, @2f
2031: bcnd    203f, tc
2033: bit     14, @26
2034: bcnd    2039, tc
2036: bit     8, @2f
2037: bcnd    203f, tc
2039: bit     3, @2f
203a: bcnd    2050, tc
203c: bit     6, @2f
203d: bcnd    2043, tc
203f: call    20e1, *
2041: b       2064, *
2043: lacl    @25
2044: add     #01
2045: sacl    @25
2046: sub     #0a
2047: bcnd    2064, lt
2049: bit     3, @27
204a: bcnd    2064, ntc
204c: call    2c29, *
204e: b       2085, *
2050: lacl    @22
2051: call    20e1, *
2053: add     #01
2054: sacl    @22
2055: sub     #02
2056: bcnd    2064, lt
2058: lacl    #3a
2059: call    12ca, *
205b: pop
205c: bit     3, @26
205d: bcnd    3bc2, tc
205f: bit     2, @26
2060: bcnd    3bea, tc
2062: b       4477, *
2064: lacc    @2b
2065: sub     #01
2066: sacl    @2b
2067: retc    neq
2068: bit     3, @27
2069: bcnd    208c, ntc
206b: lacl    #00
206c: samm    @6e
206d: lar     ar1, #029e
206f: lacl    *
2070: sacl    @2b
2071: bcnd    208c, eq
2073: apl     @26, #fffe
2075: call    2c29, *
2077: splk    @4d, #2fc2
2079: splk    @28, #0368
207b: call    14ab, *
207d: bit     6, @2f
207e: bcnd    2088, ntc
2080: lacl    @25
2081: add     #01
2082: sacl    @25
2083: sub     #04
2084: retc    lt
2085: pop
2086: b       2630, *
2088: lacc    @2b
2089: sub     #01
208a: sacl    @2b
208b: retc    neq
208c: bit     12, @27
208d: bcnd    20ac, ntc
208f: lar     ar1, #029f
2091: lacl    *
2092: sacl    @2b
2093: bcnd    20ac, eq
2095: lacc    #00003aab
2097: call    0407, *
2099: splk    @28, #01cc
209b: call    14ab, *
209d: bit     4, @2f
209e: bcnd    20a8, ntc
20a0: lacl    @21
20a1: add     #01
20a2: sacl    @21
20a3: sub     #04
20a4: retc    lt
20a5: pop
20a6: b       4492, *
20a8: lacc    @2b
20a9: sub     #01
20aa: sacl    @2b
20ab: retc    neq
20ac: bit     10, @27
20ad: bcnd    20c6, ntc
20af: splk    @2b, #0096
20b1: call    4af7, *
20b3: splk    @28, #01ba
20b5: call    14ab, *
20b7: bit     5, @2f
20b8: bcnd    20c2, ntc
20ba: lacl    @23
20bb: add     #01
20bc: sacl    @23
20bd: sub     #04
20be: retc    lt
20bf: pop
20c0: b       4a90, *
20c2: lacc    @2b
20c3: sub     #01
20c4: sacl    @2b
20c5: retc    neq
20c6: bit     7, @26
20c7: bcnd    20de, ntc
20c9: lacc    #00004800
20cb: call    0407, *
20cd: splk    @2b, #0096
20cf: splk    @28, #038f
20d1: lacl    #00
20d2: call    14aa, *
20d4: lacc    @2b
20d5: sub     #01
20d6: sacl    @2b
20d7: retc    neq
20d8: pop
20d9: bit     9, @1f
20da: bcnd    4d08, tc
20dc: b       4d30, *
20de: lacl    #0b
20df: b       12ca, *
20e1: lar     ar0, #00
20e2: sar     ar0, @25
20e3: sar     ar0, @22
20e4: sar     ar0, @21
20e5: sar     ar0, @23
20e6: sar     ar0, @20
20e7: sar     ar0, @24
20e8: ret

; DSP 20e9..229c: monitor/answer receive processing and status messages
20e9: splk    @74, #03ce
20eb: splk    @76, #0014
20ed: splk    @75, #03b6
20ef: splk    @77, #0018
20f1: lacl    #00
20f2: sacl    @6d
20f3: sacl    @6e
20f4: ldp     #007
20f5: splk    @1b, #2127
20f7: splk    @1a, #1173
20f9: splk    @28, #038f
20fb: sacl    @2f
20fc: call    20e1, *
20fe: ldp     #005
20ff: lacl    #24
2100: sacl    @06
2101: dmov    @06
2102: sach    @00
2103: sach    @02
2104: splk    @04, #038e
2106: splk    @7b, #0001
2108: lar     ar1, #02a0
210a: rpt     #07
210b: sach    *+
210c: lar     ar1, #0358
210e: rpt     #13
210f: sach    *+
2110: lar     ar1, #0180
2112: rpt     #bf
2113: sach    *+
2114: ldp     #007
2115: apl     @2f, #7e04
2117: lar     ar1, #03b0
2119: rptz    #000f
211b: sach    *+
211c: lar     ar1, #01fa
211e: rpt     #05
211f: sach    *+
2120: lar     ar1, #0263
2122: sacl    *+
2123: sacl    *-
2124: lar     ar1, #8f
2125: sar     ar1, @2a
2126: ret
2127: splk    @04, #00e4
2129: call    243a, *
212b: call    3aec, *
212d: call    244a, *
212f: call    2432, *
2131: call    2459, *
2133: lar     ar1, @28
2134: lacc    *
2135: sacl    @14
2136: calld   0696, *
2138: lar     ar2, #03b0
213a: call    232f, *
213c: call    23df, *
213e: call    23c7, *
2140: call    2426, *
2142: call    23af, *
2144: call    23a3, *
2146: call    237b, *
2148: call    23d3, *
214a: call    23bb, *
214c: bit     14, @2f
214d: cc      4538, tc
214f: lacc    @14
2150: ldp     #005
2151: sacl    @14
2152: call    06a4, *
2154: cc      06f7, eq
2156: call    3b04, *
2158: ldp     #007
2159: lacl    @4e
215a: add     #01
215b: sacl    @4e
215c: lar     ar1, @2a
215d: banz    2125, *-
215f: lacc    #0003adb0
2161: lar     ar1, #03b4
2163: sub16   *+
2164: sub     *-
2165: nop
2166: xc      2, leq
2167: opl     @2f, #0001
2169: call    229d, *
216b: lar     ar1, #0263
216d: lacc    #00007500
216f: call    22aa, *
2171: xc      2, leq
2172: opl     @2f, #8000
2174: bit     13, @2f
2175: lar     ar1, #03b6
2177: lacc    #000033ef
2179: call    22aa, *
217b: bcnd    2184, gt
217d: xc      2, tc
217e: opl     @2f, #0804
2180: opl     @2f, #2000
2182: b       2189, *
2184: xc      2, ntc
2185: apl     @2f, #fffb
2187: apl     @2f, #dfff
2189: lar     ar1, #03ba
218b: lacc    #0000429b
218d: call    22aa, *
218f: xc      2, leq
2190: opl     @2f, #0008
2192: lar     ar1, #03b8
2194: lacc    #00004b6f
2196: call    22aa, *
2198: xc      2, leq
2199: opl     @2f, #0010
219b: lar     ar1, #03bc
219d: lacc    #00005305
219f: call    22aa, *
21a1: xc      2, leq
21a2: opl     @2f, #0020
21a4: lar     ar1, #01fc
21a6: lacc    #00002adb
21a8: call    22aa, *
21aa: xc      2, leq
21ab: opl     @2f, #0040
21ad: lacc16  @30
21ae: adds    @31
21af: bsar    6
21b0: sub16   @3e
21b1: subs    @3f
21b2: nop
21b3: xc      2, gt
21b4: apl     @2f, #ffbf
21b6: lar     ar1, #01fe
21b8: lacc    #000059d8
21ba: call    22aa, *
21bc: xc      2, leq
21bd: opl     @2f, #0080
21bf: lar     ar1, #01fa
21c1: lacc    #000061d7
21c3: call    22aa, *
21c5: xc      2, leq
21c6: opl     @2f, #0100
21c8: lacc    #00008008
21ca: call    12ca, *
21cc: lacl    @2f
21cd: and     #00008fff
21cf: call    12ca, *
21d1: call    22bc, *
21d3: call    14a1, *
21d5: b       2114, *
21d7: splk    @1b, #2208
21d9: splk    @1a, #1173
21db: splk    @28, #038f
21dd: lacl    #00
21de: samm    @6e
21df: sacl    @2f
21e0: bldd    #029c, @2b
21e2: ldp     #000
21e3: splk    @74, #03ce
21e5: splk    @76, #0014
21e7: splk    @75, #03ba
21e9: splk    @77, #0018
21eb: lar     ar1, #0358
21ed: rpt     #13
21ee: sach    *+
21ef: lar     ar1, #0180
21f1: rpt     #bf
21f2: sach    *+
21f3: ldp     #007
21f4: call    20e1, *
21f6: apl     @2f, #7800
21f8: lar     ar1, #03b0
21fa: rptz    #000f
21fc: sach    *+
21fd: lar     ar1, #01fa
21ff: rpt     #05
2200: sach    *+
2201: lar     ar1, #0263
2203: sacl    *+
2204: sacl    *-
2205: lar     ar1, #8f
2206: sar     ar1, @2a
2207: ret
2208: splk    @04, #00e4
220a: call    2469, *
220c: call    2471, *
220e: call    3af4, *
2210: call    2461, *
2212: call    2442, *
2214: lar     ar1, @28
2215: lacc    *
2216: sacl    @14
2217: calld   0696, *
2219: lar     ar2, #03b0
221b: call    23bb, *
221d: call    233b, *
221f: call    23af, *
2221: call    23a3, *
2223: call    2363, *
2225: call    2397, *
2227: call    236f, *
2229: call    234f, *
222b: lar     ar1, #02aa
222d: lacc    #20000000
222f: sfl
2230: calld   22ca, *
2232: lar     ar2, #03be
2234: bit     0, @26
2235: cc      452e, tc
2237: ldp     #007
2238: lacl    @4e
2239: add     #01
223a: sacl    @4e
223b: lar     ar1, @2a
223c: banz    2206, *-
223e: call    229d, *
2240: lar     ar1, #0263
2242: lacc    #00007500
2244: call    22aa, *
2246: xc      2, leq
2247: opl     @2f, #8000
2249: lar     ar1, #01fa
224b: lacc    #000061d7
224d: call    22aa, *
224f: xc      2, leq
2250: opl     @2f, #0100
2252: lar     ar1, #03bc
2254: lacc    #00005305
2256: call    22aa, *
2258: xc      2, leq
2259: opl     @2f, #0200
225b: lar     ar1, #03be
225d: lacc16  *+
225e: adds    *-
225f: sub     #00001f40
2261: xc      2, gt
2262: opl     @2f, #0040
2264: bit     15, *
2265: lar     ar1, #02ab
2267: xc      2, tc
2268: splk    *, #0000
226a: lar     ar1, #01fe
226c: lacc    #00005027
226e: call    22aa, *
2270: xc      2, leq
2271: opl     @2f, #0080
2273: lar     ar1, #03ba
2275: lacc    #00005890
2277: call    22b3, *
2279: xc      2, leq
227a: opl     @2f, #0008
227c: lar     ar1, #01fc
227e: lacc    #0000542f
2280: call    22aa, *
2282: xc      2, leq
2283: opl     @2f, #0020
2285: lar     ar1, #03b8
2287: lacc    #000047a2
2289: call    22aa, *
228b: xc      2, leq
228c: opl     @2f, #0010
228e: lacc    #00008016
2290: call    12ca, *
2292: lacl    @2f
2293: and     #00008fff
2295: call    12ca, *
2297: call    22bc, *
2299: call    14a1, *
229b: b       21f6, *

; DSP 229d..22bb: energy qualification
229d: lar     ar1, #03b2
229f: lacc    @2d, 8
22a0: call    22aa, *
22a2: xc      2, leq
22a3: opl     @2f, #0002
22a5: lar     ar1, #0298
22a7: retd
22a8: lacc    @32
22a9: sacl    *
22aa: sub16   *+
22ab: subs    *-
22ac: retc    gt
22ad: lacc16  @30
22ae: adds    @31
22af: bsar    2
22b0: sub16   *+
22b1: subs    *-
22b2: ret
22b3: sub16   *+
22b4: subs    *-
22b5: retc    gt
22b6: lacc16  @30
22b7: adds    @31
22b8: sfr
22b9: sub16   *+
22ba: subs    *-
22bb: ret

; DSP 23a3..2478: receive filters
23a3: lar     ar1, #01ad
23a5: lacc    @14
23a6: sacl    *
23a7: calld   1395, *
23a9: lacc    #000024f6
23ab: bd      0696, *
23ad: lar     ar2, #01fa
23af: lar     ar1, #01c4
23b1: lacc    @14
23b2: sacl    *
23b3: calld   1395, *
23b5: lacc    #00002500
23b7: bd      0696, *
23b9: lar     ar2, #03bc
23bb: lar     ar1, #026c
23bd: lacc    @14
23be: sacl    *
23bf: calld   1395, *
23c1: lacc    #00002505
23c3: bd      0696, *
23c5: lar     ar2, #0263
23c7: lar     ar1, #01c9
23c9: lacc    @14
23ca: sacl    *
23cb: calld   1395, *
23cd: lacc    #0000250a
23cf: bd      0696, *
23d1: lar     ar2, #03b8
23d3: lar     ar1, #01a0
23d5: lacc    @14
23d6: sacl    *
23d7: calld   13a0, *
23d9: lacc    #0000250f
23db: bd      0696, *
23dd: lar     ar2, #01fe
23df: lar     ar3, #01ce
23e1: mar     *, ar3
23e2: lacc    @14
23e3: sacl    *
23e4: calld   13a0, *
23e6: lacc    #00002519
23e8: calld   0696, *
23ea: lar     ar2, #03b6
23ec: lar     ar1, #02a0
23ee: lacc16  *
23ef: add     #00890000
23f1: sach    *+, ar2
23f2: calld   14d6, *
23f4: lar     ar2, #03f8
23f6: mar     *, ar3
23f7: lacc    *, ar1
23f8: abs
23f9: sacl    @7d
23fa: lt      @7d
23fb: lacc    @7b, 5
23fc: mpy     @78
23fd: mpya    @79
23fe: bsar    6
23ff: add16   *+
2400: adds    *-
2401: sach    *+
2402: sacl    *+
2403: lacc    @7b, 5
2404: spac
2405: bsar    6
2406: add16   *+
2407: adds    *-
2408: sach    *+
2409: sacl    *+
240a: lacc    @7d, 6
240b: add16   *+
240c: adds    *-
240d: sach    *+
240e: sacl    *+
240f: lacl    *
2410: sub     #01
2411: sacl    *
2412: retc    gt
2413: lar     ar0, #02
2414: splk    *0-, #0960
2416: apl     @2f, #efff
2418: zap
2419: sqra    *0-
241a: sqra    *0-
241b: bsar    3
241c: sqrs    *
241d: spac
241e: nop
241f: xc      2, lt
2420: opl     @2f, #1000
2422: lacl    #00
2423: rpt     #05
2424: sacl    *+
2425: ret
2426: lar     ar1, #01d9
2428: lacc    @14
2429: sacl    *
242a: calld   13a0, *
242c: lacc    #00002523
242e: bd      0696, *
2430: lar     ar2, #03ba
2432: lar     ar1, #01e1
2434: lacc    @0f
2435: sacl    *
2436: bd      13a8, *
2438: lacc    #0000252d
243a: lar     ar1, #0196
243c: lacc    @0f
243d: sacl    *
243e: bd      1395, *
2440: lacc    #00002541
2442: lar     ar1, #01b7
2444: lacc    @0f
2445: sacl    *
2446: bd      1395, *
2448: lacc    #0000254b
244a: lar     ar1, #01b2
244c: lacc    @0f, 15
244d: sach    *
244e: calld   13a0, *
2450: lacc    #00002546
2452: setc ovm
2453: lacc16  *
2454: add16   *
2455: adrk    #02
2456: retd
2457: sach    *
2458: clrc ovm
2459: lar     ar1, #0266
245b: lacc    @0f
245c: sacl    *
245d: bd      1395, *
245f: lacc    #00002550
2461: lar     ar1, #01c9
2463: lacc    @0f
2464: sacl    *
2465: bd      1395, *
2467: lacc    #00002555
2469: lar     ar1, #01ce
246b: lacc    @0f
246c: sacl    *
246d: bd      13a4, *
246f: lacc    #0000255a
2471: lar     ar1, #01d9
2473: lacc    @0f
2474: sacl    *
2475: bd      1395, *
2477: lacc    #00002569

; supervisor 59cb6..59d3f: queue-drain waits with timer deadlines; not plain delays
59cb6: push cx
59cb7: mov cl, byte ptr [0x14e]
59cbb: sub cl, 2
59cbe: jns 0x59cc3
59cc0: add cl, 0xc8
59cc3: cmp cl, byte ptr [0x14e]
59cc7: je 0x59cd2
59cc9: mov ax, word ptr [0x2dc]
59ccc: cmp ax, word ptr [0x2de]
59cd0: jne 0x59cc3
59cd2: pop cx
59cd3: ret
59cd4: call 0x59cd8
59cd7: retf
59cd8: test byte ptr [0x19f7], 1
59cdd: je 0x59d40
59cdf: push cx
59ce0: mov cl, byte ptr [0x14e]
59ce4: sub cl, 2
59ce7: jns 0x59cec
59ce9: add cl, 0xc8
59cec: cmp cl, byte ptr [0x14e]
59cf0: je 0x59cfb
59cf2: mov ax, word ptr [0x2dc]
59cf5: cmp ax, word ptr [0x2de]
59cf9: jne 0x59cec
59cfb: pop cx
59cfc: mov al, 0x7f
59cfe: test byte ptr [0x19f7], 1
59d03: je 0x59d40
59d05: push cx
59d06: mov cl, byte ptr [0x14e]
59d0a: sub cl, 2
59d0d: jns 0x59d12
59d0f: add cl, 0xc8
59d12: cmp cl, byte ptr [0x14e]
59d16: je 0x59d3f
59d18: push ax
59d19: push word ptr [0xff18]
59d1d: mov word ptr [0xff18], 0xa
59d23: cmp byte ptr [0x2cb], 0x7f
59d28: je 0x59d34
59d2a: pop ax
59d2b: and ax, 0x7f
59d2e: mov word ptr [0xff18], ax
59d31: pop ax
59d32: jmp 0x59d12
59d34: mov byte ptr [0x2cb], al
59d37: pop ax
59d38: and ax, 0x7f
59d3b: mov word ptr [0xff18], ax
59d3e: pop ax
59d3f: pop cx

; supervisor 635a1..6362a: originate configuration and command selection
635a1: call 0x6a571
635a4: call 0x63a40
635a7: call 0x60d22
635aa: call 0x69cb6
635ad: call 0x6133a
635b0: call 0x61b74
635b3: call 0x69cb6
635b6: call 0x6132b
635b9: call 0x69cb6
635bc: call 0x618df
635bf: call 0x69cb6
635c2: call 0x61917
635c5: call 0x69cb6
635c8: call 0x618fe
635cb: push cx
635cc: mov cx, 0x28
635cf: push cx
635d0: lcall 0x57bb, 0xa82
635d5: pop cx
635d6: loop 0x635cf
635d8: pop cx
635d9: cmp byte ptr [0x1fe4], 0
635de: je 0x635e3
635e0: call 0x666f0
635e3: call 0x5e392
635e6: call 0x63f6b
635e9: call 0x6389a
635ec: call 0x638e1
635ef: call 0x6405b
635f2: mov word ptr [0x1d77], 0xe7e6
635f8: call 0x66461
635fb: jb 0x63606
635fd: mov word ptr [0x1d77], 0xe7fb
63603: call 0x640b8
63606: mov al, 0x8c
63608: lcall 0x675b, 0x1c4
6360d: call 0x639b8
63610: jb 0x6362b
63612: lcall 0x703b, 0x4593
63617: mov ax, word ptr [0x1bfa]
6361a: mov word ptr [0x1bfe], ax
6361d: mov ax, word ptr [0x1bfc]
63620: mov word ptr [0x1c00], ax
63623: mov byte ptr [0x1bf9], 7
63628: jmp 0x5b838

; supervisor 638ad..638e0: originate mode predicates
638ad: test byte ptr [0x1c06], 2
638b2: jne 0x638c0
638b4: test byte ptr [0x912], 1
638b9: jne 0x638c0
638bb: test byte ptr [0xa12], 1
638c0: ret
638c1: test byte ptr [0x93a], 0x40
638c6: jne 0x638df
638c8: cmp byte ptr [0x96e], 1
638cd: jne 0x638df
638cf: cmp byte ptr [0x974], 0
638d4: je 0x638dd
638d6: cmp byte ptr [0x974], 3
638db: jbe 0x638df
638dd: stc
638de: ret
638df: clc
638e0: ret

; supervisor 63975..63a3f: call supervision
63975: test byte ptr [0x92a], 1
6397a: jne 0x63980
6397c: call word ptr [0x1d77]
63980: test byte ptr [0x937], 1
63985: je 0x639ad
63987: push ax
63988: mov ax, 0x803
6398b: call 0x6a91d
6398e: pop ax
6398f: je 0x639ad
63991: test byte ptr [0x201f], 2
63996: je 0x639ad
63998: call 0x64023
6399b: call 0x63fc7
6399e: test byte ptr [0x201f], 8
639a3: je 0x639b7
639a5: and byte ptr [0x201f], 0xfd
639aa: stc
639ab: jmp 0x639b7
639ad: call 0x63f9e
639b0: call 0x64023
639b3: call 0x63fc7
639b6: clc
639b7: ret
639b8: cmp byte ptr [0x6a5], 0
639bd: jne 0x639c4
639bf: mov byte ptr [0x693], 0
639c4: mov byte ptr [0x1c5f], 0
639c9: test byte ptr [0x2035], 1
639ce: je 0x639d7
639d0: test byte ptr [0x2035], 4
639d5: jne 0x63a39
639d7: test byte ptr [0x1d18], 1
639dc: je 0x639f5
639de: call 0x63975
639e1: jb 0x63a39
639e3: cmp byte ptr [0x6a5], 0
639e8: je 0x639f0
639ea: mov al, 0
639ec: call word ptr [0x2ac]
639f0: lcall 0x675b, 0x8c88
639f5: test byte ptr [0x694], 0x80
639fa: jne 0x63a39
639fc: test byte ptr [0x1fe4], 0xff
63a01: jne 0x63a3b
63a03: test byte ptr [0x694], 0x40
63a08: je 0x639c9
63a0a: mov al, byte ptr [0x693]
63a0d: or al, al
63a0f: je 0x63a39
63a11: test byte ptr [0x6a3], 8
63a16: je 0x63a23
63a18: lcall 0x57bb, 0x7ca8
63a1d: call 0x68667
63a20: call 0x68667
63a23: lcall 0x7b41, 0x22f5
63a28: mov byte ptr [0x1f50], 8
63a2d: lcall 0x7b41, 0x710
63a32: or byte ptr [0x1f4b], 0x10
63a37: clc
63a38: ret
63a39: stc
63a3a: ret
63a3b: call 0x666f0
63a3e: jmp 0x639c9

; supervisor 63f9e..6405a: qualified call-progress consumers
63f9e: cmp byte ptr [0x6a5], 0
63fa3: jne 0x63fc2
63fa5: test byte ptr [0x1d6b], 2
63faa: je 0x63fc2
63fac: and byte ptr [0x1d6b], 0x8f
63fb1: cmp byte ptr [0x956], 5
63fb6: jb 0x63fbd
63fb8: mov al, 0xb
63fba: call 0x62f92
63fbd: and byte ptr [0x1d6b], 0xfd
63fc2: ret
63fc3: call 0x63fc7
63fc6: retf
63fc7: push ax
63fc8: cmp byte ptr [0x6a5], 0
63fcd: jne 0x63fe7
63fcf: mov al, byte ptr [0x1fb6]
63fd2: cmp byte ptr [0x1fb7], 1
63fd7: je 0x63fe9
63fd9: cmp byte ptr [0x965], 6
63fde: jae 0x63fe9
63fe0: cmp byte ptr [0x956], 3
63fe5: jae 0x63fe9
63fe7: pop ax
63fe8: ret
63fe9: mov ah, byte ptr [0x1d6b]
63fed: shr ah, 4
63ff0: and ah, 0xf
63ff3: cmp ah, al
63ff5: jae 0x63ff9
63ff7: jmp 0x63fe7
63ff9: pop ax
63ffa: test byte ptr [0x694], 0x80
63fff: jne 0x63fe7
64001: cmp byte ptr [0x965], 6
64006: jl 0x6400c
64008: call 0x5fb29
6400b: ret
6400c: call 0x68f9c
6400f: mov al, 7
64011: mov byte ptr [0x1bf9], 3
64016: or byte ptr [0x6a4], 1
6401b: call 0x5fb29
6401e: ret
6401f: call 0x64023
64022: retf
64023: cmp byte ptr [0x6a5], 0
64028: je 0x6402b
6402a: ret
6402b: cmp byte ptr [0x956], 5
64030: jae 0x64033
64032: ret
64033: cmp byte ptr [0x956], 7
64038: je 0x6405a
6403a: test byte ptr [0x1d6b], 1
6403f: je 0x6405a
64041: test byte ptr [0x694], 0x80
64046: jne 0x6405a
64048: call 0x68f9c
6404b: mov al, 0xc
6404d: mov byte ptr [0x1bf9], 4
64052: or byte ptr [0x6a4], 2
64057: call 0x5fb29
6405a: ret

; supervisor 6405b..6410b: originate commands 10/17 and monitor setup
6405b: mov ax, 0x5a
6405e: call 0x638c1
64061: jb 0x640ab
64063: call 0x638ad
64066: je 0x640b4
64068: cmp byte ptr [0x8fe], 2
6406d: je 0x64076
6406f: cmp byte ptr [0x8fe], 9
64074: jne 0x6408c
64076: cmp byte ptr [0x6a5], 0
6407b: jne 0x6408c
6407d: lcall 0x57bb, 0x2531
64082: mov cx, 0xa
64085: lcall 0x57bb, 0xa9f
6408a: loop 0x64085
6408c: mov bx, 0
6408f: cmp byte ptr [0x8fe], 2
64094: je 0x640a0
64096: cmp byte ptr [0x8fe], 9
6409b: je 0x640a0
6409d: mov bx, 1
640a0: mov ax, 0x7f
640a3: lcall 0x675b, 0x77b
640a8: mov ax, 0x10
640ab: mov bx, word ptr [0x2c2]
640af: lcall 0x675b, 0x77b
640b4: call 0x6410c
640b7: ret
640b8: call 0x638c1
640bb: jb 0x640ce
640bd: call 0x638ad
640c0: jne 0x640ce
640c2: mov ax, 0x17
640c5: mov bx, word ptr [0x2c2]
640c9: lcall 0x675b, 0x77b
640ce: ret
640cf: call 0x6410c
640d2: retf
640d3: call 0x6410c
640d6: retf
640d7: call 0x640db
640da: retf
640db: mov byte ptr [0x1d76], 0
640e0: cmp byte ptr [0x97c], 4
640e5: jne 0x640fc
640e7: call 0x62e51
640ea: or ax, 0x430a
640ed: inc cx
640ee: dec sp
640ef: dec sp
640f0: and byte ptr [bx + si + 0x52], dl
640f3: dec di
640f4: inc di
640f5: push dx
640f6: inc bp
640f7: push bx
640f8: push bx
640f9: or ax, 0xa
640fc: mov word ptr [0x2da], 0x627d
64102: xor bx, bx
64104: mov ax, 0x1500
64107: lcall 0x675b, 0x77f

; supervisor 6410c..64147: call-progress reset and DSP configuration
6410c: mov byte ptr [0x1d6a], 5
64111: mov byte ptr [0x1c5f], 0
64116: mov byte ptr [0x1d68], 5
6411b: xor al, al
6411d: mov di, 0x1d6b
64120: push cx
64121: mov cx, 0xb
64124: rep stosb byte ptr es:[di], al
64126: pop cx
64127: call 0x6412b
6412a: ret
6412b: push bx
6412c: xor bh, bh
6412e: mov bl, byte ptr [0x1faf]
64132: mov ax, 0x1f
64135: lcall 0x675b, 0x77b
6413a: mov bx, word ptr [0x1fb0]
6413e: mov ax, 0x19
64141: lcall 0x675b, 0x77b
64146: pop bx
64147: ret

; supervisor 67d33..67d8b: outbound word ring and silent full-queue rejection
67d33: pushf
67d34: cli
67d35: push bx
67d36: push cx
67d37: mov cx, 2
67d3a: mov bx, word ptr [0x2de]
67d3e: add cx, bx
67d40: cmp cx, 0x310
67d44: jb 0x67d49
67d46: mov cx, 0x2e0
67d49: cmp cx, word ptr [0x2dc]
67d4d: je 0x67d5a
67d4f: mov word ptr [bx], ax
67d51: mov word ptr [0x2de], cx
67d55: pop cx
67d56: pop bx
67d57: popf
67d58: clc
67d59: ret
67d5a: pop cx
67d5b: pop bx
67d5c: popf
67d5d: stc
67d5e: ret
67d5f: pushf
67d60: cli
67d61: push cx
67d62: mov cx, word ptr [0x2de]
67d66: sub cx, word ptr [0x2dc]
67d6a: jae 0x67d6f
67d6c: add cx, 0x30
67d6f: cmp cx, 0x2a
67d72: ja 0x67d89
67d74: pop cx
67d75: push ax
67d76: mov ax, 0xff00
67d79: call 0x67d33
67d7c: pop ax
67d7d: push ax
67d7e: call 0x67d33
67d81: mov ax, bx
67d83: call 0x67d33
67d86: pop ax
67d87: popf
67d88: ret
67d89: pop cx
67d8a: popf
67d8b: ret

; supervisor 6db02..6dd34: DSP monitor report processing
6db02: in al, 0x5e
6db04: mov ah, al
6db06: in al, 0x5c
6db08: test byte ptr [0x2034], 4
6db0d: jne 0x6db19
6db0f: test byte ptr [0x2036], 1
6db14: je 0x6db3a
6db16: call 0x6dd35
6db19: cmp word ptr [0x161], 0x1b58
6db1f: ja 0x6db38
6db21: cmp word ptr [0x161], 0x514
6db27: ja 0x6db3a
6db29: cmp word ptr [0x161], 0x44c
6db2f: ja 0x6db38
6db31: cmp word ptr [0x161], 0x64
6db36: ja 0x6db3a
6db38: and al, 0xfe
6db3a: test byte ptr [0x2035], 1
6db3f: je 0x6db44
6db41: call 0x6dd35
6db44: lcall 0x57bb, 0xe8d4
6db49: jae 0x6db6c
6db4b: cmp word ptr [0x161], 0xfa0
6db51: ja 0x6db6a
6db53: cmp word ptr [0x161], 0x5dc
6db59: ja 0x6db6c
6db5b: cmp word ptr [0x161], 0x514
6db61: ja 0x6db6a
6db63: cmp word ptr [0x161], 0x64
6db68: ja 0x6db6c
6db6a: and al, 0xde
6db6c: test byte ptr [0x1d68], 0xff
6db71: je 0x6db86
6db73: dec byte ptr [0x1d68]
6db77: mov byte ptr [0x1d69], 0xff
6db7c: jmp 0x6dc46
6db7f: mov byte ptr [0x1d69], 0xfe
6db84: jmp 0x6dbd1
6db86: test al, 0x3c
6db88: jne 0x6db7f
6db8a: and al, byte ptr [0x1d69]
6db8e: test al, 1
6db90: je 0x6dbd1
6db92: inc byte ptr [0x1d71]
6db96: inc byte ptr [0x1d79]
6db9a: jne 0x6dba4
6db9c: dec byte ptr [0x1d71]
6dba0: dec byte ptr [0x1d79]
6dba4: cmp byte ptr [0x1d79], 3
6dba9: jb 0x6dbc5
6dbab: mov byte ptr [0x1d79], 0
6dbb0: cmp byte ptr [0x956], 5
6dbb5: jae 0x6dbb9
6dbb7: jmp 0x6dbc5
6dbb9: cmp byte ptr [0x956], 7
6dbbe: je 0x6dbc5
6dbc0: and byte ptr [0x1d6b], 0x8f
6dbc5: cmp byte ptr [0x1d71], 0x14
6dbca: jb 0x6dbd1
6dbcc: or byte ptr [0x1d6b], 1
6dbd1: call 0x6dc80
6dbd4: test al, 0x3f
6dbd6: jne 0x6dbf6
6dbd8: cmp byte ptr [0x1d6d], 0
6dbdd: je 0x6dbec
6dbdf: push ax
6dbe0: mov al, byte ptr [0x1d6f]
6dbe3: mov byte ptr [0x1d70], al
6dbe6: pop ax
6dbe7: mov byte ptr [0x1d6f], 0
6dbec: inc byte ptr [0x1d6f]
6dbf0: jne 0x6dbf6
6dbf2: dec byte ptr [0x1d6f]
6dbf6: test al, 2
6dbf8: je 0x6dc33
6dbfa: test byte ptr [0x1d6d], 2
6dbff: jne 0x6dc0e
6dc01: push ax
6dc02: mov al, byte ptr [0x1d72]
6dc05: mov byte ptr [0x1d73], al
6dc08: pop ax
6dc09: mov byte ptr [0x1d72], 0
6dc0e: inc byte ptr [0x1d72]
6dc12: jne 0x6dc18
6dc14: dec byte ptr [0x1d72]
6dc18: cmp byte ptr [0x1d6d], al
6dc1c: je 0x6dc33
6dc1e: call 0x6dd0b
6dc21: push ax
6dc22: mov ah, byte ptr [0x1d6d]
6dc26: xor al, ah
6dc28: and al, 2
6dc2a: pop ax
6dc2b: je 0x6dc33
6dc2d: call 0x6dc9c
6dc30: call 0x6dcd2
6dc33: lcall 0x57bb, 0xc598
6dc38: jae 0x6dc46
6dc3a: cmp byte ptr [0x1d72], 0xfa
6dc3f: jb 0x6dc46
6dc41: mov byte ptr [0x1d6b], 0xe0
6dc46: and al, 0x3f
6dc48: mov byte ptr [0x1d6c], al
6dc4b: mov byte ptr [0x1d6d], al
6dc4e: cmp byte ptr [0x1d6e], 0xff
6dc53: je 0x6dc62
6dc55: inc byte ptr [0x1d6e]
6dc59: test al, 4
6dc5b: jne 0x6dc62
6dc5d: mov byte ptr [0x1d6e], 0
6dc62: cmp byte ptr [0x97c], 4
6dc67: je 0x6dc6a
6dc69: ret
6dc6a: push ax
6dc6b: lcall 0x57bb, 0xb270
6dc70: mov al, 0x20
6dc72: lcall 0x57bb, 0x1845
6dc77: mov al, 0x20
6dc79: lcall 0x57bb, 0x1845
6dc7e: pop ax
6dc7f: ret
6dc80: mov bl, al
6dc82: cmp bl, 0
6dc85: je 0x6dc9b
6dc87: cmp bl, 2
6dc8a: je 0x6dc9b
6dc8c: cmp byte ptr [0x1d6d], 2
6dc91: jne 0x6dc9b
6dc93: dec byte ptr [0x1d6a]
6dc97: je 0x6dc9b
6dc99: mov al, 2
6dc9b: ret
6dc9c: push ax
6dc9d: mov al, byte ptr [0x1d6f]
6dca0: cmp al, byte ptr [0x1fbb]
6dca4: jb 0x6dccb
6dca6: and byte ptr [0x1d6b], 0x8f
6dcab: mov al, byte ptr [0x1d73]
6dcae: cmp al, byte ptr [0x1fb9]
6dcb2: jb 0x6dccb
6dcb4: cmp al, byte ptr [0x1fba]
6dcb8: ja 0x6dccb
6dcba: and byte ptr [0x1d6b], 0x8f
6dcbf: or byte ptr [0x1d6b], 2
6dcc4: or byte ptr [0x1d76], 1
6dcc9: pop ax
6dcca: ret
6dccb: and byte ptr [0x1d6b], 0xfd
6dcd0: pop ax
6dcd1: ret
6dcd2: push ax
6dcd3: test byte ptr [0x1d6b], 2
6dcd8: jne 0x6dd04
6dcda: mov al, byte ptr [0x1d6f]
6dcdd: cmp al, byte ptr [0x1fb4]
6dce1: jb 0x6dd04
6dce3: cmp al, byte ptr [0x1fb5]
6dce7: ja 0x6dd04
6dce9: mov al, byte ptr [0x1d73]
6dcec: cmp al, byte ptr [0x1fb2]
6dcf0: jb 0x6dd04
6dcf2: cmp al, byte ptr [0x1fb3]
6dcf6: ja 0x6dd04
6dcf8: pop ax
6dcf9: add byte ptr [0x1d6b], 0x10
6dcfe: or byte ptr [0x1d76], 1
6dd03: ret
6dd04: and byte ptr [0x1d6b], 0x8f
6dd09: pop ax
6dd0a: ret
6dd0b: test al, 0x3c
6dd0d: je 0x6dd34
6dd0f: and byte ptr [0x1d6b], 0x8d
6dd14: mov byte ptr [0x1d6f], 0
6dd19: mov byte ptr [0x1d72], 0
6dd1e: mov byte ptr [0x1d70], 0
6dd23: mov byte ptr [0x1d73], 0
6dd28: cmp byte ptr [0x965], 6
6dd2d: jb 0x6dd34
6dd2f: lcall 0x57bb, 0x2703
6dd34: ret
