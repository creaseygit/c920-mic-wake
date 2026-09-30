# DRAFT: report to linux-sound (not submitted)

> **Status: draft only.** It's written for `linux-sound@vger.kernel.org` (Cc: Takashi Iwai), per
> `MAINTAINERS` for `sound/usb/`. Before sending, re-check against the current kernel, trim it,
> and ideally reproduce the fault from a known starting state (see "What would make this
> actionable" below).

---

**Subject:** `[BUG] ALSA: usb-audio: Logitech C920 (046d:082d) mic stuck returning all-zero samples; cleared by a plain alt-1 stream`

Hi,

A Logitech HD Pro Webcam C920 (`046d:082d`, bcdDevice 0.11) microphone got into a state where
every isochronous IN packet carried all-zero samples under snd-usb-audio. The mic worked on
Windows during the same period. The state survived physical replugs, a different USB port, and
kernels 7.1.9-arch1, 7.2.3-arch1 and 7.2.5 (Omarchy build).

**Observations while stuck**

- `usbmon`: 5,999 completed iso IN packets on EP 0x82 at alt 3 (32 kHz), all zero. There were
  no errors and video on EP 0x81 was normal.
- Reading the Feature Unit (id 5) directly over usbfs with the driver unbound: mute = 0,
  volume CUR 0x2400 (36 dB), MIN 0x1400, MAX 0x3200, RES 0x0200, EP rate 32000. All sane.
- Quirk flags tried live (write `quirk_flags`, re-probe): `SET_IFACE_FIRST`,
  `FORCE_IFACE_RESET`, `IFACE_DELAY`, `GET_SAMPLE_RATE`, `CTL_MSG_DELAY_5M`, and all
  combined. The mic still returned all zeros.

**Windows, fresh plug (USBPcap)**

Windows sends **no** audio class requests. It uses `SET_INTERFACE 3/0`, then `3/1` to record
and `3/0` to stop. Result: 9,022 of 9,150 iso packets non-zero.

**Linux, fresh plug (usbmon, captured after the fault had cleared)**

Linux cycles alt 1/2/3, each with endpoint `SET_CUR` for the sample rate. Then, on FU 5
volume: `GET_MAX`, `GET_MIN`, `GET_RES`, then **`SET_RES 0x0001` ten times**, `GET_RES`, then
`SET_CUR` 0x1400/0x2c00/0x2a00 (the sticky-mixer check), then 0x2400. The full decode is in
`captures/linux-driver-setup-fresh-plug.txt` in the repo linked below.

**What cleared it**

With snd_usb_audio unloaded and blocked from auto-loading, and the webcam replugged, I used
usbfs to claim interfaces 2 and 3 and stream alt 1 with no class requests first: the mic had
sound. Adding GET/SET rate, unmute, GET volume and a volume max/min/mid sweep, each followed by
a stream, still gave sound. After reloading snd-usb-audio, the mic worked through ALSA and
PipeWire. It has since kept working across replugs **without** any workaround.

**Suspects (unconfirmed)**

1. The ten `SET_RES` writes to the FU volume control at probe. Windows never sends them. If
   the firmware ever persists a resolution it accepted, a bad value could plausibly leave the
   gain stage producing zeros. (RES read back as 0x0200 while stuck, so this is speculative.)
2. The device's first post-enumeration stream being alt 3 rather than alt 1.

**What would make this actionable**

A way to put the device back into the stuck state. I no longer can: it has stayed good since
it was cleared. If anyone else hits the same symptom (all-zero samples, works on Windows),
please capture `usbmon` from plug-in and try the repo's `tools/c920-bisect.py` *before*
anything else touches the device.

The workaround, captures and tools are at https://github.com/creaseygit/c920-mic-wake

Thanks,
Paul Oesten
