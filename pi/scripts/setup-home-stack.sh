#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${KAHRABAIQ_REPO_DIR:-/opt/kahrabaiq}"
STATE_DIR="/var/lib/kahrabaiq"

sudo install -d -m 0755 "$STATE_DIR/homeassistant" "$STATE_DIR/matter-server"

if ! command -v docker >/dev/null 2>&1; then
  printf 'Docker is required for the Home Assistant and Matter stack. Install Docker, then re-run this script.\n' >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  printf 'Docker Compose v2 is required. Install the docker compose plugin, then re-run this script.\n' >&2
  exit 1
fi

sudo systemctl enable --now docker
docker compose -f "$REPO_DIR/pi/home-assistant/docker-compose.yml" up -d
sudo systemctl enable kahrabaiq-home-stack.service >/dev/null 2>&1 || true

printf 'Home Assistant: http://<pi-ip>:8123\n'
printf 'After onboarding, create a long-lived access token and set HOME_ASSISTANT_TOKEN in /etc/kahrabaiq/pi.env.\n'
printf 'Then add the Matter integration in Home Assistant. The Matter server is already running on the Pi.\n'
