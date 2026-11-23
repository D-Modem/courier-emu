# courier-emu

courier-emu is an emulator harness for the firmware of the USRobotics
Courier modems. It runs the original firmware images, so that D-Modem can
do interoperability tests against a Courier without the hardware.

The harness runs the Intel 80186 or 386EX supervisor and the TMS320C5x DSP
of the modem together, and it gives the same result each time. It models
the ASIC, the codec, the DAA, the board latches and the settings EEPROM.
Two instances can share one telephone line, and one instance can dial out
through SIP.

- Analog Couriers (`main211.xmf` and other XMF images), the ISDN I-modem
  (`.nac` and `.xmp` images) and the Quad server modem
- A live AT console on the firmware of the modem
- Two modems on one line (`link`), with Bell 103, V.34 and x2 tests
- A minimal SIP user agent on the modeled DAA
- Tools that read the flash, the RAM and the ASIC ports of a real board

Status: this is research work. The I-modem answers AT commands, and two
modems connect at 300 bit/s with Bell 103. V.34 carrier is not yet solved.
Refer to [Current boundary](docs/current-boundary.md).

## Quick start

You must have Python 3.10 or later. The firmware images are not in the
repository. Put the image that you use in the top folder. Then do these
commands:

```sh
./courier info main211.xmf                       # check and describe an XMF image
./courier isdn-run Ie030002.nac --terminal       # an AT console on the I-modem
```

The `./courier` launcher makes `.venv` at the first start, and installs
the dependencies (Unicorn and Capstone) in it. To exit the terminal, push
Ctrl-].

## Documentation

- [Usage](docs/usage.md): the commands of `./courier`, and their options
- [docs/](docs/README.md): an index of all the technical notes
- [Research notes](docs/research-log.md): the most recent results
- [Firmware catalogue](firmware/README.md): the firmware images and where they come from
- [Experiments](artifacts/README.md): the captured runs and their reports
- [Documentation style](docs/STYLE.md): the rules for ASD-STE100 Simplified Technical English
