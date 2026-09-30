#!/usr/bin/env python3
# Decode a Linux usbmon text capture (/sys/kernel/debug/usb/usbmon/<bus>u) into the control
# requests sent to one device, labelled for a UAC1 webcam (C920 layout), plus iso-IN data stats.
# Usage: python3 parse-usbmon.py capture.txt <devnum> [--all]
import collections, sys

path, dev = sys.argv[1], int(sys.argv[2])
STD = {0x09: "SET_CONFIGURATION", 0x0B: "SET_INTERFACE", 0x06: "GET_DESCRIPTOR"}
UAC = {0x01: "SET_CUR", 0x04: "SET_RES", 0x81: "GET_CUR", 0x82: "GET_MIN", 0x83: "GET_MAX", 0x84: "GET_RES",
       0x85: "GET_LEN(uvc)", 0x86: "GET_INFO(uvc)", 0x87: "GET_DEF(uvc)"}
IFACE = {0: "video-control", 1: "video-stream", 2: "audio-control", 3: "audio-stream"}
iso = collections.Counter()
t0 = None
for line in open(path):
    f = line.split()
    if len(f) < 4 or not f[3][:2] in ("Ci", "Co", "Zi"):
        continue
    kind, bus, d, ep = f[3][:2], *f[3][3:].split(":")
    if int(d) != dev:
        continue
    t = int(f[1]) / 1e6
    t0 = t0 if t0 is not None else t
    if kind == "Zi" and f[2] == "C":
        iso["packets"] += 1
        data = line.split("=", 1)[1].split() if "=" in line else []
        iso["non-zero"] += any(int(w, 16) for w in data)
        continue
    if f[2] != "S" or f[4] != "s":
        continue
    bm, br, wv, wi, wl = (int(x, 16) for x in f[5:10])
    payload = line.split("=", 1)[1].strip() if "=" in line else ""
    typ = (bm >> 5) & 3
    if typ == 0:
        name = STD.get(br, f"std{br:#x}")
        if name == "GET_DESCRIPTOR" and "--all" not in sys.argv:
            continue
    else:
        name = UAC.get(br, f"class{br:#x}")
    recip = bm & 0x1F
    if recip == 2:
        target = f"endpoint {wi:#04x}"
    else:
        ifn, unit = wi & 0xFF, wi >> 8
        target = IFACE.get(ifn, f"iface {ifn}") + (f" unit {unit}" if unit else "")
    what = ""
    if name == "SET_INTERFACE":
        what = f"alt {wv}"
    elif recip == 2 and wv >> 8 == 1:
        what = "sample rate" + (f" = {int.from_bytes(bytes.fromhex(payload.replace(' ', '')), 'little')} Hz" if payload else "")
    elif wi == 0x0502:
        cs = {1: "mute", 2: "volume"}.get(wv >> 8, f"cs{wv >> 8}")
        what = cs + (f" = {payload}" if payload else "")
    else:
        what = f"wValue={wv:#06x}" + (f" data={payload}" if payload else "")
    print(f"{t - t0:8.3f}s  {name:<17} {target:<24} {what}")
print(f"\niso IN packets: {iso['packets']}  non-zero (first 32 bytes shown by usbmon): {iso['non-zero']}")
