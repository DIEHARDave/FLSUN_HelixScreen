#!/bin/bash
# Removes FLSUN_HelixScreen and HelixScreen, and puts FLSun's stock screen
# back. HelixScreen's settings are kept in ~/helixscreen-config.bak.

set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="${HOME}/printer_data/config"
MOONRAKER_CONF="${CONFIG_DIR}/moonraker.conf"
ASVC="${HOME}/printer_data/moonraker.asvc"
SERVICE="flsun_helixscreen"

msg() { printf '\033[1;32m==>\033[0m %s\n' "$*"; }

[ "$(id -u)" -ne 0 ] || { echo "run as the pi user, not root" >&2; exit 1; }

msg "Removing the HelixScreen update service"
sudo systemctl disable --now "${SERVICE}.path" "${SERVICE}.service" > /dev/null 2>&1 || true
sudo rm -f "/etc/systemd/system/${SERVICE}.path" "/etc/systemd/system/${SERVICE}.service"
sudo systemctl daemon-reload

msg "Removing HelixScreen and starting the stock screen"
sudo /usr/bin/python3 "${REPO_DIR}/flsun_helixscreen.py" remove

msg "Removing the Moonraker settings"
sed -i '/^\[include flsun_helixscreen\.conf\]/d' "$MOONRAKER_CONF"
rm -f "${CONFIG_DIR}/flsun_helixscreen.conf" "${CONFIG_DIR}/flsun_helixscreen.cfg"
if [ -f "$ASVC" ]; then
    sed -i "/^${SERVICE}\$/d" "$ASVC"
fi

# The flsun-timesync boot service is left in place on purpose: a correct
# clock helps everything else on the printer too, and the other FLSun
# plugins use the same service.

msg "Restarting Moonraker"
sudo systemctl restart moonraker

msg "Done. Delete ~/FLSUN_HelixScreen to finish."
