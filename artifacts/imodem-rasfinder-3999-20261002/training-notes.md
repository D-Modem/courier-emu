# RasFinder 3999 native I-modem call

Account 2903 made one SIP dialog to 3999. Hunt-group member 8416 answered.
The 49.23-second bearer had 390354 actual RTP octets and 3486 silence-fill
samples (0.89%). The run report shows no SIP BYE, no new INVITE and no second call.
Thus, the tonal restarts that we saw occurred in one telephone
call. They were not new SIP calls. The run stopped at its instruction limit,
without CONNECT or NO CARRIER, and the cleanup hung up the call.

The retained timeline of the DSP gets to V.8 image request `0047:0006` at 9.8835
seconds and to supervisor command `0002:a000` at 9.8870. After these, there are no retained
replies. Thus, there is no symbol-rate report `0034` and no retrain report
`0006`. This does not yet prove the exact location of the stall. To find if the stall is in the overlay
handoff or in the execution after the transfer, a live
audit of the program transfer and state snapshots are necessary. Audio continues in both directions.
Do not automatically apply the verified later J wait of the existing offline pair to this live originate call.
