# KahrabaIQ Raspberry Pi Runtime

The Pi runs local hardware services only. The touchscreen opens the deployed AWS-hosted kiosk dashboard, while the Pi agent keeps the long-lived `PI_DEVICE_TOKEN` off the browser.

## Services

- `kahrabaiq-agent`: local token bridge, heartbeat, live-state sync, command polling, and ESP32 provisioning actions.
- `kahrabaiq-sensor-receiver`: receives ESP32 sensor posts on the local network and writes SQLite state.
- `kahrabaiq-summary-sync`: builds hourly/daily SQLite summaries and uploads them to DynamoDB.
- `kahrabaiq-kiosk-browser`: launches Chromium in kiosk mode against the deployed dashboard URL.

## Install

1. Copy the repo to `/opt/kahrabaiq` on the Pi.
2. Run `KAHRABAIQ_REPO_DIR=/opt/kahrabaiq /opt/kahrabaiq/pi/scripts/install-pi.sh`.
3. Edit `/etc/kahrabaiq/pi.env` with the real API URL, Pi identity, and ESP32 key.
4. Run `sudo systemctl enable --now kahrabaiq-agent kahrabaiq-sensor-receiver kahrabaiq-summary-sync kahrabaiq-kiosk-browser`.

## Security Model

- `PI_DEVICE_TOKEN` exists only in `/etc/kahrabaiq/pi.env` and Pi processes.
- The browser requests a short-lived kiosk token from `http://127.0.0.1:5010/api/kiosk/session`.
- The deployed dashboard uses that kiosk token for AWS kiosk APIs.
- A laptop or phone that opens the dashboard URL directly will not have the local token bridge.
