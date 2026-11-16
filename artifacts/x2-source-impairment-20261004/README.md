# x2 symmetric startup source impairment

`tools/x2_source_impairment.py` flips a bit in one of each six octets of the
symmetric startup source when it goes across the PCMU bearer. (The source is
not transformed on the wire.) To enable it for `tools/probe_imodem_pair.py`,
use `COURIER_X2_SOURCE_IMPAIR=phase[,phase...][:mask]`:

```
COURIER_X2_SOURCE_IMPAIR=2 .venv/bin/python tools/probe_imodem_pair.py --protocol x2 --settings S54=0S58=48 --nvram artifacts/imodem-pair-x2-full-rate-routed-20261002/nvram-230400-switch2.sav --instructions 250000000 --originate-send CALLER-X2 --answer-send ANSWER-X2 --output out
```

Results (`verification.json`):

- Without impairment, the result is 64000/x2 with the host report `006a:1010`.
- LSB flips on phase 2 or phase 5 give 56000/x2 with `006a:0e0e`. The two
  payloads arrive.
- A flip of bit 1 on phase 2 causes the loss of x2 (V.34 at 24000/31200).

Sweep of all six phases (LSB): each phase gives 56000/x2 with `006a:0e0e`. The
frame word `w2` (`((map << 1) & 7e) | 1`) that each end sends is a different
single-bit map: phase 0 `41`, 1 `03`, 2 `05`, 3 `09`, 4 `11`, 5 `21`. We count
the phases from the seventh `7e` of the run.

Multi-phase LSB errors (`COURIER_X2_SOURCE_IMPAIR=0,3` and other values):
`{0,3}`, `{1,2}`, `{0,2,4}` and all six phases connect at 56000/x2 with
`006a:0e0e`. The map word is the bitwise OR of the single-phase words (`49`,
`07`, `55`, `7f`).
