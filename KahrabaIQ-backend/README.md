# KahrabaIQ Backend Workspace

Python workspace for the AWS cloud API and lightweight AI inference.

## Layout

```text
seniorproject-backend/
  api_server.py                 EC2 API for Flutter, Pi sync, and AI inference
  main.py                       Reusable AI model, feature, guardrail, and chat logic
  aws_cloud_store.py            DynamoDB helpers
  home_assistant_controller.py  Shared Home Assistant integration
  occupancy_utils.py            Occupancy calculations
  timestamp_utils.py            Time helpers
  devices/                      AI model artifacts and validation scripts
  docs/                         Deployment and AI reports
```

## Cloud API Local Run

```bash
pip install -r requirements.txt
uvicorn api_server:app --reload
```

## AI Architecture

AI inference now runs inside the EC2 FastAPI backend. Legacy managed backend services are not required.

Data sources:

- Raspberry Pi and ESP32 state synced into DynamoDB.
- Latest dashboard energy/environment state.
- Recent hourly summaries from DynamoDB.
- Device state, occupancy, safety, and command history.

Main feature groups:

- Temperature, humidity, light, motion, noise, smoke/gas.
- Breaker power, voltage, current, total energy, and estimated cost.
- AC/socket state, control mode, hour of day, day of week, weekend flag.
- Recent usage averages, previous-hour energy, rolling power/energy statistics, command frequency, and occupancy score.

Prediction targets:

- `waste_event`
- `anomaly_label`
- `recommendation_type`
- `next_hour_total_energy_kWh`
- `next_hour_total_cost_BHD`

Detection method:

- `smart_energy_ai.joblib` provides lightweight scikit-learn predictions.
- Level 1 immediate rule alerts handle safety-critical and obvious device/system cases without waiting for ML: smoke/gas, stale sensor data, stale breaker data, repeated command failures, and high power while empty.
- Level 2 lightweight routine/anomaly checks run periodically and compare current/latest state with recent hourly history using rolling average/stddev, same-hour comparison, weekday/weekend routine scores, and threshold guardrails.
- Level 3 full ML prediction runs manually or hourly after hourly summaries are available. It predicts `waste_event`, `anomaly_label`, `recommendation_type`, `next_hour_total_energy_kWh`, and `next_hour_total_cost_BHD`.
- Raw ESP32 readings stay local on the Pi for the fast dashboard. EC2 AI uses hourly summaries, recent history features, command history, and compact latest-state context. Live data is only used for urgent safety checks, current context, and fallback.
- Daily summaries are for reports, trends, and long-term recommendations, not per-reading inference.
- AI should not run for every raw sensor message or every live IoT update.

Scheduling:

- `AI_ROUTINE_CHECK_INTERVAL_SECONDS`: lightweight Level 1/2 checks. Use `300` for demo or `600` for normal operation.
- `AI_FULL_PREDICTION_INTERVAL_SECONDS`: full ML cadence. Default is hourly (`3600`).
- `AI_PREDICTION_INTERVAL_SECONDS` remains as a compatibility alias for older deployments.
- Daily report generation should run once per day from daily summaries.

Normalized notification fields:

```text
id, home_id, severity, category, title, message, device_id,
target_type, recommendation_type, created_at, acknowledged,
source, confidence, explanation
```

Canonical AI storage uses the `KahrabaIQApp` DynamoDB table:

```text
PK = HOME#<home_id>, SK = AI#LATEST
PK = HOME#<home_id>, SK = AI#PREDICTION#<timestamp>
PK = HOME#<home_id>, SK = AI#ALERT#<timestamp>#<alert_id>
PK = HOME#<home_id>, SK = AI#SUGGESTION#<timestamp>#<suggestion_id>
```

AI API endpoints:

```text
POST /api/homes/{home_id}/ai/predict
POST /api/homes/{home_id}/ai/scenario-predict
GET  /api/homes/{home_id}/ai/latest
GET  /api/homes/{home_id}/ai/history
GET  /api/homes/{home_id}/ai/notifications
GET  /api/homes/{home_id}/ai/model-info
GET  /api/homes/{home_id}/ai/metrics-summary
```

The older singular `POST /api/home/{home_id}/ai/predict` remains as a compatibility alias.

`POST /api/homes/{home_id}/ai/scenario-predict` is a pure simulation endpoint. It accepts simulated room, energy, device, occupancy, and recent-history data from the Flutter Demo Scenario Mode, runs the same EC2 AI rules/model against that input, and returns normalized AI output marked with `simulation: true` and `source: scenario_ai`. It does not update real live state, queue commands, control devices, or write to `AI#LATEST`.

Dashboard AI freshness:

- Live dashboard AI only presents smoke/gas warnings when the current room/safety state is actively reporting smoke or gas.
- If `AI#LATEST` is stale or the room sensor data is stale, the dashboard returns a waiting/stale AI state instead of replaying old critical text.
- Historical smoke/gas notifications remain available through notification/history endpoints, but they are not treated as current AI card state after the condition clears.
- Dashboard logs include AI age, smoke status, sensor age, active alert count, active suggestion count, and monthly source to simplify EC2 debugging.

Monthly usage source order:

- Current-month daily DynamoDB summaries.
- Current-month hourly DynamoDB summaries when daily summaries are missing.
- Today fallback only when cloud monthly summaries are unavailable but current dashboard energy is non-zero.
- If no source exists, `month_data_available=false` and the Flutter dashboard should show an empty monthly state rather than a misleading zero.

Chatbot endpoints:

```text
GET    /api/home/{home_id}/chat/sessions
POST   /api/home/{home_id}/chat/sessions
GET    /api/home/{home_id}/chat/sessions/{session_id}/messages
POST   /api/home/{home_id}/chat/sessions/{session_id}/message
PATCH  /api/home/{home_id}/chat/sessions/{session_id}
DELETE /api/home/{home_id}/chat/sessions/{session_id}
```

Chat sessions and messages are stored in DynamoDB through the app path store under `/homes/{home_id}/chat/sessions`. Chat uses Cognito/home permissions (`can_use_ai_chat`) and Gemini through `GEMINI_API_KEY`; if Gemini is not configured, the endpoint keeps the session/history working and returns a clear Gemini-unavailable assistant message.

## AI Model Scripts

```bash
pip install -r requirements.txt
python devices/build_ai_dataset.py
python devices/train_ai_model.py
python devices/evaluate_ai_model.py
python devices/test_ai_pipeline.py
python devices/predict_ai.py
python devices/test_ai_guardrails.py
```

The current ML pipeline combines real DynamoDB hourly summaries with synthetic scenario
hourly summaries because the collected prototype data is still limited. It writes a grouped
train/validation/test split under `devices/datasets/`, compares multiple scikit-learn model
families when enough data is available, saves metrics/confusion matrices/feature
importances under `devices/models/`, and exposes runtime metadata such as `ai_mode`,
confidence, data freshness, anomaly scores, top factors, and guardrails.

KahrabaIQ currently uses weakly supervised labels generated from transparent domain rules.
This is suitable for a prototype and allows the system to train on collected smart-home
data, but future work should include manually labeled events from real users to improve
accuracy and reduce bias.

Because real collected data is limited, the current model is trained using real prototype
data plus synthetic scenario data. Metrics on synthetic data show behavior coverage, not
guaranteed real-world accuracy.

More detail: [docs/ai/ai-ml-pipeline.md](docs/ai/ai-ml-pipeline.md).

Home settings are per-home and affect cost calculation, budget notifications, AI
behavior, occupancy thresholds, stale/offline thresholds, automation, schedules, and
quiet hours. More detail: [docs/home-settings.md](docs/home-settings.md).

Scenario AI endpoint verification:

```bash
python -m py_compile api_server.py main.py devices/test_ai_guardrails.py
python devices/test_ai_guardrails.py
curl -X POST http://localhost:8000/api/homes/home_001/ai/scenario-predict \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <COGNITO_ID_TOKEN>" \
  -d '{"scenario_id":"smoke_demo","scenario_name":"Smoke Demo","room":{"temperature":29,"humidity":55,"motion":true,"smokeStatus":"Smoke/Gas"},"energy":{"power":420,"energyToday":0.4,"costToday":0.012},"devices":{"breaker_01":{"isOn":true,"power":180},"breaker_02":{"isOn":false,"power":0}},"occupancy":{"occupied":true,"state":"occupied"},"recent_history":{"sensor_staleness_seconds":0,"breaker_staleness_seconds":0}}'
```

If the real dataset is missing, build hourly/time-windowed rows from DynamoDB summaries:

```bash
python devices/build_ai_dataset.py
```

The dataset builder uses hourly summaries, not raw every-second sensor data. When real labels are unavailable, demo labels are assigned with explainable rules for safety, empty-room waste, AC waste, normal usage, and next-hour shifted energy/cost targets.

App/dashboard integration:

- Flutter calls `/api/homes/{home_id}/ai/latest`, `/ai/history`, `/ai/notifications`, and `/ai/predict`.
- Flutter parses normalized AI notifications for safety alerts, anomaly alerts, recommendations, predicted energy/cost, and daily summaries.
- The Pi dashboard keeps fast live data local and can show EC2 AI status/notifications when cloud dashboard data is available.

## Secrets

Do not commit API keys, `.env` files, Pi device tokens, kiosk secrets, or passwords. Use environment variables or a secret manager.
