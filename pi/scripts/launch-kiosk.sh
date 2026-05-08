#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${KAHRABAIQ_PI_ENV:-/etc/kahrabaiq/pi.env}"
if [ -f "$ENV_FILE" ]; then
  set -a
  . "$ENV_FILE"
  set +a
fi

KIOSK_DASHBOARD_URL="${KIOSK_DASHBOARD_URL:-${KAHRABAIQ_API_URL:-}/api/kiosk/dashboard}"
if [ -z "$KIOSK_DASHBOARD_URL" ]; then
  printf 'KIOSK_DASHBOARD_URL or KAHRABAIQ_API_URL is required.\n' >&2
  exit 1
fi

export DISPLAY="${DISPLAY:-:0}"
xset s off || true
xset -dpms || true
xset s noblank || true

exec chromium-browser \
  --kiosk \
  --noerrdialogs \
  --disable-infobars \
  --check-for-update-interval=31536000 \
  --app="$KIOSK_DASHBOARD_URL"
