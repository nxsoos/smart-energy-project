# KahrabaIQ App

Flutter client for the KahrabaIQ product. It reads dashboard, sensor, device, alert, and AI insight data from the AWS backend and calls the KahrabaIQ API for chatbot responses.

## Project Layout

```text
lib/
  core/        Runtime configuration and shared utilities
  features/    Main app features and screens
  shared/      Shared models and KahrabaIQ API services
```

## Run

```bash
flutter pub get
flutter emulators --launch Pixel_10_Pro
flutter run
```
cd /c/Nasser/Univirsity/smart-energy-project/smart_energy_app

flutter run `
  --dart-define="KAHRABAIQ_API_URL=http://52.210.115.88" `
  --dart-define="BACKEND_API_URL=http://52.210.115.88" `
  --dart-define="USE_LOCAL_PI_API=false" `
  --dart-define="REMOTE_LIVE_ONLY=true" `
  --dart-define="DEFAULT_HOME_ID=home_001" `
  --dart-define="PI_ID=pi_home_001" `
  --dart-define="AWS_REGION=eu-west-1" `
  --dart-define="COGNITO_USER_POOL_ID=eu-west-1_cMTzJaFq4" `
  --dart-define="COGNITO_APP_CLIENT_ID=3gjdm86ikat2abft8rmit7tetf" `
  --dart-define="COGNITO_IDENTITY_POOL_ID=eu-west-1:2ade4147-684c-46d6-968e-67e65a8c3b65" `
  --dart-define="AWS_IOT_ENDPOINT=a2olbiowu565t4-ats.iot.eu-west-1.amazonaws.com" `
  --dart-define="AWS_IOT_POLICY_NAME=SmartEnergyFlutterLiveSubscribePolicy" `
  --dart-define="AWS_IOT_LIVE_TOPIC=homes/home_001/live/state" `
  --dart-define="ENABLE_DEMO_SCENARIOS=true" `
  --dart-define="USE_BACKEND_SCENARIO_AI=true"
## in bash
flutter run \
  --dart-define=KAHRABAIQ_API_URL=http://52.210.115.88 \
  --dart-define=BACKEND_API_URL=http://52.210.115.88 \
  --dart-define=USE_LOCAL_PI_API=false \
  --dart-define=REMOTE_LIVE_ONLY=true \
  --dart-define=DEFAULT_HOME_ID=home_001 \
  --dart-define=PI_ID=pi_home_001 \
  --dart-define=AWS_REGION=eu-west-1 \
  --dart-define=COGNITO_USER_POOL_ID=eu-west-1_cMTzJaFq4 \
  --dart-define=COGNITO_APP_CLIENT_ID=3gjdm86ikat2abft8rmit7tetf \
  --dart-define=COGNITO_IDENTITY_POOL_ID=eu-west-1:2ade4147-684c-46d6-968e-67e65a8c3b65 \
  --dart-define=AWS_IOT_ENDPOINT=a2olbiowu565t4-ats.iot.eu-west-1.amazonaws.com \
  --dart-define=AWS_IOT_POLICY_NAME=SmartEnergyFlutterLiveSubscribePolicy \
  --dart-define=AWS_IOT_LIVE_TOPIC=homes/home_001/live/state \
  --dart-define=ENABLE_DEMO_SCENARIOS=true
## Test

```bash
flutter test
```

## Demo Scenario Mode

Demo Scenario Mode lets the final presentation show KahrabaIQ AI behavior without depending on real-time physical room conditions. It is local Flutter simulation data and does not write to DynamoDB, queue device commands, or control the Pi, ESP32, Tuya, Matter, or Home Assistant devices.

Enable it with:

```bash
flutter run --dart-define=ENABLE_DEMO_SCENARIOS=true
```

To make demo scenarios call the EC2 AI engine instead of using only local fallback AI output, run:

```bash
flutter run \
  --dart-define=ENABLE_DEMO_SCENARIOS=true \
  --dart-define=USE_BACKEND_SCENARIO_AI=true
```

When enabled, the dashboard shows a Demo Scenarios card with these simulations:

- Normal Usage
- AC Left On Without Occupancy
- Socket/Device Left On
- Unusual AC Routine
- High Energy Consumption
- Smoke/Gas Safety Alert
- Stale Breaker/Sensor Data

Each scenario clearly shows Simulation Mode, replaces live dashboard cards with simulated sensor/device/energy values, and fills the AI card with prediction status, explanation, alerts, notifications, suggestions, next-hour energy, cost, and confidence. Use Return to Live Data to resume the real dashboard.

With `USE_BACKEND_SCENARIO_AI=true`, the app posts simulated scenario data to:

```text
POST /api/homes/{home_id}/ai/scenario-predict
```

The backend runs the EC2 AI rules/model on the simulated input and returns normalized AI output marked with `simulation: true` and `source: scenario_ai`. If the backend request fails, the app keeps the local demo fallback and shows a fallback note. Demo mode always keeps device control disabled.

Keep the flag off for normal use:

```bash
flutter run --dart-define=ENABLE_DEMO_SCENARIOS=false
```

Test checklist:

```bash
flutter analyze
flutter run --dart-define=ENABLE_DEMO_SCENARIOS=true --dart-define=USE_BACKEND_SCENARIO_AI=true
```

Then select all seven scenarios, verify the AI card says the result was generated from simulated scenario data, verify Return to Live Data reloads the real dashboard, and verify device toggles show that control is disabled in Demo Mode.
