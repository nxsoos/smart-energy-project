# KahrabaIQ Raspberry Pi Runtime

The Pi runs local hardware services and reports compact state to the deployed API. During the transition, AWS IoT Core remains the live data pipe for the Flutter app; the Pi also syncs the same compact state to the EC2/API backend so the final EC2 dashboard path is ready.

## Services

- `kahrabaiq-agent`: local token bridge, heartbeat, compact live-state sync to EC2/API, kiosk command polling, and ESP32 provisioning actions.
- `kahrabaiq-sensor-receiver`: receives ESP32 sensor posts on the local network and writes SQLite state.
- `kahrabaiq-tuya-breaker-poller`: legacy Tuya Cloud breaker polling. Keep disabled for the normal Home Assistant breaker path.
- `kahrabaiq-summary-sync`: builds hourly/daily SQLite summaries and uploads them to DynamoDB.
- `kahrabaiq-iot-live-publisher`: publishes compact live state from local SQLite to AWS IoT Core for remote phone dashboards.
- `kahrabaiq-home-stack`: runs local Home Assistant and Matter server containers.
- `kahrabaiq-command-runner`: polls remote device commands through EC2/API when `REMOTE_COMMAND_SOURCE=ec2`, or directly from DynamoDB when `REMOTE_COMMAND_SOURCE=dynamodb`, then executes them locally through Home Assistant. Tuya Cloud is backup only when explicitly enabled.
- `kahrabaiq-kiosk-browser`: launches Chromium in kiosk mode against the deployed dashboard URL.

## Install

1. Copy the repo to `/opt/kahrabaiq` on the Pi.
2. Run `KAHRABAIQ_REPO_DIR=/opt/kahrabaiq /opt/kahrabaiq/pi/scripts/install-pi.sh`.
3. Edit `/etc/kahrabaiq/pi.env` with the real API URL, Pi identity, and ESP32 key.
4. Run `sudo systemctl enable --now kahrabaiq-agent kahrabaiq-sensor-receiver kahrabaiq-summary-sync kahrabaiq-command-runner kahrabaiq-iot-live-publisher kahrabaiq-kiosk-browser`.
5. For Matter devices, install Docker and run `KAHRABAIQ_REPO_DIR=/opt/kahrabaiq /opt/kahrabaiq/pi/scripts/setup-home-stack.sh`.
6. Finish Home Assistant onboarding, create a long-lived access token, set `HOME_ASSISTANT_TOKEN`, and configure the breaker/Matter entity IDs in `/etc/kahrabaiq/pi.env`.

## Transitional Cloud Flow

- ESP32 posts live sensor readings to `kahrabaiq-sensor-receiver`.
- The Pi saves sensors, breaker readings, device state, commands, and alerts in local SQLite.
- `kahrabaiq-iot-live-publisher` publishes compact live state to `homes/home_001/live/state` every `AWS_IOT_LIVE_INTERVAL_SECONDS` seconds for the current app.
- `kahrabaiq-agent` posts the same compact live state to `POST /api/pi/{pi_id}/sensor-state` every `PI_LIVE_SYNC_INTERVAL_SECONDS` seconds so EC2/API can serve current state later.
- The app sends remote commands to EC2/API; the backend queues them in DynamoDB.
- `kahrabaiq-command-runner` polls EC2/API with the Pi token, executes breaker and switch commands through Home Assistant, and reports the result back to EC2/API.
- `kahrabaiq-summary-sync` keeps low-frequency hourly/daily summaries in DynamoDB.

## Security Model

- `PI_DEVICE_TOKEN` exists only in `/etc/kahrabaiq/pi.env` and Pi processes.
- The browser requests a short-lived kiosk token from `http://127.0.0.1:5010/api/kiosk/session`.
- The deployed dashboard uses that kiosk token for AWS kiosk APIs.
- A laptop or phone that opens the dashboard URL directly will not have the local token bridge.

## Home Assistant Breakers, Matter

The Pi hosts Home Assistant and the Matter server locally. KahrabaIQ breaker and Matter switch commands are queued by AWS and executed by `kahrabaiq-command-runner` on the Pi through the Home Assistant REST API.

Required breaker values:

```env
USE_HOME_ASSISTANT_FOR_BREAKERS=true
USE_TUYA_CLOUD_FOR_BREAKERS=false
AC_BREAKER_ENTITY_ID=switch.ac_breaker_switch
SOCKET_BREAKER_ENTITY_ID=switch.socket_breaker_switch
MATTER_AC_SWITCH_ENTITY_ID=switch.ac_breaker_switch
MATTER_SOCKET_SWITCH_ENTITY_ID=switch.socket_breaker_switch
```

See `pi/docs/home-assistant-matter.md`.

## Tuya Breakers

Tuya Cloud is backup only. Keep `kahrabaiq-tuya-breaker-poller` disabled for the final Home Assistant breaker flow:

```bash
sudo systemctl stop kahrabaiq-tuya-breaker-poller
sudo systemctl disable kahrabaiq-tuya-breaker-poller
```

Tuya breaker credentials, if retained, belong in `/etc/kahrabaiq/pi.env`, not in committed files. See `pi/docs/tuya-setup.md`.
