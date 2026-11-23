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
- A live AT console on the firmware of the modem, and a browser console
  (`./courier gui`)
- Two modems on one line (`link`), with Bell 103, V.34 and x2 tests
- A minimal SIP user agent on the modeled DAA
- An experimental line backend for the Apple USB Modem (macOS)
- Tools that read the flash, the RAM and the ASIC ports of a real board

Status: this is research work. The analog 403 firmware negotiates V.34/LAPM
and V.90/LAPM over SIP, and the I-modem connects at V.90 to a RasFinder. The
Quad connects with V.34 and x2. Sustained reliability is not yet solved.
Refer to [Current boundary](docs/current-boundary.md) and
[Research notes](docs/research-log.md).

This repository is a fork of
[cryan209/courier-emu](https://github.com/cryan209/courier-emu).

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

## Licence

AGPL-3.0-only ([LICENSE](LICENSE)), or a commercial licence from the D-Modem Authors ([COMMERCIAL-LICENSE.md](COMMERCIAL-LICENSE.md)). Contributions come with a contributor agreement ([CONTRIBUTING.md](CONTRIBUTING.md)). The firmware images belong to their owners and are not under these terms.
