# KahrabaIQ

KahrabaIQ is an AI-powered smart energy and electrical safety platform that turns a home into a live, intelligent, and locally resilient energy system. It combines a Flutter mobile app, an AWS cloud backend, a Raspberry Pi home hub, ESP32 room sensing, a locked kiosk dashboard, and local device control through Home Assistant, Matter, and Tuya.

The project is designed for real-world smart-home behavior: monitor energy, detect unsafe conditions, understand occupancy, control connected breakers and switches, sync local hardware state to the cloud, and generate AI-driven recommendations from live and historical usage data.

## esp32 connection to thr internet
curl -i -X POST http://192.168.4.1/provision \
  -H "Content-Type: application/json" \
  -d '{"ssid":"Nassernxs","password":"nasser04","pi_base_url":"http://10.45.212.94:5000","home_id":"home_001","pi_id":"pi_home_001","device_id":"esp32_01","device_key":"esp32_01_key_123"}' 
## Why It Exists

Most smart-home systems either focus on comfort or basic remote control. KahrabaIQ goes further: it treats energy, safety, occupancy, automation, and intelligence as one connected system.

KahrabaIQ can:

- Monitor room conditions, breaker readings, device state, power, voltage, current, energy, and cost.
- Detect safety-critical states such as smoke/gas, stale sensors, stale breaker data, and abnormal consumption.
- Understand occupancy and flag energy waste when devices are running in empty spaces.
- Queue commands from the cloud and execute them locally through the Raspberry Pi.
- Keep the dashboard fast through local SQLite state while still syncing compact state to AWS.
- Produce AI predictions, alerts, recommendations, chat responses, and demo scenarios.
- Secure the kiosk dashboard without exposing long-lived Pi credentials to the browser.

## System Architecture

```text
Mobile user
  -> Flutter mobile app
  -> Cognito authentication
  -> KahrabaIQ FastAPI backend
  -> DynamoDB app state, summaries, AI records, command queue

Public website / dashboard
  -> Next.js bilingual web experience
  -> Cloud-hosted dashboard and kiosk surface
  -> Short-lived Pi-issued kiosk session

Raspberry Pi home hub
  -> First-boot provisioning
  -> Local SQLite state buffer
  -> ESP32 sensor receiver
  -> AWS live-state sync
  -> Remote command runner
  -> Home Assistant / Matter / Tuya device execution
  -> Locked Chromium kiosk dashboard

ESP32 room sensor
  -> Temperature, humidity, light, motion, sound, smoke/gas readings
  -> Pi-led Wi-Fi provisioning
  -> Local posts to the Pi sensor receiver

AI engine
  -> Immediate safety/rule alerts
  -> Routine and anomaly checks
  -> ML-backed predictions from summaries and latest state
  -> Chatbot and scenario simulation support
```

## Platform Components

| Component | Path | Purpose |
| --- | --- | --- |
| Mobile app | `KahrabaIQ-mobile-app/` | Flutter app for authentication, dashboards, device control, AI insights, QR pairing, roles, and demo scenarios. |
| Backend | `KahrabaIQ-backend/` | FastAPI service for homes, users, Pi sync, kiosk sessions, AI inference, chatbot APIs, command queues, Cognito auth, and DynamoDB persistence. |
| Website/dashboard | `KahrabaIQ-website/` | Professional bilingual Next.js website and cloud dashboard surface for presentation and kiosk access. |
| Raspberry Pi runtime | `pi/` | Local hub services for provisioning, sensor receiving, SQLite buffering, command execution, live sync, summaries, Home Assistant/Matter, and kiosk launch. |
| ESP32 firmware | `esp32/` | Room sensor firmware with setup hotspot, provisioning API, saved Wi-Fi/Pi config, and periodic sensor uploads. |

## Repository Structure

```text
smart-energy-project/
  KahrabaIQ-mobile-app/
    lib/                         Flutter app source
    test/                        Flutter tests
    pubspec.yaml                 Flutter dependencies

  KahrabaIQ-backend/
    api_server.py                Main FastAPI cloud API
    main.py                      AI model, rules, guardrails, and chat logic
    aws_cloud_store.py           DynamoDB helpers
    devices/                     AI dataset, model, validation, and inference scripts
    docs/                        Backend, deployment, AI, and settings documentation
    requirements.txt             Python dependencies

  KahrabaIQ-website/
    app/                         Next.js App Router source
    data/                        English and Arabic localized content
    public/                      Brand, mockup, and team assets
    package.json                 Website scripts and dependencies

  pi/
    agent/                       Pi services and local integrations
    docs/                        Provisioning, kiosk, Home Assistant, Matter, and Tuya docs
    scripts/                     Pi install, kiosk, and setup scripts
    systemd/                     Production service units
    home-assistant/              Home Assistant and Matter container setup

  esp32/
    firmware/ESP32_code.c        ESP32 firmware
    docs/                        Flashing, wiring, and provisioning contract
    libraries.txt                Arduino library requirements

  .github/workflows/ci.yml       CI checks
  .env.sample                    Safe root environment template
  README.md                      Project overview
```

## Core Capabilities

### Real-Time Energy Intelligence

KahrabaIQ tracks live and historical electrical behavior across connected breakers and smart devices. It stores compact current state for dashboards, hourly and daily summaries for trends, and command history for deeper context.

The system can surface:

- Current power, voltage, current, energy, and estimated cost.
- Daily and monthly usage summaries.
- Device-level state for AC, socket, light, and breaker entities.
- Waste patterns such as high power while the room appears empty.
- Stale or missing data from sensors and breaker sources.

### Safety And Awareness

The ESP32 room sensor gives the platform environmental awareness. Smoke/gas, temperature, humidity, motion, light, sound, and freshness signals help KahrabaIQ distinguish normal usage from unsafe or wasteful behavior.

Critical conditions are handled through immediate rules instead of waiting for a slower ML cycle. That keeps safety alerts responsive and explainable.

### Local-First Hardware Control

The Raspberry Pi is the local authority for hardware. Cloud commands are queued remotely, then pulled and executed by the Pi through Home Assistant, Matter, or Tuya depending on configuration.

This design keeps device control close to the home while still enabling cloud dashboards, mobile access, AI, and remote administration.

### AI Insights

The backend includes a lightweight AI layer built for the project data model. It combines rule-based guardrails, routine checks, historical summaries, and scikit-learn model artifacts.

Prediction and insight targets include:

- `waste_event`
- `anomaly_label`
- `recommendation_type`
- `next_hour_total_energy_kWh`
- `next_hour_total_cost_BHD`

The AI system is intentionally layered:

- Level 1: immediate safety and obvious system alerts.
- Level 2: periodic routine/anomaly checks using recent history and thresholds.
- Level 3: full ML prediction after hourly summaries are available.

The Flutter app also includes Demo Scenario Mode, which can simulate normal usage, AC left on, socket waste, unusual routine, high energy, smoke/gas, and stale data without controlling real hardware.

### Secure Kiosk Experience

The Pi launches a locked Chromium dashboard after provisioning completes. The browser never receives the long-lived `PI_DEVICE_TOKEN`. Instead, the local Pi agent exchanges that token for a short-lived kiosk session scoped to that Pi and home.

Admin unlock is intentionally limited. Cloud admin credentials or an offline recovery PIN can unlock the browser maintenance overlay, but this does not grant Raspberry Pi OS access, SSH access, root access, or arbitrary sudo permissions.

## Security Model

- `PI_DEVICE_TOKEN` stays on the Raspberry Pi in `/etc/kahrabaiq/pi.env`.
- The browser receives only short-lived kiosk sessions.
- Cognito handles mobile authentication.
- The first user who scans a new Pi pairing QR becomes `home_admin`.
- Home admins can invite or remove members/viewers within configured limits.
- Platform admins are configured through backend environment values and can perform global maintenance actions.
- Secrets must live in environment variables, AWS Secrets Manager, SSM Parameter Store, or Pi-local env files.
- Real API keys, Pi tokens, Tuya secrets, Home Assistant tokens, kiosk secrets, and `.env` files must not be committed.

## First-Boot Provisioning

KahrabaIQ supports a guided Pi-led provisioning flow for both the Raspberry Pi and ESP32 sensor.

Recommended network setup:

```text
wlan0 = built-in Raspberry Pi Wi-Fi
  -> permanent home Wi-Fi connection
  -> backend access, dashboard, Pi services, normal ESP32 communication

wlan1 = TL-WN725N USB Wi-Fi adapter
  -> temporary setup and ESP32 provisioning
  -> disabled after successful provisioning
```

Provisioning sequence:

1. The Pi boots and checks `/var/lib/kahrabaiq/provisioned.json`.
2. If the marker is missing, the Pi starts the `KahrabaIQ-Pi-Setup` hotspot on `wlan1`.
3. The locked setup screen opens on the Pi display with hotspot instructions and pairing progress.
4. An installer connects to the setup portal and enters home Wi-Fi credentials.
5. The Pi connects `wlan0` to the home network and verifies backend access.
6. The Pi requests a short-lived QR pairing token from the backend.
7. The user scans the QR code in the Flutter app and becomes the home admin.
8. The backend returns the real `home_id` after pairing succeeds.
9. The Pi connects `wlan1` to the ESP32 setup hotspot `KahrabaIQ-ESP32-Setup`.
10. The Pi provisions the ESP32 with home Wi-Fi, `home_id`, Pi sensor URL, Pi ID, device ID, and device key.
11. The ESP32 reboots, joins home Wi-Fi, and starts posting sensor data to the Pi.
12. The Pi turns off `wlan1`, writes the provisioned marker, and starts normal services and the kiosk dashboard.

Normal boot is much simpler:

```text
provisioned marker exists
  -> wlan1 remains off
  -> wlan0 connects to home Wi-Fi
  -> Pi services start
  -> locked dashboard starts
```

Detailed provisioning documentation lives in `pi/docs/first-boot-provisioning.md` and `esp32/docs/provisioning-contract.md`.

## AWS Resources

KahrabaIQ expects an AWS-backed production environment.

| AWS Resource | Required | Purpose |
| --- | --- | --- |
| DynamoDB table `KahrabaIQApp` | Yes | Users, homes, devices, Pi records, kiosk state, pairing tokens, AI records, and app path-store state. |
| DynamoDB table `SmartEnergySummaries` | Yes | Hourly summaries, daily summaries, and remote command queue records. |
| Cognito User Pool | Yes | Mobile user authentication. |
| Cognito App Client | Yes | Flutter sign-in client. |
| API hosting | Yes | Runs `KahrabaIQ-backend/api_server.py`. EC2, App Runner, ECS/Fargate, or Elastic Beanstalk are valid. |
| IAM runtime role | Yes | Grants backend access to DynamoDB. |
| ACM certificate | Recommended | HTTPS for the API and dashboard domains. |
| Route 53 or external DNS | Recommended | Points production domains to the deployed services. |
| CloudWatch Logs | Recommended | Runtime observability. |
| Secrets Manager or SSM Parameter Store | Recommended | Safer production secret storage. |

Required DynamoDB table shape:

```text
KahrabaIQApp
  Partition key: PK (String)
  Sort key:      SK (String)

SmartEnergySummaries
  Partition key: PK (String)
  Sort key:      SK (String)
```

On-demand billing is the simplest option for development and demos.

## Environment Configuration

Use `.env.sample` files as safe templates. Never commit real production values.

Backend essentials:

```env
STORAGE_BACKEND=aws
AWS_REGION=eu-west-1
AWS_DEFAULT_REGION=eu-west-1
AWS_DYNAMODB_APP_TABLE=KahrabaIQApp
AWS_DYNAMODB_SUMMARIES_TABLE=SmartEnergySummaries
PLATFORM_ADMIN_EMAILS=admin@kahrabaiq.com
INTERNAL_SERVICE_TOKEN=change_me_to_a_long_random_secret
HOME_MEMBER_LIMIT=3
PAIRING_TOKEN_TTL_SECONDS=900
HOME_INVITE_TTL_SECONDS=604800
KIOSK_SESSION_SECRET=change_me_to_a_long_random_secret
KIOSK_SESSION_TTL_SECONDS=600
```

Cognito essentials:

```env
COGNITO_USER_POOL_ID=eu-west-1_xxxxxxxxx
COGNITO_APP_CLIENT_ID=xxxxxxxxxxxxxxxxxxxxxxxxxx
COGNITO_IDENTITY_POOL_ID=eu-west-1:xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
COGNITO_ADMIN_GROUP=SmartEnergyAdmins
COGNITO_MEMBER_GROUP=SmartEnergyMembers
```

Pi runtime values normally live in:

```text
/etc/kahrabaiq/pi.env
```

Pi essentials:

```env
HOME_ID=
PI_ID=pi_unique_id
PI_DEVICE_TOKEN=change_me
KAHRABAIQ_API_URL=https://api.kahrabaiq.com
KIOSK_DASHBOARD_URL=https://dashboard.kahrabaiq.com
PI_AGENT_PORT=5010
PI_SENSOR_PORT=5000
ESP32_DEVICE_KEY=change_me
HOME_ASSISTANT_URL=http://127.0.0.1:8123
HOME_ASSISTANT_TOKEN=change_me_after_creating_a_long_lived_access_token
REMOTE_COMMAND_SOURCE=ec2
```

Home Assistant, Matter, Tuya, AI, and kiosk options are documented in the component READMEs and sample env files.

## Local Development

### Backend

```bash
cd KahrabaIQ-backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn api_server:app --reload
```

Health check:

```bash
curl http://127.0.0.1:8000/api/health
```

### Mobile App

```bash
cd KahrabaIQ-mobile-app
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

Enable presentation scenarios:

```bash
flutter run \
  --dart-define=ENABLE_DEMO_SCENARIOS=true \
  --dart-define=USE_BACKEND_SCENARIO_AI=true
```

### Website

```bash
cd KahrabaIQ-website
npm install
npm run dev
```

Open:

```text
http://localhost:3000/en
http://localhost:3000/ar
```

### Raspberry Pi

Copy the repository to `/opt/kahrabaiq` on the Pi, then run:

```bash
KAHRABAIQ_REPO_DIR=/opt/kahrabaiq /opt/kahrabaiq/pi/scripts/install-pi.sh
```

After configuring `/etc/kahrabaiq/pi.env`, enable the required services. See `pi/README.md` for the exact production service list and hardware-specific notes.

Home Assistant and Matter setup:

```bash
KAHRABAIQ_REPO_DIR=/opt/kahrabaiq /opt/kahrabaiq/pi/scripts/setup-home-stack.sh
```

### ESP32

Firmware lives in:

```text
esp32/firmware/ESP32_code.c
```

The ESP32 starts in setup mode when no Wi-Fi config is saved:

```text
SSID: KahrabaIQ-ESP32-Setup
Password: kahrabaiq123
```

The normal production path is Pi-led provisioning. Manual flashing, wiring, and HTTP contract details are in `esp32/README.md` and `esp32/docs/`.

## Verification

Backend and Pi Python checks:

```bash
python3 -m py_compile \
  KahrabaIQ-backend/api_server.py \
  KahrabaIQ-backend/aws_cloud_store.py \
  KahrabaIQ-backend/main.py \
  pi/agent/*.py
```

Flutter checks:

```bash
cd KahrabaIQ-mobile-app
flutter analyze
flutter test
```

Website checks:

```bash
cd KahrabaIQ-website
npm run lint
npm run build
```

Whitespace check:

```bash
git diff --check
```

CI runs project checks through `.github/workflows/ci.yml` on pull requests and branch pushes.

## Production Checklist

- DynamoDB tables exist with the expected names and key schema.
- Backend runtime IAM role can read, write, query, update, delete, and scan required DynamoDB tables.
- Cognito User Pool and App Client are configured for the Flutter app.
- Backend is deployed behind HTTPS at the configured API domain.
- Dashboard/website deployment is reachable over HTTPS.
- Flutter app uses the production API URL and Cognito IDs.
- Pi has `/etc/kahrabaiq/pi.env` with real Pi, API, kiosk, Home Assistant, Matter/Tuya, and ESP32 values.
- Home Assistant onboarding is complete and required entities are configured.
- ESP32 firmware is flashed and provisioned to the Pi receiver URL.
- Kiosk opens the deployed dashboard and receives only short-lived kiosk sessions.
- Real secrets are stored outside git.

## Documentation Index

- `KahrabaIQ-backend/README.md`: backend, AI pipeline, chatbot, API behavior, and model scripts.
- `KahrabaIQ-mobile-app/README.md`: Flutter app setup, runtime defines, tests, and Demo Scenario Mode.
- `KahrabaIQ-website/README.md`: bilingual Next.js website, content editing, assets, localization, and deployment.
- `pi/README.md`: Raspberry Pi services, installation, provisioning, kiosk security, Home Assistant, Matter, and command execution.
- `pi/docs/first-boot-provisioning.md`: full Pi and ESP32 first-boot provisioning flow.
- `pi/docs/kiosk-setup.md`: kiosk setup and troubleshooting.
- `pi/docs/home-assistant-matter.md`: Home Assistant and Matter integration.
- `pi/docs/tuya-setup.md`: Tuya setup and fallback control path.
- `esp32/README.md`: ESP32 firmware behavior and provisioning.
- `esp32/docs/flashing.md`: firmware flashing instructions.
- `esp32/docs/wiring.md`: sensor wiring and pins.
- `esp32/docs/provisioning-contract.md`: ESP32 provisioning HTTP API.

## Current Direction

KahrabaIQ is AWS-backed and local-hardware aware. The cloud owns authentication, app state, AI, summaries, pairing, and command queues. The Raspberry Pi owns local sensing, buffering, kiosk sessions, provisioning, and physical device execution. The ESP32 provides room-level awareness. The Flutter app and Next.js dashboard turn that system into a polished user experience.

The result is a complete smart-energy prototype with a serious architecture: cloud intelligence, local resilience, secure kiosk access, real hardware integration, and a presentation-ready product surface.
