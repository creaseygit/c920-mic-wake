#!/usr/bin/env python3
# Stream the C920 mic "the Windows way" via raw usbfs (snd-usb-audio must not own the interfaces),
# then re-test after adding back each class request Linux sends, to find the one that silences it.
# Usage (root, with snd-usb-audio unloaded and blocked from auto-loading, webcam freshly re-plugged):
#   sudo python3 c920-bisect.py /dev/bus/usb/BBB/DDD
import ctypes, fcntl, os, struct, sys, time

DEV = sys.argv[1]
AS_IF, AC_IF, FU, EP = 3, 2, 5, 0x82
NPK, PKT = 8, 68                      # altset 1 = 16 kHz stereo s16, wMaxPacketSize 68

SETINTERFACE, CLAIM, RELEASE = 0x80085504, 0x8004550F, 0x80045510
SUBMITURB, REAPURB, CONTROL, DISCARD = 0x8038550A, 0x4008550C, 0xC0185500, 0x0000550B

class IsoDesc(ctypes.Structure):
    _fields_ = [("length", ctypes.c_uint), ("actual_length", ctypes.c_uint), ("status", ctypes.c_uint)]
class Urb(ctypes.Structure):
    _fields_ = [("type", ctypes.c_uint8), ("endpoint", ctypes.c_uint8), ("status", ctypes.c_int),
                ("flags", ctypes.c_uint), ("buffer", ctypes.c_void_p), ("buffer_length", ctypes.c_int),
                ("actual_length", ctypes.c_int), ("start_frame", ctypes.c_int),
                ("number_of_packets", ctypes.c_int), ("error_count", ctypes.c_int),
                ("signr", ctypes.c_uint), ("usercontext", ctypes.c_void_p),
                ("iso", IsoDesc * NPK)]
class Ctrl(ctypes.Structure):
    _fields_ = [("bRequestType", ctypes.c_uint8), ("bRequest", ctypes.c_uint8), ("wValue", ctypes.c_uint16),
                ("wIndex", ctypes.c_uint16), ("wLength", ctypes.c_uint16), ("timeout", ctypes.c_uint32),
                ("data", ctypes.c_void_p)]
assert ctypes.sizeof(Urb) - NPK * 12 == 56 and ctypes.sizeof(Ctrl) == 24

fd = os.open(DEV, os.O_RDWR)
libc = ctypes.CDLL(None, use_errno=True)
libc.ioctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_void_p]
def pioctl(req, ptr):
    if libc.ioctl(fd, req, ptr) < 0:
        e = ctypes.get_errno(); raise OSError(e, os.strerror(e))

def ctl(rt, req, val, idx, payload=b"", length=0):
    buf = ctypes.create_string_buffer(payload, max(len(payload), length, 1))
    c = Ctrl(rt, req, val, idx, max(len(payload), length), 1000, ctypes.addressof(buf))
    try:
        n = fcntl.ioctl(fd, CONTROL, c)
        return buf.raw[:n] if rt & 0x80 else "ok"
    except OSError as e:
        return f"ERR {os.strerror(e.errno)}"

def setalt(alt):
    fcntl.ioctl(fd, SETINTERFACE, struct.pack("II", AS_IF, alt))

REAPURBNDELAY = 0x4008550D

def stream(seconds=2.0):
    """Read iso packets for `seconds`; return (packets, non-zero packets, peak)."""
    by_addr = {}
    for _ in range(4):
        b = ctypes.create_string_buffer(NPK * PKT)
        u = Urb(type=0, endpoint=EP, flags=2, buffer=ctypes.addressof(b), buffer_length=NPK * PKT,
                number_of_packets=NPK)
        for i in range(NPK):
            u.iso[i].length = PKT
        by_addr[ctypes.addressof(u)] = (u, b)
        pioctl(SUBMITURB, ctypes.addressof(u))
    n = nz = peak = 0
    end = time.time() + seconds
    ptr = ctypes.c_void_p()
    while True:
        pioctl(REAPURB, ctypes.addressof(ptr))
        u, b = by_addr[ptr.value]
        raw = b.raw
        for i in range(NPK):
            al = u.iso[i].actual_length
            chunk = raw[i * PKT:i * PKT + al]
            n += 1
            if any(chunk):
                nz += 1
                vals = struct.unpack(f"<{al // 2}h", chunk[:al // 2 * 2])
                peak = max(peak, max(abs(x) for x in vals))
            u.iso[i].actual_length = 0
            u.iso[i].status = 0
        if time.time() > end:
            break
        pioctl(SUBMITURB, ctypes.addressof(u))
    for addr in by_addr:                 # cancel whatever is still in flight
        try: pioctl(DISCARD, addr)
        except OSError: pass
    deadline = time.time() + 1           # drain without blocking
    while time.time() < deadline:
        try: pioctl(REAPURBNDELAY, ctypes.addressof(ptr))
        except OSError: time.sleep(0.02)
    return n, nz, peak

def run(label, prep=None):
    setalt(0)
    if prep:
        prep()
    setalt(1)
    time.sleep(0.2)
    n, nz, pk = stream()
    setalt(0)
    verdict = "SOUND" if nz else "SILENT"
    print(f"{label:<58} packets={n:<5} non-zero={nz:<5} peak={pk/327.68:5.1f}%  -> {verdict}", flush=True)

fcntl.ioctl(fd, CLAIM, struct.pack("I", AS_IF))
fcntl.ioctl(fd, CLAIM, struct.pack("I", AC_IF))

fu = lambda cs, ch=0: (cs << 8) | ch, (FU << 8) | AC_IF
def set_rate():  print("   rate SET_CUR 16000:", ctl(0x22, 0x01, 0x0100, EP, (16000).to_bytes(3, "little")))
def get_rate():
    r = ctl(0xA2, 0x81, 0x0100, EP, length=3)
    print("   rate GET_CUR:", int.from_bytes(r, "little") if isinstance(r, bytes) else r)
def unmute():    print("   mute SET_CUR 0:", ctl(0x21, 0x01, 0x0100, (FU << 8) | AC_IF, b"\x00"))
def vol_sweep():
    for v in (12800, 5120, 9216):     # max, min, back to 36 dB: what the sticky-mixer probe does
        print(f"   vol SET_CUR {v}:", ctl(0x21, 0x01, 0x0200, (FU << 8) | AC_IF, struct.pack("<h", v)))
def vol_get():
    r = ctl(0xA1, 0x81, 0x0200, (FU << 8) | AC_IF, length=2)
    print("   vol GET_CUR:", r.hex() if isinstance(r, bytes) else r)

print("TALK continuously while these run.\n", flush=True)
run("1. Windows way: select 16k mode, read (no class requests)")
run("2. + GET sample rate", get_rate)
run("3. + SET sample rate 16000 (Linux always does this)", set_rate)
run("4. + unmute write", unmute)
run("5. + volume read", vol_get)
run("6. + volume max/min/36dB sweep (sticky-mixer probe)", vol_sweep)
run("7. read again after all of the above")

fcntl.ioctl(fd, RELEASE, struct.pack("I", AS_IF))
fcntl.ioctl(fd, RELEASE, struct.pack("I", AC_IF))
os.close(fd)
