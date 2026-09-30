#!/usr/bin/env bash
set -euo pipefail
rm -f ~/.config/wireplumber/wireplumber.conf.d/51-c920-soft-mixer.conf
systemctl --user restart wireplumber
if [ -e /usr/local/bin/c920-mic-wake ] || [ -e /etc/udev/rules.d/51-c920-mic-wake.rules ]; then
  sudo rm -f /usr/local/bin/c920-mic-wake /etc/udev/rules.d/51-c920-mic-wake.rules
  sudo udevadm control --reload-rules
fi
echo "Removed. Replug the webcam to return to stock behaviour."
