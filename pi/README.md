# KahrabaIQ Raspberry Pi Runtime

The Pi runs local hardware services and reports compact state to the deployed API. During the transition, AWS IoT Core remains the live data pipe for the Flutter app; the Pi also syncs the same compact state to the EC2/API backend so the final EC2 dashboard path is ready.

## Services

- `kahrabaiq-agent`: local token bridge, heartbeat, compact live-state sync to EC2/API, kiosk command polling, and ESP32 provisioning actions.
- `kahrabaiq-provisioning`: first-boot setup portal. It uses `wlan1` for temporary setup, connects `wlan0` to home Wi-Fi, provisions the ESP32, turns `wlan1` off, then allows the dashboard to start.
- `kahrabaiq-setup-screen`: locked first-boot Chromium screen shown on the Pi display while setup is incomplete. It shows hotspot instructions, QR pairing, and sensor setup progress.
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
4. Run `sudo systemctl enable --now kahrabaiq-provisioning kahrabaiq-setup-screen kahrabaiq-agent kahrabaiq-sensor-receiver kahrabaiq-summary-sync kahrabaiq-command-runner kahrabaiq-iot-live-publisher kahrabaiq-kiosk-browser`.
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
- The dashboard starts only after `/var/lib/kahrabaiq/provisioned.json` exists.
- The local kiosk dashboard can be unlocked by admin credentials, then locked again without rebooting.

## First-Boot Provisioning

Use the built-in Pi Wi-Fi as `wlan0` and the TL-WN725N USB adapter as `wlan1`.

```text
wlan0 -> home Wi-Fi
wlan1 -> temporary KahrabaIQ-Pi-Setup hotspot and ESP32 setup connection
```

After provisioning succeeds, `wlan1` is disconnected and turned off. See `pi/docs/first-boot-provisioning.md`.

Detailed first-boot sequence:

1. The Pi boots and starts `kahrabaiq-provisioning.service` before the dashboard.
2. The service checks `/var/lib/kahrabaiq/provisioned.json`.
3. If the marker exists, setup is skipped, `wlan1` stays off, and normal services start.
4. If the marker does not exist, the Pi starts `KahrabaIQ-Pi-Setup` on `wlan1`.
5. Connect a phone/laptop to `KahrabaIQ-Pi-Setup` and open the setup page on port `8080`.
6. Enter the home Wi-Fi SSID/password and optional ESP32 device values. Do not enter `home_id`; QR pairing provides it.
7. The Pi connects `wlan0` to the home Wi-Fi and reaches the backend.
8. The Pi generates a backend QR pairing token and displays it on the locked setup screen.
9. The user scans the QR in the mobile app and becomes `home_admin` for the newly linked home.
10. The Pi polls pairing status until the backend returns `paired` and a real `home_id`.
11. The setup screen shows `Home paired successfully. Waiting for sensors to connect to the Pi...`.
12. The Pi stops the setup AP and connects `wlan1` to the ESP32 setup hotspot `KahrabaIQ-ESP32-Setup`.
13. The Pi detects the ESP32 setup gateway from `wlan1` and sends `POST http://<detected-gateway>/provision` with the same home Wi-Fi credentials, real `home_id`, `PI_SENSOR_BASE_URL`, `PI_ID`, device ID, and device key.
14. The ESP32 saves the config, reboots, and joins the home Wi-Fi.
15. The Pi disconnects and turns off `wlan1`.
16. The Pi writes `/var/lib/kahrabaiq/provisioned.json`.
17. `kahrabaiq-agent`, `kahrabaiq-sensor-receiver`, command/sync services, and `kahrabaiq-kiosk-browser` start.

Required provisioning environment values:

```env
PI_HOME_WIFI_INTERFACE=wlan0
PI_SETUP_WIFI_INTERFACE=wlan1
PI_SETUP_AP_SSID=KahrabaIQ-Pi-Setup
PI_SETUP_AP_PASSWORD=change_this_setup_password
PI_PROVISIONING_PORT=8080
PROVISIONING_MARKER_PATH=/var/lib/kahrabaiq/provisioned.json
ESP32_SETUP_SSID=KahrabaIQ-ESP32-Setup
ESP32_SETUP_PASSWORD=kahrabaiq123
ESP32_SETUP_URL=
ESP32_DISCOVERY_CANDIDATES=http://kahrabaiq-esp32.local
PI_PAIRING_POLL_SECONDS=2
PI_PAIRING_WAIT_TIMEOUT_SECONDS=900
PI_SENSOR_BASE_URL=http://kahrabaiq-pi.local:5000
PI_LOCAL_BASE_URL=http://kahrabaiq-pi.local:5001
```

Leave `ESP32_SETUP_URL` empty for normal installs. The Pi auto-detects the ESP32 setup server from the `wlan1` gateway after joining `ESP32_SETUP_SSID`. If gateway detection fails, provisioning fails with a clear error instead of falling back to a hardcoded IP.

The Wi-Fi password is kept in memory during the active setup session so it can be sent to the ESP32 only after QR pairing returns the real `home_id`. It is not written to `/var/lib/kahrabaiq/provisioned.json`. If the setup service restarts before ESP32 provisioning finishes, the user must re-enter Wi-Fi credentials.

The provisioning service uses NetworkManager/`nmcli`. Verify it exists on the Pi before deployment:

```bash
nmcli device status
```

## Dashboard Admin Unlock

The local kiosk dashboard is served from `http://127.0.0.1:5010/dashboard` and is locked by default after provisioning.

Admin unlock options:

```text
Long press the top-right corner for 5 seconds
Ctrl+Alt+A with a keyboard
```

Admin mode allows:

- Lock the dashboard again without rebooting.
- View Pi, Wi-Fi, provisioning, and ESP32 status.
- Restart the kiosk service.
- Exit the kiosk/setup browser to the Raspberry Pi OS desktop/session.
- Return to the dashboard kiosk or setup screen.
- Start maintenance provisioning mode.

Admin environment values:

```env
PI_CLOUD_ADMIN_UNLOCK_ENABLED=true
COGNITO_REGION=eu-west-1
COGNITO_APP_CLIENT_ID=your_cognito_app_client_id
KIOSK_ADMIN_USERNAME=admin
KIOSK_ADMIN_PASSWORD=
KIOSK_ADMIN_PASSWORD_HASH=
KIOSK_ADMIN_PIN=
KIOSK_ADMIN_PIN_HASH=change_this_to_a_sha256_pin_hash
KIOSK_ADMIN_SESSION_SECONDS=1800
```

Use platform admin credentials for normal unlock. Only backend `platform_admin` users pass cloud unlock; home admins, members, and viewers do not. Keep `KIOSK_ADMIN_PIN_HASH` as the offline recovery path and leave `KIOSK_ADMIN_PASSWORD` empty in production. The hash format is a SHA-256 hex digest.

`Exit Kiosk To Desktop` stops the browser services only. It does not unlock the Raspberry Pi OS password screen, SSH, root, or arbitrary sudo access. The installer also installs limited sudoers rules from `pi/sudoers/kahrabaiq-admin` so the Pi agent can run only allowlisted maintenance commands.

Maintenance flow:

1. Unlock admin mode.
2. Press `Enter Maintenance`.
3. The kiosk service stops.
4. `/var/lib/kahrabaiq/provisioned.json` is removed.
5. `kahrabaiq-provisioning.service` starts again.
6. `wlan1` becomes the temporary setup/provisioning adapter again.
7. After successful setup, `wlan1` turns off and the dashboard can be locked again.

## Home Assistant Breakers, Matter, Light

The Pi hosts Home Assistant and the Matter server locally. KahrabaIQ breaker, switch, and light commands are queued by AWS and executed by `kahrabaiq-command-runner` on the Pi through the Home Assistant REST API.

Required Home Assistant values:

```env
USE_HOME_ASSISTANT_FOR_BREAKERS=true
USE_TUYA_CLOUD_FOR_BREAKERS=false
AC_BREAKER_ENTITY_ID=switch.ac_breaker_switch
SOCKET_BREAKER_ENTITY_ID=switch.socket_breaker_switch
MATTER_AC_SWITCH_ENTITY_ID=switch.ac_breaker_switch
MATTER_SOCKET_SWITCH_ENTITY_ID=switch.socket_breaker_switch
LIGHT_SWITCH_ENTITY_ID=switch.light_switch_switch_1
REMOTE_COMMAND_POLL_SECONDS=2
LOCAL_COMMAND_VERIFY_DELAY_SECONDS=0.5
LOCAL_HA_STATE_SYNC_INTERVAL_SECONDS=2
PI_LIVE_SYNC_INTERVAL_SECONDS=5
AWS_IOT_LIVE_INTERVAL_SECONDS=3
```

See `pi/docs/home-assistant-matter.md`.

## Tuya Breakers

Tuya Cloud is backup only. Keep `kahrabaiq-tuya-breaker-poller` disabled for the final Home Assistant breaker flow:

```bash
sudo systemctl stop kahrabaiq-tuya-breaker-poller
sudo systemctl disable kahrabaiq-tuya-breaker-poller
```

Tuya breaker credentials, if retained, belong in `/etc/kahrabaiq/pi.env`, not in committed files. See `pi/docs/tuya-setup.md`.
