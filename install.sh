#!/usr/bin/env bash
# Install the C920 mic wake-up script and its udev rule, then apply it to a webcam that is already plugged in.
set -euo pipefail
cd "$(dirname "$0")"
sudo install -m 755 c920-mic-wake /usr/local/bin/c920-mic-wake
sudo install -m 644 51-c920-mic-wake.rules /etc/udev/rules.d/51-c920-mic-wake.rules
sudo udevadm control --reload-rules
sudo udevadm trigger --action=add --attr-match=idVendor=046d --attr-match=idProduct=082d
echo "Installed. Check it ran: journalctl -o cat | grep c920-mic-wake | tail -1"
