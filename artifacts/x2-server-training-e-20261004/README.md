# Decoding the server's stretch E with the payload mapper

`analysis.json` is the output of `tools/decode_server_training_e.py` on the octets of the I-modem
(`imodem-tx.g711`, bearer second 11.1639, 10002 symbols = 1667 frames). The octets come from the
53333/x2 analog Courier call. The configuration has six banks of nine entries, B = 19 amplitude
bits and MD = 5 independent signs. With this configuration, each frame reassembles into 24 bits.
These bits descramble with 1 + x^-18 + x^-23 to constant ones over all 1667 frames.
Other MD values give 50 %.
The tool uses only the Python standard library. The capture command is in
`artifacts/x2-courier-phase3-20261004/README.md`.
