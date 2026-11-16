# x2 7-bit marker receiver (QF060003)

`tools/verify_x2_marker_receiver.py` executes the original Quad parse at
`97b5`-`97dd`/`9800` for all 128 body values and for the two values of bit 1
of `[006f]`. Then it compares the result with the field layout of the Courier
transmitter (carrier bit, then two 3-bit indices, first-sent bit first). The
parse accepts 32 of 256 cases: the cases whose own index is 6. The arming site
is `9791` (`lacl #07`). IM020104 has the same site at `948a`. Refer to the last
section of `docs/x2-v90-protocol-selection.md`. We read the CRC and sync code,
but we did not run them on a transmitted frame.
