# KahrabaIQ

Monorepo for the KahrabaIQ product: Flutter mobile app, AWS cloud backend, AI service, Raspberry Pi edge runtime, and ESP32 firmware.

## Repository Layout

```text
smart-energy-project/
  smart_energy_app/              Flutter mobile app
  seniorproject-backend/         Python AWS backend and AI service
  pi/                            Raspberry Pi runtime, systemd units, and docs
  esp32/                         ESP32 firmware and docs
```

## Flutter App

```bash
cd smart_energy_app
flutter pub get
flutter run
```

## Cloud API

```bash
cd seniorproject-backend
pip install -r requirements.txt
uvicorn api_server:app --reload
```

Key environment values:

```text
STORAGE_BACKEND=aws
AWS_DYNAMODB_APP_TABLE=KahrabaIQApp
AWS_DYNAMODB_SUMMARIES_TABLE=SmartEnergySummaries
PLATFORM_ADMIN_EMAILS=admin@example.com
AI_SERVICE_URL=https://YOUR_AI_SERVICE_URL
INTERNAL_SERVICE_TOKEN=change_me
KIOSK_SESSION_SECRET=change_me_to_a_long_random_secret
```

## Raspberry Pi Runtime

The Pi opens the deployed AWS-hosted kiosk dashboard in Chromium. The local agent keeps `PI_DEVICE_TOKEN` out of the browser and issues short-lived kiosk sessions.

```text
pi/agent/
pi/scripts/
pi/systemd/
pi/docs/
```

## Verification

Flutter:

```bash
cd smart_energy_app
flutter analyze
flutter test
```

Backend syntax:

```bash
cd seniorproject-backend
python3 -m py_compile api_server.py main.py devices/dashboard_server.py
```

## Security Notes

- Do not commit local `.env` files, API keys, Pi device tokens, kiosk secrets, generated datasets, or trained model artifacts unless explicitly intended.
- `.agents/` and local agent lock files are development tooling and are ignored.
