# c920-mic-wake

**Fix for a Logitech C920 webcam whose microphone records pure silence on Linux, while the camera and the same mic on Windows work fine.**

If your C920 mic shows up, is unmuted, and meters stay completely flat, check whether the samples are *exactly zero*:

```bash
SRC=$(pactl list sources short | awk '/C920/{print $2; exit}')
timeout 3 pw-record --target "$SRC" /tmp/c920.wav
python3 -c "import wave,array; w=wave.open('/tmp/c920.wav'); a=array.array('h', w.readframes(w.getnframes())); print(sum(1 for x in a if x), 'non-zero samples of', len(a))"
```

A working mic is never exactly zero, even in a silent room. If you get `0 non-zero samples`, this repo is for you. **Replugging the webcam brings it back**; the fix below stops it happening again.

## The cause

It's a firmware bug in the C920 (`046d:082d`):

> If the mic **starts streaming while the webcam's hardware mute is on**, then after unmuting it keeps sending pure silence, while reporting itself as unmuted. It stays that way until it's replugged.

```
 mute on ──► app opens the mic ──► unmute ──► "unmuted", but all-zero audio   ✗  (until replug)
 mute on/off while idle, or mid-call                                 ──► fine   ✓
```

On Linux, PipeWire normally passes the desktop's mic mute (a keyboard mute key, a status-bar mic toggle, `pactl set-source-mute`, `pavucontrol`) to the webcam's hardware mute when the webcam has one. So "mute, then join a call or open a recorder, then unmute" is enough to trigger it. In our Windows USB capture, Windows never touched the webcam's mute at all, which fits the same webcam working there.

Reproduce it in about 10 seconds, without root: [`tools/c920-repro.sh`](tools/c920-repro.sh).

## The fix

A one-file WirePlumber rule ([`51-c920-soft-mixer.conf`](51-c920-soft-mixer.conf)) that makes PipeWire handle the C920's mute and volume in software (`api.alsa.soft-mixer = true`), so the webcam's buggy hardware mute is never used. It needs no root.

```bash
git clone https://github.com/creaseygit/c920-mic-wake
cd c920-mic-wake
./install.sh          # then replug the webcam once if the mic is currently silent
```

Verified: with the rule active, the exact trigger (mute → start mic → unmute) leaves the mic working, with 286,429 of 286,720 samples non-zero. The webcam's hardware switch stayed unmuted throughout.

To remove it, run `./uninstall.sh`.

**Requirements:** PipeWire with WirePlumber 0.5+. Built and tested on Arch Linux ([Omarchy](https://omarchy.org)), PipeWire 1.6.8, WirePlumber 0.5.17, kernels 7.1.9, 7.2.3 and 7.2.5.

### Optional: the plug-in wake-up script

[`c920-mic-wake`](c920-mic-wake) came first, before the cause was known. It's a udev-triggered script that briefly takes the mic from the kernel driver on every plug-in and runs a known-good "wake-up" sequence over raw USB. Replugging alone already clears the stuck state, so you don't need it with the WirePlumber rule. It's kept for reference and for setups without WirePlumber: `./install.sh --with-wake`.

## What's in here

| File | Purpose |
|---|---|
| [`51-c920-soft-mixer.conf`](51-c920-soft-mixer.conf) | **The fix**: WirePlumber rule that uses software mute and volume for the C920 |
| [`tools/c920-repro.sh`](tools/c920-repro.sh) | Reproduces the bug in about 10 s through the normal ALSA/PipeWire stack |
| [`REPORT.md`](REPORT.md) | The full investigation, from "all zeros" to the proven trigger |
| [`UPSTREAM-REPORT-DRAFT.md`](UPSTREAM-REPORT-DRAFT.md) | Draft bug report and proposed kernel quirk for the Linux sound maintainers (not submitted) |
| [`captures/`](captures) | Decoded Linux and Windows USB traffic for a freshly plugged C920 |
| [`tools/c920-rebreak.py`](tools/c920-rebreak.py) | Sends suspect requests one at a time over raw USB; this is what found the trigger |
| [`tools/c920-bisect.py`](tools/c920-bisect.py) | Streams the mic the Windows way, then re-adds Linux's setup requests |
| [`tools/parse-usbmon.py`](tools/parse-usbmon.py), [`tools/parse-usbpcap.py`](tools/parse-usbpcap.py) | Decoders for Linux `usbmon` and Windows USBPcap captures |
| [`c920-mic-wake`](c920-mic-wake), [`51-c920-mic-wake.rules`](51-c920-mic-wake.rules) | The optional plug-in wake-up script and its udev rule |

## Other webcams

Other webcams whose mics go silent after an unmute may have the same bug. Try `tools/c920-repro.sh` with the device name changed. If it reproduces, the same WirePlumber rule with your device's name should fix it. Reports and PRs are welcome.

## Author

Diagnosed and written by **Paul Oesten** ([@creaseygit](https://github.com/creaseygit)), with Claude Code. MIT licensed.
