# Native bulk G.711 for RTP audio

## What moved to native code

RTP audio packet encoding and receive-block decoding now use optional bulk
G.711 routines in `native/g711.hpp`, exported by `native/c5x_capi.cpp`:

- `courier_g711_encode`: PCM16 to mu-law or A-law octets.
- `courier_g711_decode`: mu-law or A-law octets to PCM16.

`courier_emu/g711_native.py` binds these on an **already loaded** core library.
`SipSession` uses them for its standard codecs. This replaces hundreds of
Python scalar calls per packet with one native call, including both laws.
The native header is tracked by the library build's dependency list.

These are integer codecs, not a different audio model. Exhaustive tests match
all **65,536 PCM16 input values** and all **256 codewords**, separately for
both laws. No codec tables, clipping convention, RTP payload type, timestamps,
sequence numbers, sample clocks, queue capacity or acceptance checks change.

## Compatibility and scheduling

- No loaded native core, an older prebuilt library missing the optional ABI,
  or `COURIER_NATIVE_G711=0` retains the scalar Python path. Checking support
  never builds/loads a core. Native function bindings are cached per library.
- Custom encoder/decoder callbacks bypass the bulk path.
- Encoding only accepts ordinary in-range PCM16 integers. Other scalar inputs
  retain Python's clipping and conversion behavior, including custom objects.
  A declined path does not consume queue data or one-shot iterators.
- The sender peeks before native conversion and consumes exactly one complete
  packet only after success. A failed native call raises without consuming it.
- Existing receive capacity checks still run before decoding. Native buffer,
  pointer and law guards reject invalid calls without writing output.
- Opaque digital G.711/codeword mode is untouched: its bytes are neither
  decoded nor re-encoded, preserving the V.90/x2 digital path.
- The tiny codec kernels use `ctypes.PYFUNCTYPE`, retaining the GIL just as the
  replaced Python work did. A media worker should not give up the GIL and
  wait on a busy CPU thread merely to run a short native kernel.
  This is distinct from long DSP stepping, which retains its existing policy.

## Reproducible codec-path benchmark

```sh
.venv/bin/python -m tools.benchmark_g711 --packets 5000 --pairs 4
```

The benchmark explicitly builds/loads the library **before timing**, creates no
sockets and runs no firmware or live calls. It includes marshalling, sender
queue extension/consumption and receive queue extension, not just a native
inner loop. The scalar encoding control is the original per-sample path.
Measurements alternate order within the same process; output is checked against
the original scalar codecs. There is no speed threshold in regression tests.

On vmhost, Clang 19.1.7, pinned benchmark subprocess, 5,000 packets/measurement:

| Path | Scalar median s | Native median s | Speedup |
| --- | ---: | ---: | ---: |
| PCMU encode packet | 0.34182 | 0.06962 | **4.91x** |
| PCMA encode packet | 0.37631 | 0.07027 | **5.35x** |
| PCMU decode block | 0.09559 | 0.01937 | **4.93x** |
| PCMA decode block | 0.09333 | 0.01940 | **4.81x** |

These are **codec-path performance results**, not an end-to-end modem speedup
or evidence that long-call timing/stability is fixed. The earlier fake-SIP
firmware replay bypasses RTP codecs, so it is not a performance benchmark for
this change. No such replay gain is claimed.

## Validation and artifacts

- **70 focused tests passed on vmhost**: exhaustive codec parity, scalar and
  older-library fallback, packet boundaries/accounting, custom callbacks,
  codeword bypass, native failure/bounds behavior and existing RTP/media-clock,
  packet-recovery and media-start controls.
- **286 focused local tests passed** across the new codecs, all RTP/SIP test
  modules, bearer SIP playout, resampling, native scheduler reentry and G.711
  peer pacing/framing. This includes a benchmark smoke test without a speed
  assertion. Neither result is a full-suite claim.
- Synthetic complete RTP datagrams, sequence/timestamp progress, queue state
  and transmit timing/accounting snapshots match with native mode enabled and
  disabled. This is packet-path differential evidence, not a live call claim.

The remote candidate, copied source, compiler/source/library manifest, raw
alternating timings and tests remain isolated under
`/root/courier-perf-followup/perf-g711-followup/`. Local artifacts are under
`tmp/tx-timing-followup/vmhost-g711/` with the launcher alongside. The source
snapshot already contained uncommitted work; this is not a clean-revision claim.

CT127 is restored to **stopped**. No existing deployment/default library, PBX
configuration, credentials or unrelated call was changed. No live calls were
placed for this change.
