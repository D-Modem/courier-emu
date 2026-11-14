# 403 pair budgeted on line frames

```sh
./courier link artifacts/courier-board-21210-capture-403/courier-board.rom \
  --with-dsp --nvram-fixture idsdl403 --board-id 7 --dip-preset default --tick-ms 5 \
  --audio-dir <dir> --line-frames 300 \
  --a-at ATX0 --a-at ATDT5551234 --b-at ATA \
  --instructions 250000000 --summary
```

Both ends stop at 300 line frames. That is 30.00 s of codec time for each end.
With a budget on instructions, the times are 22.82 s and 15.89 s. No socket closes
early. Both ends report `connected: true` and `buffer_left: 2`.
