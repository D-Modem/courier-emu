# Capture artifacts

This directory has the primary evidence from the physical Couriers and from the offline probes. Each
capture directory keeps its own `manifest.json`. That file records the acquisition details,
the hashes and the assumptions. Use that file as the authority for what a capture is.

## Experiment index and local archives

The [Experiment index](experiment-index.md) lists the purposes of the experiments, the result
reports and the storage dispositions. [The machine-readable index](experiment-index.json)
also records the archive locations, the SHA-256 hashes and the cleanup accounting. The purpose
labels come from the directory names. The findings come from the cited reports.

Keep compact findings, verification results, reproduction profiles and
documented primary evidence in Git. Put bulk PCM, packet captures, timelines and
DSP snapshots in compressed archives in `.artifact-archives/` at the
repository root. Git ignores that directory. It is local storage, not a
remote backup. Each archive has a manifest next to it. The manifest contains the archive
checksum, and the path, the size and the SHA-256 hash of each original file.

The archive tool reads back each archived file and verifies its checksum before
it prunes a source. It keeps tracked files, scripts, notes, profiles, small
JSON reports, the selected working and failing controls, and real Courier
captures. It does not touch experiments that changed in the last ten minutes.

```sh
# Inventory only; create no archives and delete nothing.
.venv/bin/python -m tools.archive_artifacts --date 20261002 --date 20261003

# Archive, verify, then prune eligible untracked generated output.
.venv/bin/python -m tools.archive_artifacts \
  --apply --prune --date 20261002 --date 20261003

# Restore an experiment from the archive named in the index.
# Run from the repository root; compare its SHA-256 with the manifest first.
shasum -a 256 .artifact-archives/RUN/EXPERIMENT.tar.gz
tar -xzf .artifact-archives/RUN/EXPERIMENT.tar.gz -C .
```

Some documentation links point to detailed captures that are now in these
archives. To examine those files, restore the related experiment. The
retained tracked reports and summaries are available in a new clone.

| Directory | Contents |
|---|---|
| `courier-board-21210-capture-01/` | Full 512 KiB CPU flash window read from the 20.16 MHz board, with its audit and the check of the recovered handler |
| `courier-board-21210-ram-01/` | Two live passes over physical `00000..0feff` |
| `courier-board-21210-upper-ram-01/` | Two live passes over the `10000..1ffff` window |
| `atg-monitor/` | The first two `ATGLK2=` page reads that we did manually, and their comparisons |
| `io-port-map/` | `ATGLK2B` port-space sweeps from two units, and the output of the static IN/OUT scan |
| `dsp-port-sample-01/` | Repeated reads of the DSP reader ports and of the `0x64`-`0x7e` block from the 20.16 MHz unit |
| `dsp-mailbox-write-01/` | First attempt at a host-to-DSP mailbox write. It wrote the four data registers with no commit on `0x1c`, and it saw nothing. We keep it as the negative result that the protocol work explains |
| `dsp-mailbox-queue-01/`, `dsp-mailbox-queue-02/` | Seeding of the host-to-DSP ring with the commit edge, and the discriminators in `queue-01/followups/`. These keep the one change that we saw without a known cause |
| `dsp-mailbox-command-01/`, `dsp-mailbox-command-02/` | The repeatable host write: null-control and query tags. We fixed each inbound-register prediction from the disassembly before the test, and each one was correct |
| `dsp-mailbox-312-comparison-01/` | The `07, 2d, 62, 07` sequence on the DSP 3.1.2 board, replayed offline through the real dispatcher and sender of that firmware. Before this, we verified seven flash pages byte for byte. The `62` reply is different (hardware `0015`, emulator `0012`). We keep this difference visible and do not adjust the model to it |
| `dsp-window-pump-01/` | Tag `06` armed and pumped. The channel responds, but its sources are empty on an idle unit |
| `dsp-window-pump-02/`, `dsp-window-pump-03/` | Tag `46` pumped: sixteen words. The first four are DSP **program** memory, and they are the same as the flash image at addresses that we predicted before the test. They come from the V.34 carrier and symbol-rate table. Thus, the window reports which of the two the datapump uses |
| `dsp-window-pump-312-01/` | The tag `06` window on the 3.1.2 board: seven words, all zero on an idle unit, with `1c` bit 2 that marks the sequence length. This is the run that derived again the 7.4.16 chain vector `[0x01cd]` and confirmed it live |
| `dsp-window-index-01/` | Tag `48` writes `ffb1` all-ones before tag `46` is armed. The index stays `0`, because the other AND terms are call-setup state |
| `dsp-window-stream-01/` | The live state of the `0x60`/`0x62` chain. It also shows that tag `06` arms the DSP streamer but does not send |
| `audio-312-01/` | All 16 DTMF pairs, rendered by the selector, the oscillator, the mixer and the serial ISR of DSP 3.1.2. It has the spectra for each digit, the PCM hashes and the serial counters. It also has the five flash pages read back from the board, which are the same as the captured ROM. The WAV is in `.gitignore`. The command in `docs/audio-312-path.md` makes it again. Its 7200 Hz rate is an inference from the phase increments. It is not measured |
| `audio-312-hardware-01/`, `-02/` | Two attempts to make a call to an Asterisk echo test, to record a physical waveform. No attempt opened a channel before the limited timeout. We stopped the two attempts, then sent `ATH` and a successful `AT`. Nothing was recorded, and no PBX configuration changed. We keep this as the negative result. The physical comparison is still open |
| `dil-alaw-01/` | A V.90 DIL sent downstream in answer to the Ja of this Courier, in G.711 A-law. 197 segments x 66 symbols. Each segment has the level of the Ucode that the firmware generates for it. The user supplied this capture. We did not make it here |
| `dil-ulaw-impaired-01/` | The same DIL received with impairments: a 6 dB digital pad and additive noise. The signs are correct. The impairment is flat across all six data-frame intervals, thus it is not robbed-bit signalling. `courier_emu.vpcm.score_dil` scores it |
| `host-ram-rate-01/` | Timed reads of the host RAM pages that change on an idle unit, with a rate fitted to each 16-bit cell. There is one counter, `0x012a` at 200.00 Hz (the 5 ms tick). Nothing runs at an audio rate |
| `io-latch-bit2-01/` | Port `0x14` bit 2 probe |
| `dsp-rom-probe-v1/`, `dsp-rom-transport-v*/` | Offline probe and transport builds. No hardware was used |
| `sdl-image-extraction-01/` | Firmware recovered from the vendor SDL packages in `docs/usrdl/`. It has the 16-byte download-record format of the loaders and the XOR 0x55 of the XMD. It also has the string comparison that shows that the Sportster Vi DSVD is a reduced Courier. The images do not have accurate flash addresses, because the record addresses are 16-bit and wrap. They are not tracked. No hardware was used |

## What is not tracked

`.gitignore` excludes two intermediate directories, one entry for each page:

- `responses/` — one raw serial reply for each page request
- `blocks/` — the verified 256-byte pages

Together, they are about 32 MB across 8,200 files. All their contents can be
reconstructed from the assembled images and `pages.jsonl`, which are tracked.

Thus, **`audit_capture.py` cannot run from a new clone**. It
parses `responses/` again and compares them with `blocks/`. It works only in a
working tree that still has the original capture output. The assembled images,
the hashes of each page in `pages.jsonl`, and the final hashes in `manifest.json` and
`audit.json` are tracked. Thus, you can still verify the images independently
without those directories.
