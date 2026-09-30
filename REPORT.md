# Report: Logitech C920 microphone records silence on Linux

**Date:** 30 September 2026
**Device:** Logitech HD Pro Webcam C920, USB ID `046d:082d`, firmware `bcdDevice 0.11`
**Host:** Intel Tiger Lake laptop (xHCI), Arch Linux / Omarchy 4, PipeWire 1.6.8, WirePlumber 0.5.17
**Kernels tested:** 7.1.9-arch, 7.2.3-arch, 7.2.5-omarchy
**Status:** worked around with `c920-mic-wake`. The root cause is inside the webcam's response to the Linux driver's setup sequence.

---

## 1. Symptom

- The camera worked. The mic appeared in PipeWire, was the default input, and was unmuted.
- Apps (Teams in Chrome) and level meters showed nothing from it.
- Recording the mic produced **exactly zero** in every sample, not just quiet audio.
- The same webcam's mic worked on a Windows laptop.
- It had previously worked on this Linux machine.

## 2. What was ruled out

Each step was checked by measuring the recorded samples, not by watching a level meter.

| # | Test | Result |
|---|---|---|
| 1 | PipeWire source mute and volume | Unmuted, 44% → still all zeros |
| 2 | Cycling the card profile in PipeWire | All zeros |
| 3 | `arecord -D hw:…` straight from ALSA, PipeWire out of the way, at 16, 24 and 32 kHz | All zeros at every rate |
| 4 | ALSA `Mic Capture Switch` toggled and `Mic Capture Volume` at maximum | All zeros |
| 5 | Physical replug, and a different USB port | All zeros |
| 6 | USB autosuspend disabled for the device (udev `power/control=on`) | All zeros |
| 7 | Unloading every app that might hold the mic (e.g. Buzz) | All zeros |
| 8 | Kernel 7.2.5-omarchy → 7.2.3-arch → 7.1.9-arch | All zeros on all three |
| 9 | Camera streaming at the same time (LED on, 76+ frames captured) | All zeros |
| 10 | `snd_usb_audio` quirk flags applied live and re-probed: `SET_IFACE_FIRST`, `FORCE_IFACE_RESET`, `IFACE_DELAY`, skip `GET_SAMPLE_RATE`, `CTL_MSG_DELAY_5M`, and all combined | All zeros on every combination |

The kernel's USB-audio quirk table has no C920-specific entry, only the Logitech-wide `CTL_MSG_DELAY_1M`. The kernel log showed no errors, and no "sticky mixer" messages from the 7.1/7.2 mixer changes.

## 3. Microscope: what the webcam actually sends

### 3a. Linux USB capture (`usbmon`)

With the camera on and the user talking, the webcam's isochronous audio endpoint (`0x82`) delivered **5,999 packets, all completed without error, and every one of them all zeros**. Video packets on endpoint `0x81` flowed normally. So the kernel wasn't dropping audio: the device itself was sending silence.

### 3b. The device's real control state, read over raw usbfs

With the driver detached, `GET_CUR`/`MIN`/`MAX`/`RES` read directly from the device's Feature Unit (ID 5):

```
ch0/1/2: MUTE=0  VOL CUR=36.0 dB (range 20–50 dB, 2 dB steps)
Endpoint 0x82 sample rate: 32000
```

Everything was normal: unmuted, a sensible gain, and a valid rate. Writing the same values back changed nothing.

### 3c. Windows USB capture (USBPcap), with a replug

Decoded with [`tools/parse-usbpcap.py`](tools/parse-usbpcap.py). From plug-in to recording, Windows sent:

```
SET_CONFIGURATION 1
SET_INTERFACE  iface 1 alt 0     (video)
SET_INTERFACE  iface 3 alt 0     (audio streaming idle)
... UVC video control reads only ...
SET_INTERFACE  iface 3 alt 1     (16 kHz)   ← start recording
SET_INTERFACE  iface 3 alt 0                ← stop
```

It sent **no audio class requests at all**: no sample-rate `SET_CUR` on the endpoint, no mute and no volume. Audio endpoint result: **9,150 packets, 9,022 non-zero**. The camera LED stayed off; the mic doesn't need the camera running.

Linux's `snd-usb-audio`, by contrast, reads and writes the Feature Unit at probe (including a volume sweep to detect "sticky" mixers), sets the endpoint sample rate, and defaults to alt 3 (32 kHz).

## 4. Bisect: reproduce Windows on Linux, then add Linux's requests back

With [`tools/c920-bisect.py`](tools/c920-bisect.py), the approach was:

1. Unload `snd_usb_audio` and block it from auto-loading.
2. Replug the webcam, so the driver never touches its audio side.
3. Stream over raw usbfs the Windows way, then add each request Linux sends, one at a time.

```
1. Windows way: select 16k mode, read (no class requests)  non-zero=1990/2008  -> SOUND
2. + GET sample rate                                       non-zero=1990/2008  -> SOUND
3. + SET sample rate 16000 (Linux always does this)        non-zero=1990/2008  -> SOUND
4. + unmute write                                          non-zero=1990/2008  -> SOUND
5. + volume read                                           non-zero=1982/2000  -> SOUND
6. + volume max/min/36dB sweep (sticky-mixer probe)        non-zero=1991/2008  -> SOUND
7. read again after all of the above                       non-zero=1982/2000  -> SOUND
```

After that sequence, reloading `snd-usb-audio` and recording through PipeWire gave **371,207 non-zero samples of 372,736**. The mic worked through the normal stack.

## 5. Conclusion

- A freshly plugged-in C920 on this machine goes silent when `snd-usb-audio` is the first thing to configure its audio.
- Once the mic has streamed once the Windows way (alt 1, before any class requests), it stays awake, and none of the driver's later requests silence it again.
- The exact trigger within the driver's first setup isn't pinned down. It's somewhere in probe-time requests made before the first stream, not any single request tested in isolation after a wake-up. This bisect didn't cover the driver's alt 3 (32 kHz) default as the *first* stream.

## 6. Fix

[`c920-mic-wake`](c920-mic-wake), run by [`51-c920-mic-wake.rules`](51-c920-mic-wake.rules) via `systemd-run` on every `add` event for `046d:082d`, including at boot:

1. Wait for `snd-usb-audio` to finish probing.
2. Unbind it from the audio interfaces.
3. Claim them over usbfs, select alt 1, and stream isochronous IN for 0.5 s.
4. Return to alt 0, release the interfaces, and re-bind `snd-usb-audio`.

Verified after a real replug: the warm-up logged 486/504 packets non-zero, and PipeWire then recorded **373,084 non-zero samples of 374,784**.

## 7. Side findings

- **Bluetooth earbuds show no level in `pavucontrol`, but work on calls.** This is expected: in A2DP (music) mode there's no mic. Apps like Teams switch the earbuds to HFP (headset) mode when a call starts.
- **Level meters are a poor diagnostic** for this class of fault. Count non-zero samples instead.

## Possible next steps upstream

- Capture the driver's probe sequence with `usbmon` on a fresh plug, then replay it request by request against a freshly plugged webcam, to find the exact trigger.
- If one specific request is confirmed, propose a `snd-usb-audio` quirk for `046d:082d` to linux-sound.

---

Investigated by **Paul Oesten** ([@creaseygit](https://github.com/creaseygit)) with Claude Code.
