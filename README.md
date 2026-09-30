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
 plug in ──► snd-usb-audio sets the mic up ──► C920 streams all-zero audio   ✗
 plug in ──► read it once "the Windows way" ──► snd-usb-audio takes over ──► real audio   ✓
```

When a freshly plugged-in C920 is set up by the Linux USB audio driver (`snd-usb-audio`), the webcam itself sends silence. A USB capture shows every audio packet arriving intact, but full of zeros. Windows sets the mic up differently: it just selects the 16 kHz audio mode and starts reading. Doing that once from Linux "wakes" the mic, and from then on the normal driver, PipeWire and every app work as expected.

`c920-mic-wake` does that automatically. A udev rule runs it every time the C920 is plugged in, and at boot. It briefly detaches the audio driver, reads half a second of audio directly over USB, then re-attaches the driver. The whole thing takes about a second.

## Install

```bash
git clone https://github.com/creaseygit/c920-mic-wake
cd c920-mic-wake
./install.sh
```

Check it ran:

```bash
journalctl -o cat | grep c920-mic-wake | tail -1
# c920-mic-wake: woke 1-1 (/dev/bus/usb/001/010): 486/504 packets non-zero during warm-up; snd-usb-audio re-bound
```

To remove it, run `./uninstall.sh`.

**Requirements:** Python 3 (standard library only), systemd and udev. It was built and tested on Arch Linux ([Omarchy](https://omarchy.org)) with PipeWire and kernels 7.1.9, 7.2.3 and 7.2.5.

## What's in here

| File | Purpose |
|---|---|
| [`c920-mic-wake`](c920-mic-wake) | The fix: wakes the mic over raw usbfs, then hands it back to `snd-usb-audio` |
| [`51-c920-mic-wake.rules`](51-c920-mic-wake.rules) | udev rule that runs it on every plug-in (`046d:082d`) |
| [`REPORT.md`](REPORT.md) | The full investigation: every layer tested, the Windows-vs-Linux USB comparison, and the bisect that found the fix |
| [`tools/c920-bisect.py`](tools/c920-bisect.py) | Streams the mic the Windows way, then re-adds each request Linux sends, to find which one matters |
| [`tools/parse-usbpcap.py`](tools/parse-usbpcap.py) | Decodes a Windows USBPcap capture into control requests and audio-packet stats |

## Other webcams

The approach should carry over to other UVC webcams whose mics go silent in the same way: all-zero samples, working on Windows. Change the vendor and product IDs in the udev rule, and check the interface numbers, alt setting and packet size in the script against `lsusb -v`. Reports and PRs are welcome.

## Author

Diagnosed and written by **Paul Oesten** ([@creaseygit](https://github.com/creaseygit)), with Claude Code. MIT licensed.
