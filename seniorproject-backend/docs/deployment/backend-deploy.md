# KahrabaIQ Intelligence Cloud Run Deployment

This service deploys the trained Python AI model to Google Cloud Run using FastAPI.
It does not retrain the model. It only loads `devices/models/smart_energy_ai.joblib`,
reads live Firebase Realtime Database data, runs prediction, and writes the result to:

```text
/homes/home_001/backend/ai/latest_prediction
```

## Endpoints

```text
GET  /health
POST /predict
POST /predict/{home_id}
POST /chat/{home_id}
```

`POST /predict` uses `DEFAULT_HOME_ID`, which defaults to `home_001`.

## Required APIs

Set your project first:

```bash
gcloud config set project YOUR_PROJECT_ID
```

Enable the required APIs:

```bash
gcloud services enable run.googleapis.com
gcloud services enable cloudbuild.googleapis.com
gcloud services enable artifactregistry.googleapis.com
gcloud services enable firebase.googleapis.com
```

## Firebase Database URL

Use your Firebase Realtime Database URL. For example:

```text
https://YOUR_PROJECT_ID-default-rtdb.firebaseio.com
```

Your project currently uses a regional database URL, so use that exact URL if needed:

```text
https://seniorproject-energy-default-rtdb.asia-southeast1.firebasedatabase.app
```

## Deploy To Cloud Run

Run this from the repository root, where `main.py`, `Dockerfile`, and `requirements.txt` exist:

On this project, that folder is:

```powershell
cd C:\Nasser\Univirsity\smart-energy-project\seniorproject-backend
```

Do not run Cloud Run deploy from the Flutter app folder or from the parent
`smart-energy-project` folder. Otherwise `gcloud` can scan Flutter/Gradle cache
files and fail before deployment starts.

```bash
gcloud run deploy smart-energy-ai \
  --source . \
  --region me-central2 \
  --set-env-vars FIREBASE_DATABASE_URL="https://YOUR_PROJECT_ID-default-rtdb.firebaseio.com",DEFAULT_HOME_ID="home_001",GEMINI_API_KEY="YOUR_GEMINI_API_KEY" \
  --allow-unauthenticated
```

For your existing Firebase database, the command may look like:

```bash
gcloud run deploy smart-energy-ai \
  --source . \
  --region me-central2 \
  --set-env-vars FIREBASE_DATABASE_URL="https://seniorproject-energy-default-rtdb.asia-southeast1.firebasedatabase.app",DEFAULT_HOME_ID="home_001",GEMINI_API_KEY="YOUR_GEMINI_API_KEY" \
  --allow-unauthenticated
```

`--allow-unauthenticated` is acceptable for demo testing. For a real system, secure
the API with IAM authentication, Firebase Auth, an API gateway, or another access
control layer.

Never put `GEMINI_API_KEY` in Flutter, GitHub, or committed files. It belongs only
in Cloud Run environment variables or a secret manager.

If the service is already deployed, set or update only the Gemini key with:

```bash
gcloud run services update smart-energy-ai \
  --region asia-southeast1 \
  --update-env-vars GEMINI_API_KEY="YOUR_GEMINI_API_KEY"
```

Then deploy code changes with:

```bash
gcloud run deploy smart-energy-ai \
  --source . \
  --region asia-southeast1 \
  --set-env-vars FIREBASE_DATABASE_URL="https://seniorproject-energy-default-rtdb.asia-southeast1.firebasedatabase.app",DEFAULT_HOME_ID="home_001",GEMINI_API_KEY="YOUR_GEMINI_API_KEY" \
  --allow-unauthenticated
```

## Cloud Run Service Account Permissions

This service does not use `serviceAccountKey.json`.
Firebase Admin SDK uses Application Default Credentials from the Cloud Run service account.

Find the Cloud Run service account:

```bash
gcloud run services describe smart-energy-ai \
  --region me-central2 \
  --format="value(spec.template.spec.serviceAccountName)"
```

If you did not set a custom service account, Cloud Run may use the default Compute service account.
For demo testing, grant it Firebase Admin permissions:

```bash
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:SERVICE_ACCOUNT_EMAIL" \
  --role="roles/firebase.admin"
```

For production, use the narrowest permissions possible and secure the endpoint.

Also make sure your Firebase Realtime Database rules and project settings allow
Admin SDK access from this service account.

## Test Health

After deploy, Cloud Run prints a service URL. Test:

```bash
curl https://YOUR_CLOUD_RUN_URL/health
```

Expected response:

```json
{
  "status": "ok",
  "service": "smart-energy-ai"
}
```

## Test Prediction

Run prediction for the default home:

```bash
curl -X POST https://YOUR_CLOUD_RUN_URL/predict
```

Run prediction for a specific home:

```bash
curl -X POST https://YOUR_CLOUD_RUN_URL/predict/home_001
```

The response includes:

```text
home_id
timestamp
energy_waste
abnormal_usage
recommendation_type
next_hour_energy
next_hour_cost
efficiency_score
explanation
firebase_path_written
latest_prediction
```

Then check Firebase:

```text
/homes/home_001/backend/ai/latest_prediction
/homes/home_001/backend/ai/prediction_history
```

## Test Chatbot

The Flutter app should call the Cloud Run backend, not Gemini directly.

Request:

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d "{\"message\":\"Why is energy waste detected?\"}" \
  https://YOUR_CLOUD_RUN_URL/chat/home_test
```

Expected response shape:

```json
{
  "home_id": "home_test",
  "answer": "...",
  "used_data": true,
  "timestamp": 1770000000000
}
```

The endpoint reads:

```text
/homes/{home_id}/backend/ai/latest_prediction
/homes/{home_id}/backend/dashboard/ai
/homes/{home_id}/backend/ai/daily_summary
/homes/{home_id}/backend/recommendations/ai_energy_insight
/homes/{home_id}/backend/active_alerts/ai_abnormal_usage
/homes/{home_id}/backend/ai/prediction_history
```

Only the latest 5 prediction history records are sent to Gemini.

Chat logs are saved under:

```text
/homes/{home_id}/backend/ai/chat_history/{timestamp_key}
```

## Flutter Chatbot Screen

The Flutter chatbot screen lives in the Flutter app:

```text
../smart_energy_app/lib/screens/ai_chatbot_screen.dart
```

The app uses the `dio` package to call this backend. The backend URL is
configured in:

```text
../smart_energy_app/lib/config/app_config.dart
```

This backend repo also includes a reference copy:

```text
FLUTTER_AI_CHATBOT_SCREEN.dart
```

Add a navigation button wherever your dashboard/menu actions live:

```dart
ElevatedButton.icon(
  icon: const Icon(Icons.chat_bubble_outline),
  label: const Text('KahrabaIQ Assistant'),
  onPressed: () {
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => const AiChatbotScreen(homeId: 'home_001'),
      ),
    );
  },
)
```

Import the screen:

```dart
import 'screens/ai_chatbot_screen.dart';
```

For test scenarios, open it with:

```dart
const AiChatbotScreen(homeId: 'home_test')
```

The Flutter app must not store or call the Gemini API key. It should only call:

```text
POST https://smart-energy-ai-237804589333.asia-southeast1.run.app/chat/{home_id}
```

Each prediction also updates AI-owned backend paths:

```text
/homes/home_001/backend/dashboard/ai
/homes/home_001/backend/ai/daily_summary
/homes/home_001/backend/recommendations/ai_energy_insight
/homes/home_001/backend/active_alerts/ai_abnormal_usage
```

The AI uses `source: smart_energy_ai` and `ai_...` keys so it does not overwrite
the rule-based alerts and recommendations created by Firebase Functions. Safety
and device-health rules should still be treated as the source of truth.

## Prediction History Deduplication

The AI still runs every 5 minutes, but it does not write a new
`prediction_history` record every time. Each run always updates:

```text
/homes/home_001/backend/ai/latest_prediction
/homes/home_001/backend/dashboard/ai
/homes/home_001/backend/ai/daily_summary
```

Before creating a new history record, the service compares the new AI output
with the previous `latest_prediction`. It ignores timestamps and counters, then
checks meaningful fields:

```text
energy_waste
abnormal_usage
recommendation_type
efficiency_score
next_hour_energy
next_hour_cost
explanation
```

Numeric tolerances:

```text
efficiency_score: 3 points
next_hour_energy: 0.01 kWh
next_hour_cost: 0.001 BHD
```

If the output is not meaningfully different, the service skips the history
write and updates metadata on `latest_prediction`:

```text
history_written: false
change_reason: "No meaningful change from previous AI output"
same_status_count
checks_since_change
last_checked_at
last_changed_at
```

If the output changes meaningfully, it writes a new history record and sets:

```text
history_written: true
change_reason: describes what changed
same_status_count: 1
checks_since_change: 0
last_changed_at: current timestamp
```

Daily summary still counts every AI check, even when history is skipped:

```text
total_ai_checks_today
history_records_today
waste_predictions_today
abnormal_predictions_today
average_efficiency_score
latest_status_message
```

## AI Scenario Tests

Use `devices/test_ai_scenarios.py` to write controlled test data to a safe test
home:

```text
/homes/home_test
```

It never writes to `/homes/home_001`.

List available scenarios:

```bash
py devices/test_ai_scenarios.py --list
```

Write a scenario only:

```bash
py devices/test_ai_scenarios.py --scenario normal_usage
py devices/test_ai_scenarios.py --scenario empty_room_energy_waste
py devices/test_ai_scenarios.py --scenario abnormal_high_power
```

Write a scenario while preserving previous AI outputs. This is useful for
deduplication tests because normal scenario writes replace `/homes/home_test`:

```bash
py devices/test_ai_scenarios.py --scenario empty_room_energy_waste --call-ai --preserve-ai-state
```

Call the deployed AI service after writing a scenario:

```bash
export AI_SERVICE_URL="https://smart-energy-ai-237804589333.asia-southeast1.run.app"
py devices/test_ai_scenarios.py --scenario empty_room_energy_waste --call-ai
```

If `AI_SERVICE_URL` is not set, the script uses the deployed project default:

```text
https://smart-energy-ai-237804589333.asia-southeast1.run.app
```

On PowerShell:

```powershell
$env:AI_SERVICE_URL="https://smart-energy-ai-237804589333.asia-southeast1.run.app"
py devices\test_ai_scenarios.py --scenario empty_room_energy_waste --call-ai
```

Writing a scenario replaces `/homes/home_test`. If you write a scenario without
`--call-ai`, the test input and expected metadata will exist, but AI output paths
such as `latest_prediction`, `dashboard/ai`, and `daily_summary` may be missing
until you call `/predict/home_test`.

For deduplication tests, use `--preserve-ai-state` on the second run so the
previous `latest_prediction` and `prediction_history` remain available for
comparison.

Clear the test home:

```bash
py devices/test_ai_scenarios.py --clear
py devices/test_ai_scenarios.py --clear --yes
```

Available scenarios:

```text
normal_usage
empty_room_energy_waste
abnormal_high_power
bright_room_lights_on
night_device_left_on
occupied_high_temperature
low_power_empty_room
missing_sensor_data
```

## Optional: Schedule It Later

After the API is deployed, you can use Cloud Scheduler to call `POST /predict`
every few minutes. If the Cloud Run service is unauthenticated for demo testing,
the scheduler can call the URL directly. For production, use authenticated calls.

Enable Cloud Scheduler:

```bash
gcloud services enable cloudscheduler.googleapis.com
```

Create a job that calls the AI every 5 minutes:

```bash
gcloud scheduler jobs create http smart-energy-ai-every-5-min \
  --location asia-southeast1 \
  --schedule "*/5 * * * *" \
  --time-zone "Asia/Bahrain" \
  --uri "https://YOUR_CLOUD_RUN_URL/predict" \
  --http-method POST \
  --headers "Content-Type=application/json" \
  --message-body "{}"
```

For the deployed service in this project:

```bash
gcloud scheduler jobs create http smart-energy-ai-every-5-min \
  --location asia-southeast1 \
  --schedule "*/5 * * * *" \
  --time-zone "Asia/Bahrain" \
  --uri "https://smart-energy-ai-237804589333.asia-southeast1.run.app/predict" \
  --http-method POST \
  --headers "Content-Type=application/json" \
  --message-body "{}"
```

Run the scheduler manually for testing:

```bash
gcloud scheduler jobs run smart-energy-ai-every-5-min \
  --location asia-southeast1
```

Check the job:

```bash
gcloud scheduler jobs describe smart-energy-ai-every-5-min \
  --location asia-southeast1
```

If the job already exists and you need to change the URL or schedule, use:

```bash
gcloud scheduler jobs update http smart-energy-ai-every-5-min \
  --location asia-southeast1 \
  --schedule "*/5 * * * *" \
  --uri "https://YOUR_CLOUD_RUN_URL/predict" \
  --http-method POST \
  --headers "Content-Type=application/json" \
  --message-body "{}"
```
