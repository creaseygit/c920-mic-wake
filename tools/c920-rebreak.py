#!/usr/bin/env python3
# Try to put a healthy C920 mic back into the stuck all-zero state, one suspect request at a time.
# After each step the mic is streamed at alt 1 (16 kHz) and alt 3 (32 kHz); a step that turns it
# silent is reported, then the known clearing sequence is run so the remaining steps start clean.
# Usage (root, snd-usb-audio unloaded and blocked from auto-loading, webcam freshly re-plugged):
#   sudo python3 c920-rebreak.py /dev/bus/usb/BBB/DDD
import ctypes, fcntl, os, struct, sys, time

DEV = sys.argv[1]
AS_IF, AC_IF, FU, EP = 3, 2, 5, 0x82
PKT = {1: 68, 2: 100, 3: 132}         # wMaxPacketSize per alt setting (16 / 24 / 32 kHz)
RATE = {1: 16000, 2: 24000, 3: 32000}
NPK = 8
FU_IDX = (FU << 8) | AC_IF

SETINTERFACE, CLAIM, RELEASE = 0x80085504, 0x8004550F, 0x80045510
SUBMITURB, REAPURB, REAPURBNDELAY, DISCARD, CONTROL = 0x8038550A, 0x4008550C, 0x4008550D, 0x0000550B, 0xC0185500

class IsoDesc(ctypes.Structure):
    _fields_ = [("length", ctypes.c_uint), ("actual_length", ctypes.c_uint), ("status", ctypes.c_uint)]
class Urb(ctypes.Structure):
    _fields_ = [("type", ctypes.c_uint8), ("endpoint", ctypes.c_uint8), ("status", ctypes.c_int),
                ("flags", ctypes.c_uint), ("buffer", ctypes.c_void_p), ("buffer_length", ctypes.c_int),
                ("actual_length", ctypes.c_int), ("start_frame", ctypes.c_int),
                ("number_of_packets", ctypes.c_int), ("error_count", ctypes.c_int),
                ("signr", ctypes.c_uint), ("usercontext", ctypes.c_void_p), ("iso", IsoDesc * NPK)]
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

def stream(alt, seconds=0.4):
    """Stream `alt` for `seconds`; return (packets, non-zero packets)."""
    pkt = PKT[alt]
    setalt(alt)
    by_addr, ptr, n, nz = {}, ctypes.c_void_p(), 0, 0
    for _ in range(4):
        b = ctypes.create_string_buffer(NPK * pkt)
        u = Urb(type=0, endpoint=EP, flags=2, buffer=ctypes.addressof(b), buffer_length=NPK * pkt,
                number_of_packets=NPK)
        for i in range(NPK):
            u.iso[i].length = pkt
        by_addr[ctypes.addressof(u)] = (u, b)
        pioctl(SUBMITURB, ctypes.addressof(u))
    end = time.time() + seconds
    while True:
        pioctl(REAPURB, ctypes.addressof(ptr))
        u, b = by_addr[ptr.value]
        for i in range(NPK):
            al = u.iso[i].actual_length
            n += 1
            nz += any(b.raw[i * pkt:i * pkt + al])
            u.iso[i].actual_length = u.iso[i].status = 0
        if time.time() > end:
            break
        pioctl(SUBMITURB, ctypes.addressof(u))
    for addr in by_addr:
        try: pioctl(DISCARD, addr)
        except OSError: pass
    deadline = time.time() + 1
    while time.time() < deadline:
        try: pioctl(REAPURBNDELAY, ctypes.addressof(ptr))
        except OSError: time.sleep(0.02)
    setalt(0)
    return n, nz

def hx(r):
    return r.hex() if isinstance(r, bytes) else r

def state():
    m = ctl(0xA1, 0x81, 0x0100, FU_IDX, length=1)
    v = ctl(0xA1, 0x81, 0x0200, FU_IDX, length=2)
    r = ctl(0xA1, 0x84, 0x0200, FU_IDX, length=2)
    rate = ctl(0xA2, 0x81, 0x0100, EP, length=3)
    return f"mute={hx(m)} vol={hx(v)} res={hx(r)} rate={int.from_bytes(rate, 'little') if isinstance(rate, bytes) else rate}"

def check():
    a1, a3 = stream(1), stream(3)
    ok = a1[1] > 0 and a3[1] > 0
    return ok, f"alt1 {a1[1]}/{a1[0]}  alt3 {a3[1]}/{a3[0]}"

def clear():
    stream(1, 0.5)
    ctl(0xA2, 0x81, 0x0100, EP, length=3)
    ctl(0x22, 0x01, 0x0100, EP, (16000).to_bytes(3, "little"))
    ctl(0x21, 0x01, 0x0100, FU_IDX, b"\x00")
    ctl(0xA1, 0x81, 0x0200, FU_IDX, length=2)
    for v in (12800, 5120, 9216):
        ctl(0x21, 0x01, 0x0200, FU_IDX, struct.pack("<h", v))
    stream(1, 0.3)

broke = []
def step(label, action):
    action()
    ok, detail = check()
    print(f"{'  ok  ' if ok else 'BROKE!'} {label:<52} {detail:<32} {state()}", flush=True)
    if not ok:
        broke.append(label)
        clear()
        ok2, d2 = check()
        print(f"        -> clearing sequence: {'recovered' if ok2 else 'STILL SILENT'} ({d2})", flush=True)

def set_vol(raw_bytes):
    return lambda: ctl(0x21, 0x01, 0x0200, FU_IDX, raw_bytes)
def set_res(raw_bytes, times=1):
    return lambda: [ctl(0x21, 0x04, 0x0200, FU_IDX, raw_bytes) for _ in range(times)]
def rate_cycle():
    for alt in (1, 2, 3):
        setalt(0); setalt(alt)
        ctl(0x22, 0x01, 0x0100, EP, RATE[alt].to_bytes(3, "little"))
        ctl(0xA2, 0x81, 0x0100, EP, length=3)
    setalt(0)
def reads():
    ctl(0xA1, 0x81, 0x0100, FU_IDX, length=1)
    for r in (0x83, 0x82, 0x84):
        ctl(0xA1, r, 0x0200, FU_IDX, length=2)

fcntl.ioctl(fd, CLAIM, struct.pack("I", AS_IF))
fcntl.ioctl(fd, CLAIM, struct.pack("I", AC_IF))
setalt(0)

print("Fresh device state:", state(), flush=True)
# Driver's first stream is alt 3; check that before anything else touches the device.
n3 = stream(3)
print(f"{'  ok  ' if n3[1] else 'BROKE!'} {'0. very first stream at alt 3 (driver default)':<52} alt3 {n3[1]}/{n3[0]}", flush=True)
if not n3[1]:
    broke.append("first stream alt 3")
step("1. baseline (alt 1 + alt 3)", lambda: None)
step("2. driver rate cycling alt 1/2/3 with SET_CUR", rate_cycle)
step("3. driver mixer reads (mute, vol max/min/res)", reads)
step("4. SET_RES volume = driver bytes 00 01, x10", set_res(b"\x00\x01", 10))
step("5. driver sticky sweep 0x1400/0x2c00/0x2a00/0x2400",
     lambda: [ctl(0x21, 0x01, 0x0200, FU_IDX, bytes.fromhex(h)) for h in ("0014", "002c", "002a", "0024")])
step("6. volume = 0x8000 (UAC 'silence')", set_vol(struct.pack("<H", 0x8000)))
step("7. volume back to 36 dB", set_vol(struct.pack("<h", 9216)))
step("8. mute = 1", lambda: ctl(0x21, 0x01, 0x0100, FU_IDX, b"\x01"))
step("9. mute = 0", lambda: ctl(0x21, 0x01, 0x0100, FU_IDX, b"\x00"))
step("10. SET_RES volume = 0x0000", set_res(b"\x00\x00"))
step("11. SET_RES volume = 0x0001 (bytes 01 00)", set_res(b"\x01\x00"))
step("12. SET_RES volume = 0xffff", set_res(b"\xff\xff"))
step("13. SET_RES volume = 0x0200 (device default)", set_res(b"\x00\x02"))
step("14. volume below min (0x0000)", set_vol(b"\x00\x00"))
step("15. volume above max (0x7fff)", set_vol(b"\xff\x7f"))
step("16. volume back to 36 dB", set_vol(struct.pack("<h", 9216)))

print("\nSteps that silenced the mic immediately:", broke or "none", flush=True)
print("Final state:", state(), flush=True)
fcntl.ioctl(fd, RELEASE, struct.pack("I", AS_IF))
fcntl.ioctl(fd, RELEASE, struct.pack("I", AC_IF))
os.close(fd)
