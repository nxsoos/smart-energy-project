# KahrabaIQ

Monorepo for the KahrabaIQ product: Flutter mobile app, cloud backend, AI service, Firebase functions, and Raspberry Pi edge dashboard/services.

## Repository Layout

```text
smart-energy-project/
  smart_energy_app/              Flutter mobile app
    lib/
      core/                      Shared UI, config, utilities
      features/                  Feature-first screens and flows
      shared/                    Shared models and API services

  seniorproject-backend/         Python backend workspace
    api_server.py                Cloud API for app, homes, users, pairing, devices
    main.py                      AI service entry point
    docs/                        Deployment and AI documentation
    devices/                     Raspberry Pi dashboard, services, firmware, local docs
    functions/                   Firebase Cloud Functions project
```

## Flutter App

```bash
cd smart_energy_app
flutter pub get
flutter run
```

Runtime config lives in:

```text
smart_energy_app/lib/core/config/app_config.dart
```

## Cloud API

```bash
cd seniorproject-backend
pip install -r requirements.txt
uvicorn api_server:app --reload
```

Required environment values depend on the feature being used:

```text
FIREBASE_DATABASE_URL
PLATFORM_ADMIN_EMAILS
AI_SERVICE_URL
INTERNAL_SERVICE_TOKEN
PI_DASHBOARD_TOKEN
```

Deployment docs:

```text
seniorproject-backend/docs/deployment/
```

## AI Service

```bash
cd seniorproject-backend
pip install -r requirements.txt
uvicorn main:app --reload
```

Set secrets and API keys through environment variables or your cloud secret manager. Do not commit keys.

## Raspberry Pi Dashboard

Pi dashboard files live in:

```text
seniorproject-backend/devices/
  dashboard_server.py
  static/
  templates/
  docs/
```

Local kiosk URL:

```text
http://localhost:5001
```

Pi docs:

```text
seniorproject-backend/devices/docs/
```

## Firebase Functions

```bash
cd seniorproject-backend/functions
npm install
npm run build
npm run serve
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

- Do not commit Firebase service account keys, local `.env` files, API keys, generated datasets, or trained model artifacts unless explicitly intended.
- `.agents/` and local agent lock files are development tooling and are ignored.
