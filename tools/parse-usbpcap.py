#!/usr/bin/env python3
# Decode a USBPcap (linktype 249) capture: list control requests sent to each device and
# summarise isochronous IN data (zero vs non-zero) per device/endpoint.
# Usage: python3 parse-usbpcap.py capture.pcap [--all]   (capture made with USBPcapCMD on Windows)
import struct, sys, collections

f = open(sys.argv[1], "rb").read()
magic, _, _, _, _, snap, link = struct.unpack("<IHHiIII", f[:24])
assert link == 249, f"linktype {link}"
off = 24
REQ = {0: "GET_STATUS", 1: "CLEAR_FEATURE", 3: "SET_FEATURE", 5: "SET_ADDRESS", 6: "GET_DESCRIPTOR",
       8: "GET_CONFIGURATION", 9: "SET_CONFIGURATION", 10: "GET_INTERFACE", 11: "SET_INTERFACE"}
UAC = {0x01: "SET_CUR", 0x81: "GET_CUR", 0x82: "GET_MIN", 0x83: "GET_MAX", 0x84: "GET_RES"}
iso = collections.defaultdict(lambda: [0, 0, 0])   # (dev,ep) -> [packets, nonzero packets, bytes]
t0 = None
ctl = []
while off + 16 <= len(f):
    ts_s, ts_us, incl, orig = struct.unpack("<IIII", f[off:off + 16]); off += 16
    rec = f[off:off + incl]; off += incl
    t = ts_s + ts_us / 1e6; t0 = t0 or t
    hlen, irp, status, func, info, bus, dev, ep, xfer, dlen = struct.unpack("<HQIHBHHBBI", rec[:27])
    data = rec[hlen:]
    if xfer == 2:  # control
        stage = rec[27]
        if stage == 0 and len(data) >= 8:  # SETUP
            bm, br, wv, wi, wl = struct.unpack("<BBHHH", data[:8])
            typ = (bm >> 5) & 3
            name = REQ.get(br, f"req{br:#x}") if typ == 0 else (UAC.get(br, f"class{br:#x}") if typ == 1 else f"VENDOR{br:#x}")
            ctl.append([t - t0, dev, bm, br, wv, wi, wl, name, None])
        elif stage == 2 and ctl and ctl[-1][1] == dev and ctl[-1][8] is None:  # DATA stage payload
            ctl[-1][8] = data[:16].hex()
        elif stage == 3 and ctl and ctl[-1][1] == dev and ctl[-1][8] is None and (info & 1):  # completion w/ data
            ctl[-1][8] = data[:16].hex() if data else ""
    elif xfer == 0 and (ep & 0x80) and (info & 1):  # iso IN completion
        start, npk, errc = struct.unpack("<III", rec[27:39])
        s = iso[(dev, ep)]
        for i in range(npk):
            po, pl, ps = struct.unpack("<III", rec[39 + 12 * i:51 + 12 * i])
            s[0] += 1
            if pl:
                chunk = data[po:po + pl]; s[2] += pl
                if any(chunk): s[1] += 1

print("== control requests (non-standard-descriptor noise trimmed) ==")
for t, dev, bm, br, wv, wi, wl, name, payload in ctl:
    if name == "GET_DESCRIPTOR" and "--all" not in sys.argv:
        continue
    print(f"{t:8.3f}s dev{dev:<3} bm={bm:#04x} {name:<17} wValue={wv:#06x} wIndex={wi:#06x} wLen={wl:<4} {payload or ''}")
print("\n== isochronous IN data ==")
for (dev, ep), (n, nz, b) in sorted(iso.items()):
    print(f"dev{dev} ep{ep:#04x}: packets={n} non-zero packets={nz} bytes={b}")
