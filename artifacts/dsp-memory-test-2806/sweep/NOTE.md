# The sweep's first sample is clobbered

This sweep uses 21 addresses, `--memory-test-addresses`. Sample 0 is "PMST as found". It reads
`5aa5` and not `00b0`. The cause is that this sweep writes its test patterns to data
`0x1000`. That address is `ROM_DUMP_BUFFER`, thus the write goes onto the sample that is already stored.
Only that one word is affected. All the address rows are correct. The value of
`PMST` as found is also in `run-a` and `run-b`, and these runs do not touch `0x1000`.

Before you read data into sample 0 again, move the buffer or remove `0x1000` from the address list.
