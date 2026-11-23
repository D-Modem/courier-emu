# 3453 normal/bootmodem execution checks

Implementation and reproduction: [3453 flash boot](../../docs/3453-flash-boot.md).

The initial `bc-normal.json` records the previous unprocessed AT input;
`c-normal.json` records the previously working stock C execution. Intermediate
`*-first.json`/`*-fixed.json` files preserve bring-up results, not a guarantee
that every diagnostic trace represents the final implementation.

Whole-flash B/C runs demonstrate:

* `bc-whole-normal.json` and `bc-whole-boot.json`: firmware-generated `5608`
  and OK using the private captured settings; verified resident download.
* `bc-whole-normal-ati7.json` and `bc-whole-boot-ati7.json`: full profile output
  from the original firmware, with 2.2.09 / DSP 2.0.34 and the captured serial.
  Product type, DAA revision and flash ID are not hardware-faithful yet.
* `bc-switch-to-boot.json` and `bc-switch-to-normal.json`: original guest
  `ATZ!!` handlers cross the verified entry vectors; the final mode and the
  transition instruction count appear in `flash`.
* `bc-roundtrip.json`: normal → bootmodem → normal, with `5608` and OK in each
  resulting mode and zero remaining serial input.

The assembled image and raw settings live only under the Git-ignored private
archive. They are not part of this public evidence bundle.

Final regression command:

```sh
.venv/bin/python -m pytest -q tests/test_3453* tests/test_machine_map.py \
  tests/test_cli_link.py tests/test_native_machine.py
```

Full power-on initially had **79 passing tests**. The hardware-model follow-up
now covers **91 tests**: the full run passed 89, and the two corrected split-image
fixture assertions passed on focused rerun (no implementation changes afterward).
See [hardware-model progress](hardware-model-progress.md) for banking, flash ID,
DAA identity and board-tick fixes, plus the remaining failed call bring-up. Tests cover all four public
captured supervisors, complete-flash round trips, DSP source/table cache
isolation, code-hash guards, actual-PC diagnostics, CLI forwarding and existing
3453/older ROM behavior. Power-on cases execute `FFFF0` and the original loader:
valid application CRCs select normal, a momentary selection input selects
recovery, and corrupt application/supervisor bytes or an absent normal image
cause genuine CRC-driven recovery. Both families answer AT commands after these
paths with matching DSP bootstrap. A cold B/C startup also passes a subsequent
`ATZ!!` round trip. Carrier operation remains untested.
