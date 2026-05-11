#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${KAHRABAIQ_PI_ENV:-/etc/kahrabaiq/pi.env}"
MARKER_PATH="/var/lib/kahrabaiq/provisioned.json"
SETUP_INTERFACE="wlan1"

if [ -f "$ENV_FILE" ]; then
  set -a
  . "$ENV_FILE"
  set +a
fi

MARKER_PATH="${PROVISIONING_MARKER_PATH:-$MARKER_PATH}"
SETUP_INTERFACE="${PI_SETUP_WIFI_INTERFACE:-$SETUP_INTERFACE}"

if [ "$(id -u)" -ne 0 ]; then
  printf 'Run with sudo:\n  sudo %s\n' "$0" >&2
  exit 1
fi

printf '\n== KahrabaIQ Pi setup hotspot reset ==\n'
printf 'Env file: %s\n' "$ENV_FILE"
printf 'Provisioning marker: %s\n' "$MARKER_PATH"
printf 'Setup Wi-Fi interface: %s\n\n' "$SETUP_INTERFACE"

printf '1. Removing provisioning marker so setup can start...\n'
rm -f "$MARKER_PATH"

printf '2. Unblocking Wi-Fi radios...\n'
rfkill unblock wifi || true
rfkill unblock all || true

printf '3. Restarting NetworkManager...\n'
systemctl enable --now NetworkManager.service || true
systemctl restart NetworkManager.service || true
sleep 3

printf '4. Bringing setup interface up...\n'
ip link set "$SETUP_INTERFACE" up || true
nmcli device set "$SETUP_INTERFACE" managed yes || true

printf '5. Clearing old KahrabaIQ setup AP connection...\n'
nmcli connection down "${PI_SETUP_AP_CONNECTION:-kahrabaiq-setup-ap}" || true
nmcli connection delete "${PI_SETUP_AP_CONNECTION:-kahrabaiq-setup-ap}" || true

printf '6. Reloading and restarting KahrabaIQ setup services...\n'
systemctl daemon-reload
systemctl stop kahrabaiq-kiosk-browser.service || true
systemctl restart kahrabaiq-provisioning.service
systemctl restart kahrabaiq-setup-screen.service || true

printf '7. Current Wi-Fi devices:\n'
nmcli device status || true

printf '\n8. Provisioning service status:\n'
systemctl --no-pager status kahrabaiq-provisioning.service || true

printf '\n9. Recent provisioning logs:\n'
journalctl -u kahrabaiq-provisioning.service -n 80 --no-pager || true

printf '\nDone. Look for Wi-Fi SSID: %s\n' "${PI_SETUP_AP_SSID:-KahrabaIQ-Pi-Setup}"
printf 'Default setup page after connecting: http://10.42.0.1:%s/setup\n' "${PI_PROVISIONING_PORT:-8080}"
