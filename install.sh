#!/usr/bin/env bash
# Install the fix: a WirePlumber rule so PipeWire never uses the C920's buggy hardware mute.
# No root needed. Add --with-wake to also install the optional plug-in wake-up script (needs sudo).
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p ~/.config/wireplumber/wireplumber.conf.d
install -m 644 51-c920-soft-mixer.conf ~/.config/wireplumber/wireplumber.conf.d/51-c920-soft-mixer.conf
CARD=$(awk '/C920/{print $1; exit}' /proc/asound/cards 2>/dev/null || true)
[ -n "$CARD" ] && amixer -q -c "$CARD" sset Mic cap 8 || true      # hardware: unmuted, 36 dB
systemctl --user restart wireplumber
echo "Installed the WirePlumber rule. If the mic is currently silent, replug the webcam once."
if [ "${1:-}" = "--with-wake" ]; then
  sudo install -m 755 c920-mic-wake /usr/local/bin/c920-mic-wake
  sudo install -m 644 51-c920-mic-wake.rules /etc/udev/rules.d/51-c920-mic-wake.rules
  sudo udevadm control --reload-rules
  sudo udevadm trigger --action=add --attr-match=idVendor=046d --attr-match=idProduct=082d
  echo "Installed the wake-up script. Check: journalctl -o cat | grep c920-mic-wake | tail -1"
fi
