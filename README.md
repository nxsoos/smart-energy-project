# Smart Energy Project

Monorepo for the Smart Energy senior project. The repository is split into a
Flutter client, a Python AI backend, and Firebase Cloud Functions.

## Structure

```text
smart-energy-project/
  smart_energy_app/          Flutter application
  seniorproject-backend/     FastAPI AI service and Firebase Functions
    devices/                 AI training, prediction, and device scripts
    functions/               Firebase Cloud Functions TypeScript project
```

## Run The Flutter App

```powershell
cd smart_energy_app
flutter pub get
flutter run
```

Runtime values used by the Flutter app live in:

```text
smart_energy_app/lib/config/app_config.dart
```

## Run The AI Backend Locally

```powershell
cd seniorproject-backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:FIREBASE_DATABASE_URL="https://YOUR_DATABASE.firebaseio.com"
uvicorn main:app --reload
```

Cloud Run deployment notes are in:

```text
seniorproject-backend/README_DEPLOY.md
```

## Firebase Functions

```powershell
cd seniorproject-backend/functions
npm install
npm run build
npm run serve
```

## Repository Notes

- Keep Firebase service account keys, local `.env` files, build outputs, and
  generated model data out of git.
- The trained model currently lives at
  `seniorproject-backend/devices/models/smart_energy_ai.joblib` because the
  Cloud Run Dockerfile copies it into the image.
- `seniorproject-backend` still contains its own `.git` folder from the original
  backend repository. Remove that nested `.git` only after you are sure the
  outer repository is the one you want to use going forward.
