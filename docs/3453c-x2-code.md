# x2 executable code retained in 3453C 2.3.33

We examined this on 2026-10-04 against `docs/3453C_v2.3.33/2_3_33.XMF`, SHA256
`c8d44a1c984a203f6e9a91b14c77382706ea05fc2b860081f986c47b6fa7c41e`.
The root `2_3_33.XMF` is identical. The supervisor addresses below use the
physical mapping of the XMF at `0x40000`. The DSP addresses are program word
addresses.

**Executable x2 setup code stays in the image, with a caller in the connection
setup.** This is stronger evidence than retained strings. But it does not show
a complete working x2 connection. It also does not show that each original
peer-detection path stays.

An overlay-aware [DSP decompilation bundle](../artifacts/3453c-x2-decomp-20261004/README.md)
now contains manually lifted C, the original disassembly, and 1,793 execution
comparisons with the original DSP code. These include the retained scramblers
and the fixed-GPC PCM training generator.

The [server reconstruction](../artifacts/x2-server-decomp-20261004/README.md)
adds 6,562 C/native comparisons for the pre-V.90 I-modem and the shared
x2/V.90 Quad helpers. It includes the route of the I-modem from tag 70 to its
INFO0 capability buffer. In this 3453C build, the equivalent route does not exist: the negotiation start (`0a64`) puts the tag-51 word at `[7fec]` in the queue, and nothing reads the tag-70 word at `[7feb]`.
The latest lift includes 4,096 consecutive calls through the four-state
asymmetric startup source of the server. Its cycle of 2,010 calls contains
1,747 `007e` words, seven zeros, and 128 ascending/descending pairs.
The source words alone do not show the sample timing or the receiver
acceptance.

An ITU-style draft is at
`artifacts/x2-spec-20261004/x2-technical-specification.docx`. It has numbered
clauses, state tables, capability fields and separate evidence levels.
The complete downstream mapper and the full-call negotiation are still open.

## Supervisor

The connection-setup sequence is:

```text
63e22  call 61746         ; x2 eligibility
63e25  jb   63e2a         ; carry means ineligible
63e27  call 618ca         ; x2 setup
63e2a  call 61705         ; adjacent V.90 eligibility
63e2d  jb   63e35
63e2f  call 61879         ; adjacent V.90 setup
```

The x2 eligibility routine at `61746` does these steps:

- It must have `[1a07] & 20h`.
- It rejects `[093c] & 01h` (the relocated S58 x2-disable test).
- It rejects mode 1 and modes of 6 or more.
- It calls the shared line gate `63a0f`.
- It examines the maximum-speed and conditional ceiling settings.

It returns with carry clear at `61783` for eligibility, and with carry set at
`61785` for rejection.

The setup routine at `618ca` clears the PCM diagnostic state and tests
`[093c] & 1` again at `618f5`. Then it gets the base capability word from
`6129b`:

```text
618ff  and bx, fdff
61903  test byte ptr [093c], 04
61908  je 6190e
6190a  or bx, 0200
6190e  or bx, 0400
61912  test byte ptr [093c], 10
61917  je 6191d
61919  and bx, fbff
6191d  and bx, e7ff
61921  and bx, 3fff
61925  mov ax, 0070
61928  lcall 6770:0777     ; queue mailbox command/value
6192d  lcall 57bb:2118
61932  ret
```

These capability edits and command `70` agree with the older x2-specific
setup in [pcm-x2-v90.md](pcm-x2-v90.md). The adjacent V.90 routine tests
`[093c] & 20h` and sends command `72`. It does not have the old empty body.

## DSP

The resident dispatcher at `12c0` subtracts `87h` from the tag, adds `1394h`,
and reads the handler from the table. Thus its effective table base is
`130dh`. Entry `137dh` for tag `70h` names `08f8`, in the downloaded low
overlay 7 (origin `0000`, file offset `12b20`, 4,094 words).

```text
08f8  smmr @7a, #7feb
08fa  lar ar1, #7feb
08fc  opl *, #4000
08fe  apl *, #7fff
0900  opl *, #0000
0902  lar ar1, #7fe8
0904  splk *, #8000
0906  lar ar1, #7fee
0908  opl *, #0001
090a  ret
```

This keeps the old shape of the capability/parameter-fresh/enable update,
with relocated cells and changed capability handling. The older mask was
`3fff`. This build is different: it forces bit 14 and clears bit 15. Thus do
not treat it as byte-identical to the old x2 DSP behavior. Tag `71` also stays
at `090b`, and stores a 15-bit rate mask into `7fea`.

We executed the original `08f8` machine code in `NativeC5x` after we loaded
the resident and the low overlay. With DP=0 and ARP=1, the inputs `0000`,
`0400`, `0600`, and `ffff` each returned in 13 instructions, with:

| Input | `[7feb]` | `[7fe8]` | `[7fee]` |
|---|---|---|---|
| 0000 | 4000 | 8000 | 0001 |
| 0400 | 4400 | 8000 | 0001 |
| 0600 | 4600 | 8000 | 0001 |
| ffff | 7fff | 8000 | 0001 |

The isolated execution confirms that the handler operates as decoded. We did
not change live modem settings, and we did not try an x2 call. The complete
peer negotiation, the PCM training and the data transfer are not verified.
