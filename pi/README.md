# KahrabaIQ Raspberry Pi Runtime

The Pi runs local hardware services only. The touchscreen opens the deployed AWS-hosted kiosk dashboard, while the Pi agent keeps the long-lived `PI_DEVICE_TOKEN` off the browser.

## Services

- `kahrabaiq-agent`: local token bridge, heartbeat, live-state sync, command polling, and ESP32 provisioning actions.
- `kahrabaiq-sensor-receiver`: receives ESP32 sensor posts on the local network and writes SQLite state.
- `kahrabaiq-summary-sync`: builds hourly/daily SQLite summaries and uploads them to DynamoDB.
- `kahrabaiq-home-stack`: runs local Home Assistant and Matter server containers.
- `kahrabaiq-command-runner`: polls AWS-queued device commands and executes them locally through Tuya or Home Assistant/Matter.
- `kahrabaiq-kiosk-browser`: launches Chromium in kiosk mode against the deployed dashboard URL.

## Install

1. Copy the repo to `/opt/kahrabaiq` on the Pi.
2. Run `KAHRABAIQ_REPO_DIR=/opt/kahrabaiq /opt/kahrabaiq/pi/scripts/install-pi.sh`.
3. Edit `/etc/kahrabaiq/pi.env` with the real API URL, Pi identity, and ESP32 key.
4. Run `sudo systemctl enable --now kahrabaiq-agent kahrabaiq-sensor-receiver kahrabaiq-summary-sync kahrabaiq-command-runner kahrabaiq-kiosk-browser`.
5. For Matter devices, install Docker and run `KAHRABAIQ_REPO_DIR=/opt/kahrabaiq /opt/kahrabaiq/pi/scripts/setup-home-stack.sh`.
6. Finish Home Assistant onboarding, create a long-lived access token, set `HOME_ASSISTANT_TOKEN`, and configure the Matter entity IDs in `/etc/kahrabaiq/pi.env`.

## Security Model

- `PI_DEVICE_TOKEN` exists only in `/etc/kahrabaiq/pi.env` and Pi processes.
- The browser requests a short-lived kiosk token from `http://127.0.0.1:5010/api/kiosk/session`.
- The deployed dashboard uses that kiosk token for AWS kiosk APIs.
- A laptop or phone that opens the dashboard URL directly will not have the local token bridge.

## Home Assistant And Matter

The Pi hosts Home Assistant and the Matter server locally. KahrabaIQ device commands that require local control are queued by AWS and executed by `kahrabaiq-command-runner` on the Pi.

See `pi/docs/home-assistant-matter.md`.

## Tuya Breakers

Tuya breaker credentials belong in `/etc/kahrabaiq/pi.env`, not in committed files. See `pi/docs/tuya-setup.md`.
