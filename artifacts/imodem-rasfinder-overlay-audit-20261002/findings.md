# Live RasFinder overlay audit

The repeated call used native firmware. It did not use the foreground overlay assist.
At live completion, all transfers agree exactly with their transported words. These
transfers are the startup destinations d100 (7536 words) and 9260 (16000 words), then the
call overlay a000 (13912 words). The advance of the destination agrees with each transfer.
There are exactly three completed transfers. There are no later overlay requests.

After a000 completes, the firmware executes and changes the native receive
callbacks (93f4, 9406, 941e, 9458, 97b2, 97e1, 97eb, 980a, and other callbacks).
The transmit callbacks go through 9e45 and 9e82 in a cycle, with the sequence pointers
9e0c and 9e08. At 9e45, the native generator sets the polarity state to one
and branches to 9e7a. The code at 9e7a makes a fixed constellation point. At
9e82, the transmit callback returns. These states occur before the later
V.34 S/PP/TRN/J generators that we examined before in the offline pair.

Before the instruction limit, these items do not occur: a 0034 symbol-rate report,
a native retrain report 0006, or a Hayes CONNECT. The overlay is complete and its
training logic runs. A focused trace is still necessary to find the exact receive
detector that is not satisfied. If a subsequent mailbox reply does not occur, do not
interpret this as proof that the loader stopped.
