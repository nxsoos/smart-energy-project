# KahrabaIQ AI and Machine-Learning Pipeline

KahrabaIQ uses a hybrid AI design:

1. Weakly supervised ML models trained from hourly smart-home summaries.
2. Statistical anomaly detection using recent rolling and same-hour history.
3. Safety and freshness guardrails for smoke/gas, stale sensors, stale breakers, and offline hub cases.
4. Scenario simulation support for demos.
5. Chatbot explanations that can describe the AI result, but are separate from the trained ML model.

## Data Source

The preferred real data source is DynamoDB hourly summaries for a home, normally `home_001`.
However, the current prototype has limited collected real data. To avoid training and evaluating on only a tiny number of rows, the dataset builder combines:

1. real DynamoDB hourly summaries
2. synthetic scenario-generated hourly summaries
3. optional manual test rows from CSV

Hourly rows include room sensor summaries, occupancy summaries, breaker energy/power summaries, time features, and command/system context when available.
Raw ESP32 readings are not used directly as training rows. They are summarized first so the ML model learns from stable hourly windows rather than noisy every-second data.

Each row includes:

```text
data_origin: real_dynamodb, synthetic_scenario, or manual_test
scenario_family: normal_usage, ac_left_on, socket_left_on, routine_anomaly,
                 high_energy, smoke_gas, stale_data, hub_offline,
                 low_usage_normal, power_spike, real_home, or manual_test
scenario_variant_id: group identifier used to prevent scenario leakage
```

## Synthetic Scenario Data

Synthetic scenario rows are generated as hourly summaries, not raw sensor readings. They randomize realistic prototype ranges for:

- temperature and humidity
- motion, brightness, sound, noise, smoke/gas, and high-temperature counts
- AC power, socket power, peak power, energy kWh, and cost BHD
- time of day, day of week, weekend flag, and day part
- occupancy score
- sensor, breaker, and hub freshness ages
- command and command-failure counts
- prior/routine statistics used for anomaly features

The generator creates many variations of scenario families instead of relying on only a few fixed demo scenarios. The default build creates at least 1,000 synthetic rows.

Because real collected data is limited, the current model is trained using real prototype data plus synthetic scenario data. Metrics on synthetic data show behavior coverage, not guaranteed real-world accuracy.

## Dataset Files

`devices/build_ai_dataset.py` writes:

```text
devices/datasets/ai_dataset_full.csv
devices/datasets/ai_dataset_train.csv
devices/datasets/ai_dataset_validation.csv
devices/datasets/ai_dataset_test.csv
devices/datasets/ai_dataset_metadata.json
devices/ai_ready_dataset_60_days.csv
```

The split is grouped by `scenario_variant_id`: about 70% train, 15% validation, and 15% test. This keeps similar scenario variants from leaking into both training and testing. Real DynamoDB rows are kept in the dataset, but synthetic scenario coverage prevents tiny real data from dominating training behavior or headline metrics.

## Features

The pipeline keeps the original sensor, occupancy, breaker, time, energy, cost, and tariff features and adds richer context:

- previous-hour energy and power
- rolling 3h, 6h, and 24h energy/power averages
- rolling standard deviations
- same-hour 7-day averages and deviations
- energy and power z-scores
- occupancy/power mismatch score
- motion, brightness, noise, smoke, and high-temperature rates
- stale sensor/breaker/hub flags
- AC/socket on flags and state-duration estimates
- high-power and empty-room duration estimates
- command count and command-failure count
- day-part and routine-deviation features

Missing fields are filled safely during training. Old summaries can still be used.

## Labels

KahrabaIQ currently uses weakly supervised labels generated from transparent domain rules. This is suitable for a prototype and allows the system to train on collected smart-home data, but future work should include manually labeled events from real users to improve accuracy and reduce bias.

Current label categories include normal use, low usage, empty-room power waste, AC running empty-room, socket left-on, unusual same-hour usage, sudden power spike, stale sensor/breaker/hub cases, smoke/gas safety, high-temperature comfort, noisy possible occupancy, and routine change.

Optional manual overrides can be added in:

```text
devices/datasets/manual_labels.csv
```

Expected columns:

```text
record_id or timestamp_ms, waste_event, anomaly_label, recommendation_type
```

## Targets

The trained model predicts:

```text
waste_event
anomaly_label
recommendation_type
next_hour_total_energy_kWh
next_hour_total_cost_BHD
```

## Training and Evaluation

`devices/train_ai_model.py` compares Random Forest, Extra Trees, Gradient Boosting, and Histogram Gradient Boosting when enough data exists. If the dataset is too small or a target has only one class, it falls back to a dummy baseline and records a warning.

Classification targets are selected by validation macro F1. Regression targets are selected by validation MAE.

Training/evaluation writes:

```text
devices/models/smart_energy_ai.joblib
devices/models/smart_energy_ai_metrics.json
devices/models/smart_energy_ai_feature_importance.csv
devices/models/smart_energy_ai_confusion_matrices.json
devices/models/smart_energy_ai_evaluation_report.md
```

## Runtime Modes

Runtime responses expose:

- `ai_mode`: `full_ml`, `hybrid_ml_rules`, `rule_only`, or `insufficient_data`
- `model_version`
- `data_source`: hourly summary, live dashboard fallback, or scenario simulation
- `confidence`
- `data_freshness`
- `anomaly_scores`
- `top_factors`
- `guardrails_applied`

Full ML runs hourly after summaries or on demand. Lightweight safety/routine checks can run more often.

Runtime model-info endpoints expose whether the model was trained from real plus synthetic rows, data-origin counts, scenario-family counts, and limitations. The backend should not claim production-grade accuracy.

## Commands

```bash
cd KahrabaIQ-backend
pip install -r devices/requirements-ai.txt
python devices/build_ai_dataset.py
python devices/train_ai_model.py
python devices/evaluate_ai_model.py
python devices/test_ai_pipeline.py
python devices/test_ai_guardrails.py
```

On Windows, use `py -3` in place of `python`.

Useful dataset options:

```bash
python devices/build_ai_dataset.py --synthetic-rows 1500
python devices/build_ai_dataset.py --no-synthetic
python devices/build_ai_dataset.py --fallback-csv devices/datasets/manual_test_rows.csv
```

## API

Model and metric summaries are available through:

```text
GET /api/homes/{home_id}/ai/model-info
GET /api/homes/{home_id}/ai/metrics-summary
```

These endpoints return summarized model metadata and metrics only. They do not expose training rows or private raw data.

## Future Work

- collect more real homes and longer real hourly history
- manually label real waste/anomaly events
- compare real-only, synthetic-only, and mixed models
- calibrate confidence using more real validation data
- add device-specific models when enough device history exists
