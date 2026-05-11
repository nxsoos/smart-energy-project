# KahrabaIQ

KahrabaIQ is a smart energy and home-safety platform built around an AWS cloud backend, a Flutter mobile app, a Raspberry Pi local hub, and ESP32 room sensors. It supports secure Pi kiosk access, local device control through Tuya and Home Assistant/Matter, local SQLite buffering, and cloud synchronization through AWS.

## System Overview

```text
Mobile user
  -> Flutter app
  -> Cognito authentication
  -> KahrabaIQ API
  -> DynamoDB app state

Raspberry Pi touchscreen
  -> Deployed AWS-hosted kiosk dashboard
  -> Local Pi agent at 127.0.0.1
  -> Short-lived kiosk session token

ESP32 room sensor
  -> Pi sensor receiver
  -> Local SQLite state buffer
  -> Pi agent live-state sync
  -> KahrabaIQ API

Device command
  -> AWS command queue
  -> Pi command runner
  -> Tuya Cloud or Home Assistant/Matter
  -> Local device state update
```

The browser never receives the long-lived `PI_DEVICE_TOKEN`. That token stays on the Raspberry Pi. The local Pi agent exchanges it for short-lived kiosk tokens that are scoped to one Pi/home.

## Pi and ESP32 First-Boot Provisioning

The Raspberry Pi must provision itself and the ESP32 before the locked dashboard starts. The recommended hardware setup uses the built-in Pi Wi-Fi plus a TL-WN725N USB Wi-Fi adapter:

```text
wlan0 = built-in Pi Wi-Fi
  -> permanent home Wi-Fi connection
  -> dashboard, backend/cloud, local receiver, and normal ESP32 communication

wlan1 = TL-WN725N USB Wi-Fi adapter
  -> temporary setup/provisioning only
  -> turned off after successful provisioning
```

First boot flow:

1. `kahrabaiq-provisioning.service` starts before the dashboard and checks `/var/lib/kahrabaiq/provisioned.json`.
2. If the marker does not exist, the Pi starts `KahrabaIQ-Pi-Setup` on `wlan1`.
3. `kahrabaiq-setup-screen.service` opens a locked setup screen on the Pi display with hotspot instructions, QR pairing, and sensor setup progress.
4. The installer connects a phone/laptop to the Pi setup hotspot and opens the setup page on port `8080`.
5. The setup page collects the home Wi-Fi SSID/password and optional ESP32 device values. It does not ask for `home_id`.
6. The Pi connects `wlan0` to the home Wi-Fi and verifies backend access.
7. The Pi requests a short-lived QR pairing token from the backend and displays it on the setup screen.
8. The user scans the QR code in the KahrabaIQ mobile app. The scanning user becomes `home_admin`.
9. After backend pairing returns the real `home_id`, the setup screen shows `Home paired successfully. Waiting for sensors to connect to the Pi...`.
10. The Pi uses `wlan1` to connect to the ESP32 setup hotspot `KahrabaIQ-ESP32-Setup`.
11. The Pi detects the ESP32 setup gateway from `wlan1` and posts the same home Wi-Fi credentials, real `home_id`, Pi sensor URL, Pi ID, device ID, and device key to `http://<detected-gateway>/provision`.
12. The ESP32 saves the config, reboots, joins the home Wi-Fi, and starts posting to the Pi sensor receiver.
13. The Pi disconnects and turns off `wlan1`.
14. The Pi writes `/var/lib/kahrabaiq/provisioned.json` and only then allows normal services and the locked kiosk dashboard to start.

Normal boot flow:

```text
provisioned marker exists
  -> wlan1 remains off
  -> wlan0 connects to home Wi-Fi
  -> Pi services start
  -> locked dashboard starts
```

Admin unlock flow:

```text
Long press the dashboard top-right corner for 5 seconds
or press Ctrl+Alt+A
  -> enter platform admin credentials or recovery PIN
  -> backend confirms platform_admin for cloud unlock
  -> view status, restart dashboard, exit kiosk to desktop, return to kiosk, or enter maintenance provisioning
  -> press Lock Dashboard to return to locked kiosk mode without rebooting
```

Cloud Pi unlock only unlocks the browser maintenance overlay. It does not unlock Raspberry Pi OS, SSH, root, or arbitrary sudo access.

See `pi/README.md`, `pi/docs/first-boot-provisioning.md`, and `esp32/README.md` for device-specific details.

## Repository Structure

```text
smart-energy-project/
  .github/
    workflows/
      ci.yml                         GitHub Actions checks for PRs and pushes

  smart_energy_app/
    lib/
      core/                          App-wide config, theme, constants, utilities
      features/                      Feature screens and flows
      shared/                        Shared models and KahrabaIQ API services
    test/                            Flutter widget/unit tests
    pubspec.yaml                     Flutter dependencies and SDK constraints

  seniorproject-backend/
    api_server.py                    Main AWS API: auth, homes, pairing, Pi sync, kiosk, commands
    aws_cloud_store.py               DynamoDB path-store and summary/command helpers
    main.py                          AI service entry point
    home_assistant_controller.py     Shared Home Assistant API helper used by backend paths
    occupancy_utils.py               Occupancy logic shared with Pi modules
    timestamp_utils.py               Timezone/timestamp helpers
    requirements.txt                 Backend/API Python dependencies
    docs/
      deployment/                    AWS deployment notes
      ai/                            AI scenario notes
    devices/
      models/                        AI model artifacts
      predict_ai.py                  Local AI prediction helper
      train_ai_model.py              AI training helper
      test_ai_guardrails.py          AI validation tests
      test_occupancy_scenarios.py    Occupancy scenario tests
      requirements-ai.txt            AI-specific Python dependencies

  pi/
    .env.sample                      Safe Pi runtime environment template
    README.md                        Pi-specific deployment guide
    agent/
      pi_agent.py                    Local token bridge, heartbeat, live sync, command polling, admin unlock
      pi_provisioning.py             First-boot Pi Wi-Fi and ESP32 provisioning portal
      esp32_receiver.py              Local ESP32 sensor receiver
      summary_sync.py                Hourly/daily local summary sync
      aws_remote_command_runner.py   Polls AWS queued commands and executes locally
      local_command_controller.py    Tuya and Home Assistant/Matter command execution
      home_assistant_controller.py   Local Home Assistant API client
      local_state_store.py           SQLite-backed local path store
      occupancy_utils.py             Pi-local occupancy helper copy
      timestamp_utils.py             Pi-local timestamp helper copy
    docs/
      first-boot-provisioning.md     Pi/ESP32 first-boot setup and admin maintenance flow
      kiosk-setup.md                 Pi kiosk browser setup and troubleshooting
      home-assistant-matter.md       Local Home Assistant and Matter stack setup
      tuya-setup.md                  Tuya credential and breaker setup
    home-assistant/
      docker-compose.yml             Home Assistant and Matter containers
    scripts/
      install-pi.sh                  Pi dependency and service install script
      launch-kiosk.sh                Chromium kiosk launcher
      setup-home-stack.sh            Home Assistant/Matter container setup
    systemd/
      kahrabaiq-provisioning.service
      kahrabaiq-setup-screen.service
      kahrabaiq-agent.service
      kahrabaiq-sensor-receiver.service
      kahrabaiq-summary-sync.service
      kahrabaiq-command-runner.service
      kahrabaiq-home-stack.service
      kahrabaiq-kiosk-browser.service

  esp32/
    README.md                        ESP32 firmware overview
    libraries.txt                    Arduino library requirements
    firmware/
      ESP32_code.c                   ESP32 sensor/provisioning firmware
    docs/
      provisioning-contract.md       ESP32 HTTP provisioning contract
      flashing.md                    Firmware flashing instructions
      wiring.md                      Sensor wiring and pins

  .env.sample                        Safe root environment template
  .gitignore                         Ignore rules for local secrets/build artifacts
  README.md                          This file
```

## AWS Resources Required

| AWS Resource | Required | Purpose |
| --- | --- | --- |
| DynamoDB table `KahrabaIQApp` | Yes | App path-store state: users, homes, devices, Pi records, pairing tokens, kiosk state. |
| DynamoDB table `SmartEnergySummaries` | Yes | Hourly/daily summaries and remote command queue records. |
| Cognito User Pool | Yes | Phone app user authentication. |
| Cognito App Client | Yes | Flutter app sign-in client. |
| Cognito Identity Pool | Optional | Only needed if the app directly signs AWS requests. |
| API hosting | Yes | Runs `seniorproject-backend/api_server.py`. App Runner, ECS/Fargate, EC2, or Elastic Beanstalk are valid. |
| IAM role for API runtime | Yes | Grants DynamoDB read/write/query permissions. |
| ACM certificate | Recommended | HTTPS certificate for `api.your-domain.com`. |
| Route 53 or external DNS | Recommended | Points your API domain to the deployed backend. |
| CloudWatch Logs | Recommended | Runtime logs for API hosting. |
| Secrets Manager or SSM Parameter Store | Recommended | Store production secrets instead of plain env values. |

## AWS DynamoDB Configuration

Create two tables in the same region as the backend runtime.

`KahrabaIQApp`:

```text
Partition key: PK  (String)
Sort key:      SK  (String)
Billing mode:  On-demand is simplest for development
```

`SmartEnergySummaries`:

```text
Partition key: PK  (String)
Sort key:      SK  (String)
Billing mode:  On-demand is simplest for development
```

The backend uses generic path-store records in `KahrabaIQApp` and summary/remote-command records in `SmartEnergySummaries`.

## AWS Cognito Configuration

Create a Cognito User Pool for phone app users.

Required values:

```env
COGNITO_USER_POOL_ID=eu-west-1_xxxxxxxxx
COGNITO_APP_CLIENT_ID=xxxxxxxxxxxxxxxxxxxxxxxxxx
COGNITO_ADMIN_GROUP=SmartEnergyAdmins
COGNITO_MEMBER_GROUP=SmartEnergyMembers
```

Recommended setup:

- Enable email sign-in.
- Create the app client without a client secret for Flutter mobile use.
- Create groups `SmartEnergyAdmins` and `SmartEnergyMembers` if you use group-based policy mapping.
- Add your platform admin email to `PLATFORM_ADMIN_EMAILS` in the backend environment.
- Use the same Cognito app client values on the Pi for platform-admin kiosk unlock.

If the Flutter app uses direct AWS request signing, also configure:

```env
COGNITO_IDENTITY_POOL_ID=eu-west-1:xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

## AWS IAM Permissions

The backend runtime role needs access to both DynamoDB tables.

Minimum policy shape:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:DeleteItem",
        "dynamodb:Query",
        "dynamodb:Scan"
      ],
      "Resource": [
        "arn:aws:dynamodb:eu-west-1:ACCOUNT_ID:table/KahrabaIQApp",
        "arn:aws:dynamodb:eu-west-1:ACCOUNT_ID:table/SmartEnergySummaries"
      ]
    }
  ]
}
```

Replace `eu-west-1` and `ACCOUNT_ID` with your real AWS region/account.

## Backend Environment Variables

Use these on the deployed API service.

Core AWS/backend values:

```env
STORAGE_BACKEND=aws
AWS_REGION=eu-west-1
AWS_DEFAULT_REGION=eu-west-1
AWS_DYNAMODB_APP_TABLE=KahrabaIQApp
AWS_DYNAMODB_SUMMARIES_TABLE=SmartEnergySummaries
PLATFORM_ADMIN_EMAILS=admin@kahrabaiq.com
AI_SERVICE_URL=https://YOUR_AI_SERVICE_URL
INTERNAL_SERVICE_TOKEN=change_me_to_a_long_random_secret
HOME_MEMBER_LIMIT=3
PAIRING_TOKEN_TTL_SECONDS=900
HOME_INVITE_TTL_SECONDS=604800
```

Cognito values:

```env
COGNITO_USER_POOL_ID=
COGNITO_APP_CLIENT_ID=
COGNITO_IDENTITY_POOL_ID=
COGNITO_ADMIN_GROUP=SmartEnergyAdmins
COGNITO_MEMBER_GROUP=SmartEnergyMembers
```

Kiosk/Pi security values:

```env
KIOSK_SESSION_SECRET=change_me_to_a_long_random_secret
KIOSK_SESSION_TTL_SECONDS=600
KIOSK_COMMAND_TTL_SECONDS=300
```

Home Assistant/Matter values used by backend command decisions:

```env
HOME_ASSISTANT_URL=http://homeassistant.local:8123
HOME_ASSISTANT_TOKEN=change_me
HOME_ASSISTANT_COMMAND_MODE=auto
HOME_ASSISTANT_TIMEOUT_SECONDS=5
HA_SYNC_INTERVAL_SECONDS=30
MATTER_SOCKET_SWITCH_ENTITY_ID=switch.socket_switch
MATTER_AC_SWITCH_ENTITY_ID=switch.ac_switch
```

Tuya values for local command execution on Pi:

```env
TUYA_ACCESS_ID=your_tuya_cloud_access_id
TUYA_ACCESS_SECRET=your_tuya_cloud_access_secret
TUYA_API_ENDPOINT=https://openapi.tuyaeu.com
TUYA_BREAKER_01_DEVICE_ID=your_switch_breaker_device_id
TUYA_BREAKER_02_DEVICE_ID=your_ac_breaker_device_id
TUYA_VERIFY_ATTEMPTS=7
```

Do not commit real values for secrets. Use AWS service environment variables, Secrets Manager, SSM Parameter Store, or `/etc/kahrabaiq/pi.env` on the Pi.

## Domain And HTTPS Setup

Recommended public API domain:

```text
https://api.your-domain.com
```

Required steps:

1. Deploy `seniorproject-backend/api_server.py` to AWS App Runner, ECS/Fargate, EC2, or Elastic Beanstalk.
2. Request an ACM certificate for `api.your-domain.com` in the correct region for the hosting choice.
3. Attach the custom domain/certificate to the backend service or load balancer.
4. Add DNS record `api.your-domain.com` pointing to the AWS target.
5. Verify the API responds over HTTPS.

Verification:

```bash
curl https://api.your-domain.com/api/health
```

The Pi kiosk URL should normally be:

```env
KIOSK_DASHBOARD_URL=https://dashboard.your-domain.com
```

For the EC2-hosted production dashboard, use the dashboard domain instead:

```env
KIOSK_DASHBOARD_URL=https://dashboard.kahrabaiq.com
```

## Cloud Backend Local Run

```bash
cd seniorproject-backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn api_server:app --reload
```

Local health check:

```bash
curl http://127.0.0.1:8000/api/health
```

## Flutter App

Run locally:

```bash
cd smart_energy_app
flutter pub get
flutter run
```

Typical runtime defines:

```bash
flutter run \
  --dart-define=KAHRABAIQ_API_URL=https://api.your-domain.com \
  --dart-define=BACKEND_API_URL=https://api.your-domain.com \
  --dart-define=COGNITO_USER_POOL_ID=your_pool_id \
  --dart-define=COGNITO_APP_CLIENT_ID=your_client_id \
  --dart-define=COGNITO_IDENTITY_POOL_ID=your_identity_pool_id
```

## Raspberry Pi Runtime

The Pi acts as the local hub. It runs:

- `kahrabaiq-agent`: kiosk token bridge, heartbeat, live state sync, command polling, ESP32 provisioning.
- `kahrabaiq-sensor-receiver`: receives ESP32 sensor posts and writes local SQLite state.
- `kahrabaiq-summary-sync`: builds and uploads hourly/daily summaries.
- `kahrabaiq-command-runner`: executes AWS-queued Tuya and Home Assistant/Matter commands locally.
- `kahrabaiq-home-stack`: starts Home Assistant and Matter containers.
- `kahrabaiq-kiosk-browser`: hardens common X11/Openbox escape shortcuts, launches Chromium against the deployed kiosk dashboard, and restarts quickly if the browser exits.

Pi runtime env file:

```text
/etc/kahrabaiq/pi.env
```

Required Pi values:

```env
HOME_ID=
PI_ID=pi_unique_id
PI_DEVICE_TOKEN=change_me
KAHRABAIQ_API_URL=https://api.kahrabaiq.com
KIOSK_DASHBOARD_URL=https://dashboard.kahrabaiq.com
PI_AGENT_PORT=5010
PI_SENSOR_PORT=5000
PI_LOCAL_BASE_URL=
PI_SENSOR_BASE_URL=
ESP32_DEVICE_KEY=change_me
HOME_ASSISTANT_URL=http://127.0.0.1:8123
HOME_ASSISTANT_TOKEN=change_me_after_creating_a_long_lived_access_token
HOME_ASSISTANT_COMMAND_MODE=queue
MATTER_SOCKET_SWITCH_ENTITY_ID=switch.socket_switch
MATTER_AC_SWITCH_ENTITY_ID=switch.ac_switch
```

Leave `PI_LOCAL_BASE_URL` and `PI_SENSOR_BASE_URL` empty for normal installs. The Pi sends its current Wi-Fi IP-derived URLs to ESP32 during provisioning and to the backend on heartbeat. Use `HOME_ASSISTANT_URL=http://127.0.0.1:8123` when Home Assistant runs on the same Pi, including Docker host-network mode.

The production dashboard is served by EC2 at `https://dashboard.kahrabaiq.com`. The backend learns each Pi public IP from heartbeat and only serves the dashboard when the request IP matches a fresh Pi record with dashboard access enabled and the browser has a valid Pi-issued kiosk session cookie. The Pi launcher gets that cookie through `/dashboard/session/start`; laptops on the same Wi-Fi public IP are blocked unless they have that Pi kiosk session. Unpaired Pis get a waiting-for-pairing screen; paired Pis get live sensor data with AWS IoT realtime updates and polling fallback.

Install flow on the Pi:

```bash
KAHRABAIQ_REPO_DIR=/opt/kahrabaiq /opt/kahrabaiq/pi/scripts/install-pi.sh
```

After configuring `/etc/kahrabaiq/pi.env`:

```bash
sudo systemctl enable --now \
  kahrabaiq-agent \
  kahrabaiq-sensor-receiver \
  kahrabaiq-summary-sync \
  kahrabaiq-command-runner \
  kahrabaiq-kiosk-browser
```

Home Assistant and Matter setup:

```bash
KAHRABAIQ_REPO_DIR=/opt/kahrabaiq /opt/kahrabaiq/pi/scripts/setup-home-stack.sh
```

Pi documentation:

- `pi/README.md`
- `pi/docs/kiosk-setup.md`
- `pi/docs/home-assistant-matter.md`
- `pi/docs/tuya-setup.md`

## ESP32 Firmware

Firmware lives in:

```text
esp32/firmware/ESP32_code.c
```

Provisioning support includes:

- Setup hotspot: `KahrabaIQ-ESP32-Setup`
- Setup URL: auto-detected by the Pi from the `wlan1` gateway after it joins the ESP32 setup hotspot
- `GET /status`
- `POST /provision`
- `POST /reset`
- mDNS hostname: `kahrabaiq-esp32.local`

ESP32 documentation:

- `esp32/README.md`
- `esp32/docs/provisioning-contract.md`
- `esp32/docs/flashing.md`
- `esp32/docs/wiring.md`

## Pairing And Roles

- The Pi has a long-lived `PI_ID` and `PI_DEVICE_TOKEN` configured locally.
- The Pi obtains short-lived kiosk tokens from the AWS API.
- The kiosk dashboard can display a pairing QR payload.
- The first phone user who scans the Pi QR becomes `home_admin`.
- The `home_admin` mobile panel can generate invite QR codes for `viewer` or `member` access and remove existing viewers/members.
- The fixed global admin account is configured with `PLATFORM_ADMIN_EMAILS=admin@kahrabaiq.com` and can delete homes or remove members across all homes.
- The same platform admin credentials can unlock Pi browser maintenance controls when `PI_CLOUD_ADMIN_UNLOCK_ENABLED=true`; local recovery PIN remains the offline fallback.
- Deleting a home marks the linked Pi as `unpaired` and queues a `reset_pairing` command so it returns to pairing mode when online.
- `HOME_MEMBER_LIMIT` caps the total non-admin users per home: `member + viewer <= 3` by default.

## Verification

Backend and Pi Python checks:

```bash
python3 -m py_compile \
  seniorproject-backend/api_server.py \
  seniorproject-backend/aws_cloud_store.py \
  seniorproject-backend/main.py \
  pi/agent/*.py
```

Flutter checks:

```bash
cd smart_energy_app
flutter analyze
flutter test
```

Whitespace check:

```bash
git diff --check
```

CI runs these checks on pull requests and branch pushes through `.github/workflows/ci.yml`.

## Security Notes

- Do not commit real API keys, Pi device tokens, Tuya secrets, kiosk secrets, Home Assistant tokens, or local `.env` files.
- Put Pi runtime secrets in `/etc/kahrabaiq/pi.env` on the Pi.
- Keep production backend secrets in AWS service environment variables, Secrets Manager, or SSM Parameter Store.
- The deployed kiosk dashboard must use the local Pi agent session bridge; it must not receive `PI_DEVICE_TOKEN`.
- Rotate any secret that was ever committed to git history.

## Production Readiness Checklist

- DynamoDB tables exist and use the configured table names.
- Backend runtime IAM role can read/write/query both DynamoDB tables.
- Cognito User Pool and App Client are configured.
- Backend is deployed behind HTTPS at `api.your-domain.com`.
- Flutter app uses the deployed API URL and Cognito IDs.
- Pi has `/etc/kahrabaiq/pi.env` with real Pi, API, Tuya, Home Assistant, and ESP32 values.
- Home Assistant onboarding is complete and Matter devices are paired.
- ESP32 firmware is flashed and provisioned to the Pi receiver URL.
- Kiosk opens the deployed dashboard and receives only short-lived kiosk tokens.

## Current Direction

KahrabaIQ is AWS-only. App/backend state is stored through AWS services, the phone app authenticates through Cognito, and Pi hardware integrations run locally with secure sync to the cloud API.
