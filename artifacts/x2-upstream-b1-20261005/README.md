# Courier x2 upstream B1, 5 October 2026

The B1 acquisition in v90modem is now correct. The original capture is
`../x2-upstream-e-20261005/courier-upstream.g711` (278249 PCMU samples;
SHA256 b01953a0b55f5784692c53b13dd4f1f7a115a6aa38b01a1d74ff379b9bfcbefe).

- `live-b1-setup-trace.json`: a new paired call with the original firmware,
  B1A1..B1C2. B1B4 sends N=10 (24000 upstream bit/s) into the mapper builder.
- `analog-dsp-{program,data}.bin`: the original DSP snapshot that we kept from
  the MP call before this one. It supplies the program and the lookup tables
  to the controlled execution.
- `native-verification.json`, `mapper.asm`, `native-symbols.json`: the original
  B1A1 setup, then AF99/mapper execution for 480 Q9.7 symbols. We seed the
  received word, the direction and the mask explicitly. We do not infer them
  from a complete replay. Each symbol decrements the 03CA counter of the outer
  scheduler.
- `reference.c`, `reference-*.json`, `reference-comparison.json`: a comparison
  with the SpanDSP all-one mapper. Expanded shaping agrees with all 480
  amplitude norms. Expanded/64-state agrees with 475 complex symbols, and
  minimum/16-state agrees with 49. This acquisition correction does not solve
  the five remaining rotations.
- `default-replay.log`: the full engine with default settings gives a 99.9% B1
  fit. A separate 256-symbol check has a lattice distance of 0.252 and a power
  of 147.2 against 147.7. The winning settings are GPA/expanded/64-state. The
  decoder also receives the winning trellis. The end state is still TRAINING.
  We did not verify the decoded upstream payload.
- `disabled-replay.log`: ME_X2_UPSTREAM_ACQUIRE=0 disables the acquisition.
- `acquisition-tests.log`: the capture at block sizes 17 and 160 acquires
  above 95%. It selects expanded/64-state in the template and in the decoder.
  The test rejects silence.
- `v34-data-tests.log`: all 402 cases of the V.34 data decoder pass.

To reproduce, use these commands:

```
.venv/bin/python tools/verify_x2_upstream_b1.py
cc -I/opt/homebrew/opt/libtiff/include -I../v90modem/spandsp-master/src artifacts/x2-upstream-b1-20261005/reference.c ../v90modem/spandsp-master/src/.libs/libspandsp.a -lm -o /private/tmp/x2-b1-reference
/private/tmp/x2-b1-reference 24000 4 6 0 1 2
make -C ../v90modem x2-b1-test v90_engine_replay
ME_MODE=x2 ../v90modem/v90_engine_replay artifacts/x2-upstream-e-20261005/courier-upstream.g711 ulaw --fast --from 0
```

The logged sample 8309 of B1 is relative to the prepared 9600-Hz T/3 ring. It
is not an absolute sample of the PCMU bearer. We did not add a G.711 gain
adjustment or resampling to the input path of the engine. The internal V.34
receiver continues to use its existing T/3 processing.
