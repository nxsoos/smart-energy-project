#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${KAHRABAIQ_REPO_DIR:-/opt/kahrabaiq}"
SERVICE_USER="${KAHRABAIQ_SERVICE_USER:-$(id -un)}"
PI_ENV_DIR="/etc/kahrabaiq"
PI_CERT_DIR="/etc/kahrabaiq/certs"
STATE_DIR="/var/lib/kahrabaiq"
SERVICE_DIR="/etc/systemd/system"

sudo install -d -m 0755 "$PI_ENV_DIR" "$STATE_DIR"
sudo install -d -m 0700 "$PI_CERT_DIR"
chmod +x "$REPO_DIR/pi/scripts/force-pi-setup-hotspot.sh" "$REPO_DIR/pi/scripts/harden-kiosk-x11.sh" "$REPO_DIR/pi/scripts/launch-kiosk.sh" || true
if [ ! -f "$PI_ENV_DIR/pi.env" ]; then
  sudo install -m 0600 "$REPO_DIR/pi/.env.sample" "$PI_ENV_DIR/pi.env"
  printf 'Created %s. Edit it with real HOME_ID, PI_ID, PI_DEVICE_TOKEN, API URL, and ESP32 key.\n' "$PI_ENV_DIR/pi.env"
fi

python3 -m venv "$REPO_DIR/.venv"
"$REPO_DIR/.venv/bin/pip" install --upgrade pip
"$REPO_DIR/.venv/bin/pip" install flask python-dotenv requests qrcode boto3 tuya-connector-python awsiotsdk

sudo install -m 0644 "$REPO_DIR/pi/systemd/"*.service "$SERVICE_DIR/"
sudo sed -i "s/^User=pi$/User=$SERVICE_USER/" "$SERVICE_DIR"/kahrabaiq-*.service
if [ -f "$REPO_DIR/pi/sudoers/kahrabaiq-admin" ]; then
  sudo install -m 0440 "$REPO_DIR/pi/sudoers/kahrabaiq-admin" /etc/sudoers.d/kahrabaiq-admin
  sudo sed -i "s/__KAHRABAIQ_SERVICE_USER__/$SERVICE_USER/g" /etc/sudoers.d/kahrabaiq-admin
  sudo visudo -cf /etc/sudoers.d/kahrabaiq-admin
fi
sudo systemctl daemon-reload
if [ -x "$REPO_DIR/pi/scripts/harden-kiosk-x11.sh" ]; then
  "$REPO_DIR/pi/scripts/harden-kiosk-x11.sh" || true
fi

printf 'Installed KahrabaIQ Pi services. Enable after configuring /etc/kahrabaiq/pi.env:\n'
printf '  sudo systemctl enable --now kahrabaiq-provisioning kahrabaiq-setup-screen kahrabaiq-agent kahrabaiq-sensor-receiver kahrabaiq-summary-sync kahrabaiq-command-runner kahrabaiq-iot-live-publisher kahrabaiq-kiosk-browser\n'
printf 'Provisioning uses NetworkManager/nmcli. Install network-manager first if nmcli is unavailable.\n'
printf 'For Home Assistant and Matter containers, install Docker and run:\n'
printf '  KAHRABAIQ_REPO_DIR=%s %s/pi/scripts/setup-home-stack.sh\n' "$REPO_DIR" "$REPO_DIR"
