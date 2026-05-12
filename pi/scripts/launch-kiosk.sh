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

export DISPLAY="${DISPLAY:-:0}"
export XAUTHORITY="${XAUTHORITY:-$HOME/.Xauthority}"
if [ -z "${DBUS_SESSION_BUS_ADDRESS:-}" ] && [ -S "/run/user/$(id -u)/bus" ]; then
  export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$(id -u)/bus"
fi
KIOSK_USER_DATA_DIR="${KIOSK_USER_DATA_DIR:-${XDG_CACHE_HOME:-$HOME/.cache}/kahrabaiq-kiosk-chromium}"
mkdir -p "$KIOSK_USER_DATA_DIR"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"$SCRIPT_DIR/harden-kiosk-x11.sh" || true
timeout 3s xset s off || true
timeout 3s xset -dpms || true
timeout 3s xset s noblank || true

CHROMIUM_CMD=(chromium
  --kiosk \
  --noerrdialogs \
  --disable-infobars \
  --disable-gpu \
  --disable-gpu-compositing \
  --disable-accelerated-2d-canvas \
  --disable-background-networking \
  --disable-sync \
  --disable-extensions \
  --disable-features=MediaRouter,OptimizationHints,Translate,BackForwardCache \
  --ozone-platform=x11 \
  --no-first-run \
  --disable-session-crashed-bubble \
  --disable-restore-session-state \
  --disable-pinch \
  --user-data-dir="$KIOSK_USER_DATA_DIR" \
  --remote-debugging-address=127.0.0.1 \
  --remote-debugging-port=9222 \
  --overscroll-history-navigation=0 \
  --check-for-update-interval=31536000 \
  --app="$FINAL_DASHBOARD_URL")

if command -v dbus-run-session >/dev/null 2>&1 && [ -z "${DBUS_SESSION_BUS_ADDRESS:-}" ]; then
  exec dbus-run-session -- "${CHROMIUM_CMD[@]}"
fi

exec "${CHROMIUM_CMD[@]}"
