# ATY4DT123 on emulated 403

We ran the exact command `ATY4DT123` for 80,000,000 supervisor instructions.
The run used the recovered boot ROM, board ID 7, the fixture EEPROM, a 5 ms
tick and a behavioral dial-tone DAA. We did not use a physical modem or an
external call.

Serial response:

```text
CALL PROGRESS
```

The firmware consumed all of the command. It asserted the hook relay of the
panel at instruction 37,704,462. It sent the tag-13 tone-selector commands of
the DSP, `0013:0001`, `0013:0002`, `0013:0003`, one time each. These agree with
digits 1, 2 and 3 in the recovered 3.1.2 tone-selector mapping.

The run stopped at its instruction limit. It did not give a CONNECT or a
terminal failure response. The DSP stayed active, with no error and zero ROM
holes.

The panel reports off-hook, but the behavioral DAA stays idle/on-hook with
zero generated samples. Thus the configured dial-tone source did not get to
the line model on this ROM path. The `dial_digits` summary of the bridge is
also empty. The evidence for the three requested digits is the firmware
mailbox trace, not that helper field. This run does not show emitted DTMF
audio or a working connection.

`report.json` contains the full run. `serial.txt` has the parity-decoded
output. To reproduce it from the repository root, use this command:

```sh
.venv/bin/python artifacts/aty4dt123-403-01/run.py
```
