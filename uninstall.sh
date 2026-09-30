#!/usr/bin/env bash
set -euo pipefail
sudo rm -f /usr/local/bin/c920-mic-wake /etc/udev/rules.d/51-c920-mic-wake.rules
sudo udevadm control --reload-rules
echo "Removed. Replug the webcam to return to stock behaviour."
