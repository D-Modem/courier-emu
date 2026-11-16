# Original client record verification

To get the same results again, run `.venv/bin/python tools/trace_x2_client_record.py`.
For the interpretation of the fields and the limits, refer to `docs/x2-client-record-production.md`.
The JSON keeps these four items separate:

- The packing of the host diagnostics.
- The rate selection of the peer.
- The interoperability of the original serializer.
- The construction of the position report of variable length.

The firmware images are local originals. We do not claim to have vendor source.
