# V.8 dispatcher, 403 linked pair

```sh
./courier link artifacts/courier-board-21210-capture-403/courier-board.rom \
  --with-dsp --nvram-fixture idsdl403 --board-id 7 --dip-preset default --tick-ms 5 \
  --a-at ATX0 --a-at ATDT5551234 --b-at ATA \
  --instructions 85000000 --summary
```

`run-baseline.json` comes from the same command, with the pre-linked test of
`_find_call_overlay` forced to true. That is, it shows the behaviour before
this change. Each V.8 number is identical in the two runs. Only
`call_overlay_available` is different.

## Audio capture

`run-audio.json` and `audio/` come from the same command with `--audio-dir`.

| wav | frames | peak | nonzero | first | last |
|---|---:|---:|---:|---:|---:|
| `a-tx` | 127,200 | **0** | **0** | - | - |
| `b-rx` | 126,400 | **0** | **0** | - | - |
| `b-tx` | 126,400 | 17,188 | 23,841 | 96,273 | 120,113 |
| `a-rx` | 126,400 | 17,188 | 23,841 | 96,273 | 120,113 |

B to A is sample-exact. A transmits silence for all of the run.
