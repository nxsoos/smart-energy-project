# Smart Energy API Cloud Run Deployment

This deploys `api_server.py` as the public API layer for Flutter and the
Raspberry Pi dashboard.

It is separate from the existing `smart-energy-ai` Cloud Run service. The AI
service runs predictions and chatbot responses; this API service reads Firebase,
formats dashboard data, validates device commands, and writes command requests.

## Local Test

```powershell
cd C:\Nasser\Univirsity\smart-energy-project\seniorproject-backend
$env:FIREBASE_DATABASE_URL="https://seniorproject-energy-default-rtdb.asia-southeast1.firebasedatabase.app"
$env:SERVICE_ACCOUNT_PATH="devices/serviceAccountKey.json"
py -m uvicorn api_server:app --host 0.0.0.0 --port 8000 --reload
```

Open:

```text
http://localhost:8000/api/health
http://localhost:8000/api/home/home_001/dashboard
```

## Deploy To Cloud Run

Cloud Run should use Application Default Credentials through its service
account. Do not upload `serviceAccountKey.json`.

Set your Google Cloud project:

```bash
gcloud config set project YOUR_PROJECT_ID
```

Build the API image with the dedicated API Dockerfile:

```bash
gcloud builds submit \
  --tag gcr.io/YOUR_PROJECT_ID/smart-energy-api \
  --file Dockerfile.api
```

Deploy it:

```bash
gcloud run deploy smart-energy-api \
  --image gcr.io/YOUR_PROJECT_ID/smart-energy-api \
  --region asia-southeast1 \
  --set-env-vars FIREBASE_DATABASE_URL="https://seniorproject-energy-default-rtdb.asia-southeast1.firebasedatabase.app",AI_SERVICE_URL="https://smart-energy-ai-237804589333.asia-southeast1.run.app" \
  --allow-unauthenticated
```

For production, replace `--allow-unauthenticated` with a secure auth strategy.
For the senior-project demo, unauthenticated access is simpler but anyone with
the URL can call the API.

## Cloud Run Permissions

Find the service account:

```bash
gcloud run services describe smart-energy-api \
  --region asia-southeast1 \
  --format="value(spec.template.spec.serviceAccountName)"
```

Grant Firebase access to that service account:

```bash
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:SERVICE_ACCOUNT_EMAIL" \
  --role="roles/firebase.admin"
```

For a production system, use narrower permissions and authenticated API access.

## Test Deployed API

After deployment, Cloud Run prints a service URL. Test:

```bash
curl https://YOUR_SMART_ENERGY_API_URL/api/health
curl https://YOUR_SMART_ENERGY_API_URL/api/home/home_001/dashboard
```

Test command creation only when it is safe to operate the breaker:

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"command":"turn_off","requested_by":"flutter_app"}' \
  https://YOUR_SMART_ENERGY_API_URL/api/home/home_001/devices/breaker_01/command
```

The command is written to Firebase. The Raspberry Pi Tuya controller must still
be running at home to physically process breaker commands.

## Point Flutter To Cloud Run

For emulator/local API testing, the default remains:

```text
http://10.0.2.2:8000
```

For Cloud Run, run Flutter with:

```bash
flutter run -d emulator-5554 \
  --dart-define=BACKEND_API_URL=https://YOUR_SMART_ENERGY_API_URL
```

For a release build:

```bash
flutter build apk \
  --dart-define=BACKEND_API_URL=https://YOUR_SMART_ENERGY_API_URL
```

Once this is set, the Flutter app can load dashboard data from anywhere with
internet access.
