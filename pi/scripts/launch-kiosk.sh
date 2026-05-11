#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${KAHRABAIQ_PI_ENV:-/etc/kahrabaiq/pi.env}"
if [ -f "$ENV_FILE" ]; then
  set -a
  . "$ENV_FILE"
  set +a
fi

KIOSK_DASHBOARD_URL="${KIOSK_DASHBOARD_URL:-${KAHRABAIQ_API_URL:-}/dashboard}"
if [ -z "$KIOSK_DASHBOARD_URL" ]; then
  printf 'KIOSK_DASHBOARD_URL or KAHRABAIQ_API_URL is required.\n' >&2
  exit 1
fi

FINAL_DASHBOARD_URL="$KIOSK_DASHBOARD_URL"
case "$KIOSK_DASHBOARD_URL" in
  http://127.0.0.1*|http://localhost*)
    ;;
  *)
    FINAL_DASHBOARD_URL="$(python3 - <<'PY'
import json
import os
import sys
import urllib.parse
import urllib.request

api_url = os.environ.get("KAHRABAIQ_API_URL", "").rstrip("/")
dashboard_url = os.environ.get("KIOSK_DASHBOARD_URL", "")
pi_id = os.environ.get("PI_ID", "")
device_token = os.environ.get("PI_DEVICE_TOKEN", "")

if not api_url or not dashboard_url or not pi_id or not device_token:
    sys.exit("KAHRABAIQ_API_URL, KIOSK_DASHBOARD_URL, PI_ID, and PI_DEVICE_TOKEN are required.")

request = urllib.request.Request(
    f"{api_url}/api/pi/kiosk-session",
    method="POST",
    headers={"X-Pi-Id": pi_id, "X-Device-Token": device_token},
)
with urllib.request.urlopen(request, timeout=12) as response:
    data = json.load(response)

kiosk_token = data.get("kiosk_token")
if not data.get("success") or not kiosk_token:
    sys.exit(data.get("detail") or data.get("message") or "Failed to create kiosk session.")

parsed = urllib.parse.urlparse(dashboard_url)
if not parsed.scheme or not parsed.netloc:
    sys.exit("KIOSK_DASHBOARD_URL must be an absolute URL.")

origin = f"{parsed.scheme}://{parsed.netloc}"
print(f"{origin}/dashboard/session/start?token={urllib.parse.quote(kiosk_token, safe='')}")
PY
)"
    ;;
esac

export DISPLAY="${DISPLAY:-:0}"
xset s off || true
xset -dpms || true
xset s noblank || true

exec chromium-browser \
  --kiosk \
  --noerrdialogs \
  --disable-infobars \
  --check-for-update-interval=31536000 \
  --app="$FINAL_DASHBOARD_URL"
