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

AI inference now runs inside the EC2 FastAPI backend. Firebase, Cloud Run, and SageMaker are not required.

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
- Rule-based guardrails handle safety-critical and obvious waste cases.
- EC2 adds statistical checks using recent summaries, including rolling average/stddev and same-hour usage comparison.
- AI runs on demand, hourly from summaries, or immediately for critical/major events. It should not run for every raw sensor message.

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
GET  /api/homes/{home_id}/ai/latest
GET  /api/homes/{home_id}/ai/history
GET  /api/homes/{home_id}/ai/notifications
```

The older singular `POST /api/home/{home_id}/ai/predict` remains as a compatibility alias.

## AI Model Scripts

```bash
pip install -r requirements.txt
python devices/train_ai_model.py
python devices/predict_ai.py
python devices/test_ai_guardrails.py
```

If the real dataset is missing, build hourly/time-windowed rows from DynamoDB summaries and label demo data with documented rules for `waste_event`, `anomaly_label`, and `recommendation_type`.

## Secrets

Do not commit API keys, `.env` files, Pi device tokens, kiosk secrets, or passwords. Use environment variables or a secret manager.
