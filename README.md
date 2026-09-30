# c920-mic-wake

**Fix for a Logitech C920 webcam whose microphone records pure silence on Linux, while the camera and the same mic on Windows work fine.**

If your C920 mic shows up, is unmuted, and meters stay completely flat, check whether the samples are *exactly zero*:

```bash
SRC=$(pactl list sources short | awk '/C920/{print $2; exit}')
timeout 3 pw-record --target "$SRC" /tmp/c920.wav
python3 -c "import wave,array; w=wave.open('/tmp/c920.wav'); a=array.array('h', w.readframes(w.getnframes())); print(sum(1 for x in a if x), 'non-zero samples of', len(a))"
```

A working mic is never exactly zero, even in a silent room. If you get `0 non-zero samples`, this repo is for you.

## What's going on

```
 stuck C920 + Linux driver              ──► all-zero audio            ✗
 read it once "the Windows way" over USB ──► driver takes over again ──► real audio   ✓
```

The webcam got stuck in a state where, under the Linux USB audio driver (`snd-usb-audio`), it
sent pure silence. A USB capture showed every audio packet arriving intact, but full of zeros.
The state survived replugs, a different USB port, three kernels, and a trip to Windows (where the
mic worked anyway, because Windows sets the mic up far more simply).

Streaming the mic once the Windows way, straight over USB, then replaying Linux's setup
requests, cleared it. From then on the normal driver, PipeWire and every app worked, including
after replugs with no fix running.

`c920-mic-wake` replays that clearing sequence automatically on every plug-in and at boot, as a
safeguard. A udev rule runs it. It briefly detaches the audio driver, runs the sequence over raw
USB in about a second, then re-attaches the driver.

The exact trigger isn't confirmed. The strongest lead is that Linux sends the mic's volume
control ten "set resolution" commands at startup, which Windows never sends. See
[`REPORT.md`](REPORT.md) and the draft kernel report
[`UPSTREAM-REPORT-DRAFT.md`](UPSTREAM-REPORT-DRAFT.md).

## Install

```bash
git clone https://github.com/creaseygit/c920-mic-wake
cd c920-mic-wake
./install.sh
```

Check it ran:

```bash
journalctl -o cat | grep c920-mic-wake | tail -1
# c920-mic-wake: woke 1-1 (/dev/bus/usb/001/012): 486/504 then 286/304 packets non-zero during warm-up; snd-usb-audio re-bound
```

To remove it, run `./uninstall.sh`.

**Requirements:** Python 3 (standard library only), systemd and udev. It was built and tested on Arch Linux ([Omarchy](https://omarchy.org)) with PipeWire and kernels 7.1.9, 7.2.3 and 7.2.5.

## What's in here

| File | Purpose |
|---|---|
| [`c920-mic-wake`](c920-mic-wake) | The fix: wakes the mic over raw usbfs, then hands it back to `snd-usb-audio` |
| [`51-c920-mic-wake.rules`](51-c920-mic-wake.rules) | udev rule that runs it on every plug-in (`046d:082d`) |
| [`REPORT.md`](REPORT.md) | The full investigation: every layer tested, the Windows-vs-Linux USB comparison, and the bisect that found the fix |
| [`UPSTREAM-REPORT-DRAFT.md`](UPSTREAM-REPORT-DRAFT.md) | Draft bug report for the Linux kernel sound maintainers (not submitted) |
| [`captures/`](captures) | Decoded Linux and Windows USB traffic for a freshly plugged C920 |
| [`tools/c920-bisect.py`](tools/c920-bisect.py) | Streams the mic the Windows way, then re-adds each request Linux sends, to find which one matters |
| [`tools/parse-usbpcap.py`](tools/parse-usbpcap.py) | Decodes a Windows USBPcap capture into control requests and audio-packet stats |
| [`tools/parse-usbmon.py`](tools/parse-usbmon.py) | Decodes a Linux `usbmon` capture into labelled webcam audio/video requests |

**Hit this yourself?** Capture evidence *before* running the fix; see "If you hit this" in [`REPORT.md`](REPORT.md). A reproducible stuck state is what's needed to get this fixed in the kernel.

## Other webcams

The approach should carry over to other UVC webcams whose mics go silent in the same way: all-zero samples, working on Windows. Change the vendor and product IDs in the udev rule, and check the interface numbers, alt setting and packet size in the script against `lsusb -v`. Reports and PRs are welcome.

## Author

Diagnosed and written by **Paul Oesten** ([@creaseygit](https://github.com/creaseygit)), with Claude Code. MIT licensed.
