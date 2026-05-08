#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${KAHRABAIQ_REPO_DIR:-/opt/kahrabaiq}"
PI_ENV_DIR="/etc/kahrabaiq"
STATE_DIR="/var/lib/kahrabaiq"
SERVICE_DIR="/etc/systemd/system"

sudo install -d -m 0755 "$PI_ENV_DIR" "$STATE_DIR"
if [ ! -f "$PI_ENV_DIR/pi.env" ]; then
  sudo install -m 0600 "$REPO_DIR/pi/.env.sample" "$PI_ENV_DIR/pi.env"
  printf 'Created %s. Edit it with real HOME_ID, PI_ID, PI_DEVICE_TOKEN, API URL, and ESP32 key.\n' "$PI_ENV_DIR/pi.env"
fi

python3 -m venv "$REPO_DIR/.venv"
"$REPO_DIR/.venv/bin/pip" install --upgrade pip
"$REPO_DIR/.venv/bin/pip" install flask python-dotenv requests boto3 tuya-connector-python

sudo install -m 0644 "$REPO_DIR/pi/systemd/"*.service "$SERVICE_DIR/"
sudo systemctl daemon-reload

printf 'Installed KahrabaIQ Pi services. Enable after configuring /etc/kahrabaiq/pi.env:\n'
printf '  sudo systemctl enable --now kahrabaiq-agent kahrabaiq-sensor-receiver kahrabaiq-summary-sync kahrabaiq-command-runner kahrabaiq-kiosk-browser\n'
printf 'For Home Assistant and Matter containers, install Docker and run:\n'
printf '  KAHRABAIQ_REPO_DIR=%s %s/pi/scripts/setup-home-stack.sh\n' "$REPO_DIR" "$REPO_DIR"
