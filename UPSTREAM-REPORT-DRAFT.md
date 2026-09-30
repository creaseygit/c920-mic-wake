# DRAFT: report to linux-sound (not submitted)

> **Status: draft only.** It's written for `linux-sound@vger.kernel.org` (Cc: Takashi Iwai), per
> `MAINTAINERS` for `sound/usb/`. Before sending, re-test on the current mainline kernel, and
> ideally on a second C920 unit or firmware revision.

---

**Subject:** `[BUG] ALSA: usb-audio: Logitech C920 (046d:082d) capture stays silent after unmute if stream started while muted`

Hi,

The Logitech HD Pro Webcam C920 (`046d:082d`, bcdDevice 0.11) microphone has a firmware bug in
its UAC1 Feature Unit mute. If the capture stream is started while the Feature Unit mute is
set, clearing the mute afterwards has no effect. The device keeps returning all-zero isochronous
packets, while `GET_CUR` reports mute = 0. Only re-enumeration (replugging) recovers it.

In practice this is easy to hit on a desktop. PipeWire maps the user's mic mute to the ALSA
`Mic Capture Switch`, so "mute, then an app opens the mic, then unmute" leaves the mic dead.

**Reproducer.** The tested version is `tools/c920-repro.sh` in the repo below: amixer plus
`pw-record`, no root, stock snd-usb-audio and PipeWire. Equivalent plain-ALSA form (not run
verbatim; PipeWire must not be holding the device):

```
amixer -c C920 sset Mic nocap          # FU 5 mute = 1
arecord -D hw:C920 -f S16_LE -r 32000 -c 2 -d 2 /dev/null   # start a stream while muted
amixer -c C920 sset Mic cap            # FU 5 mute = 0; GET_CUR confirms 0
arecord -D hw:C920 -f S16_LE -r 32000 -c 2 -d 3 out.wav     # every sample is 0
```

| Sequence | Result |
|---|---|
| mute → unmute while idle | OK |
| mute → unmute while a stream is running | OK (silent while muted, audio resumes) |
| mute → **start stream** → unmute | stuck silent until replug |

The same was confirmed at the USB level, over raw usbfs with snd-usb-audio unbound, `usbmon`
recording: `SET_CUR` mute = 1 → stream → `SET_CUR` mute = 0 → all later iso IN packets on EP 0x82
are all-zero at alt 1 (16 kHz) and alt 3 (32 kHz). The volume, sample rate and resolution
requests the driver sends at probe (including its ten `SET_RES` writes and the sticky-mixer
sweep) did **not** affect it.

Windows didn't touch the Feature Unit mute at all in a USBPcap trace, which fits the webcam
working there.

**Proposed fix:** don't expose the C920's Feature Unit mute. That's the same approach as
5ab3dc647751 ("ALSA: usb-audio: skip the broken mute control on AVerMedia GC553Pro"), for
example a `usbmix_ctl_map` entry for `046d:082d` that ignores unit 5's mute control. Userspace
then falls back to software mute, which works. As a userspace workaround,
`api.alsa.soft-mixer = true` for the device in WirePlumber stops the bug from triggering; this has
been verified.

Tested on kernels 7.1.9-arch1, 7.2.3-arch1 and 7.2.5 (Omarchy build), PipeWire 1.6.8,
WirePlumber 0.5.17, Intel Tiger Lake xHCI.

Reproducer, captures, tools and the full investigation are at
https://github.com/creaseygit/c920-mic-wake

Thanks,
Paul Oesten
