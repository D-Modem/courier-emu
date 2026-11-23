# The time base

The supervisor arms countdowns and waits for them. For example, `ATI11` gives
itself 20 ticks at `0x62d68` before it prints an empty diagnostics page. But
nothing drives these countdowns. The chain that decrements them starts on
vector `0x0f`, and this firmware keeps that vector masked for the full run.
Thus, `ATI10` and `ATI11` stop before they are complete. All other firmware
timeouts wait forever.

`--tick-ms MS` lets you do experiments with that edge. But it obeys the mask.
Thus, now it delivers nothing, and the `ticks` count stays zero. This is
intentional: the board cannot accept an edge that the firmware disabled.

`--tick-source dsp` is the other candidate, and it is the useful one to run. It
paces the chain from the DSP frame interrupt, not from a period. Only this
arrangement keeps the two mutual watchdogs of the firmware quiet. These
watchdogs limit the legal ratio to between 1/25 and 3 ticks for each frame, and
1:1 is in that range. The option is still disabled by default, because 1:1 in
that range is a choice, not a measurement.

With this option, the diagnostics pages complete and the line-detector poller
runs. Also, the harness stops the forgery of the two counters that the poller
feeds. For the behavior of a linked pair in this condition, see "Two instances
on one line". `courier_firmware_analysis.md` has the evidence.
