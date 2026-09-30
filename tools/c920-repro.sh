#!/usr/bin/env bash
# Reproduce the C920 stuck-silent mic in ~10 seconds, through the normal ALSA/PipeWire stack.
# Trigger: the mic stream starts while the webcam's hardware mute is on; after unmuting it keeps
# sending all-zero audio (and reports itself unmuted) until it is replugged.
# Run WITHOUT 51-c920-soft-mixer.conf active (otherwise PipeWire never uses the hardware mute).
# No root needed. Replug the webcam afterwards to recover.
set -euo pipefail
SRC=$(pactl list sources short | awk '/C920/{print $2; exit}')
CARD=$(awk '/C920/{print $1; exit}' /proc/asound/cards)
count() { python3 -c "import wave,array,sys; w=wave.open(sys.argv[1]); a=array.array('h', w.readframes(w.getnframes())); print(sum(1 for x in a if x), 'non-zero samples of', len(a))" "$1"; }
rec() { timeout "$1" pw-record --target "$SRC" "$2" >/dev/null 2>&1 || true; }

rec 3 /tmp/c920-before.wav;  echo "1. healthy:                       $(count /tmp/c920-before.wav)"
amixer -q -c "$CARD" sset Mic nocap                     # hardware mute ON
rec 2 /tmp/c920-muted.wav                              # an app starts the mic while muted
amixer -q -c "$CARD" sset Mic cap                       # hardware mute OFF
echo "   switch now reports: $(amixer -c "$CARD" sget Mic | grep -o '\[o[nf]*\]' | tail -1)"
rec 3 /tmp/c920-after.wav;   echo "2. after start-while-muted+unmute: $(count /tmp/c920-after.wav)"
echo "(Muting and unmuting while the mic is idle, or mid-stream, does NOT trigger it.)"
