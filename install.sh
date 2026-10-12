#!/bin/bash
# FLSUN_HelixScreen installer for the FLSun T1 Pro.
# Run as the pi user from the cloned repo: ~/FLSUN_HelixScreen/install.sh
# Options:
#   --local FILE   install this helixscreen-flsun-t1-*.tar.gz package instead
#                  of downloading the pinned release
# Safe to re-run, e.g. after a FLSun firmware update.

set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="${HOME}/printer_data/config"
MOONRAKER_CONF="${CONFIG_DIR}/moonraker.conf"
ASVC="${HOME}/printer_data/moonraker.asvc"
SERVICE="flsun_helixscreen"

msg() { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

LOCAL=""
while [ $# -gt 0 ]; do
    case "$1" in
        --local) [ -n "${2:-}" ] || die "--local needs a file"; LOCAL="$(readlink -f "$2")"; shift 2 ;;
        *) die "unknown option: $1" ;;
    esac
done

[ "$(id -u)" -ne 0 ] || die "run as the pi user, not root (sudo is used where needed)"
# The services and boot script point at this path.
[ "$REPO_DIR" = "${HOME}/FLSUN_HelixScreen" ] \
    || die "clone the repo to ${HOME}/FLSUN_HelixScreen (it is at $REPO_DIR)"
[ "$HOME" = /home/pi ] || die "this installer expects the pi user's home, /home/pi"
[ -x /usr/bin/python3 ] || die "/usr/bin/python3 not found"
[ -f "$MOONRAKER_CONF" ] || die "$MOONRAKER_CONF not found"
[ -d /home/pi/qt/out_linux ] || die "FLSun's screen files (/home/pi/qt/out_linux) not found; is this a T1 Pro?"
[ -z "$LOCAL" ] || [ -f "$LOCAL" ] || die "$LOCAL not found"

# Clock, certificates and git https support, shared with the other FLSun
# plugins; see prepare.sh.
"${REPO_DIR}/prepare.sh"

msg "Installing the boot service that sets the clock"
sudo install -m 755 "${REPO_DIR}/system/flsun-timesync" /usr/local/bin/flsun-timesync
sudo install -m 644 "${REPO_DIR}/system/flsun-timesync.service" /etc/systemd/system/flsun-timesync.service

msg "Installing the HelixScreen update service"
chmod 755 "${REPO_DIR}/flsun_helixscreen.py"
if [ ! -f "${CONFIG_DIR}/flsun_helixscreen.cfg" ]; then
    cp "${REPO_DIR}/config/flsun_helixscreen.cfg" "${CONFIG_DIR}/flsun_helixscreen.cfg"
fi
sudo install -m 644 "${REPO_DIR}/system/${SERVICE}.service" "/etc/systemd/system/${SERVICE}.service"
sudo install -m 644 "${REPO_DIR}/system/${SERVICE}.path" "/etc/systemd/system/${SERVICE}.path"
sudo systemctl daemon-reload
sudo systemctl enable flsun-timesync.service "${SERVICE}.service" "${SERVICE}.path" > /dev/null 2>&1
sudo systemctl restart "${SERVICE}.path"

msg "Adding the Moonraker update manager entry"
if [ ! -f "${CONFIG_DIR}/flsun_helixscreen.conf" ]; then
    cp "${REPO_DIR}/config/flsun_helixscreen.conf" "${CONFIG_DIR}/flsun_helixscreen.conf"
fi
if ! grep -q '^\[include flsun_helixscreen\.conf\]' "$MOONRAKER_CONF"; then
    cp "$MOONRAKER_CONF" "${MOONRAKER_CONF}.flsun_helixscreen.bak"
    printf '\n[include flsun_helixscreen.conf]\n' >> "$MOONRAKER_CONF"
fi
# Let Moonraker restart the service after an update.
if [ -f "$ASVC" ] && ! grep -qx "$SERVICE" "$ASVC"; then
    # FLSun's file has no final newline.
    [ -z "$(tail -c 1 "$ASVC")" ] || echo >> "$ASVC"
    echo "$SERVICE" >> "$ASVC"
fi

msg "Restarting Moonraker"
sudo systemctl restart moonraker

if [ -n "$LOCAL" ]; then
    msg "Installing HelixScreen from $LOCAL"
    sudo /usr/bin/python3 "${REPO_DIR}/flsun_helixscreen.py" install "$LOCAL"
else
    msg "Installing HelixScreen"
    sudo /usr/bin/python3 "${REPO_DIR}/flsun_helixscreen.py" apply
fi

msg "Done."
/usr/bin/python3 "${REPO_DIR}/flsun_helixscreen.py" status
