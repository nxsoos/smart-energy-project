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

flutter run \
  --dart-define=KAHRABAIQ_API_URL=http://52.210.115.88 \
  --dart-define=BACKEND_API_URL=http://52.210.115.88 \
  --dart-define=USE_LOCAL_PI_API=false \
  --dart-define=DEFAULT_HOME_ID=home_001 \
  --dart-define=PI_ID=pi_home_001 \
  --dart-define=AWS_REGION=eu-west-1 \
  --dart-define=COGNITO_USER_POOL_ID=eu-west-1_cMTzJaFq4 \
  --dart-define=COGNITO_APP_CLIENT_ID=3gjdm86ikat2abft8rmit7tetf \
  --dart-define=COGNITO_IDENTITY_POOL_ID=eu-west-1:2ade4147-684c-46d6-968e-67e65a8c3b65 \
  --dart-define=AWS_IOT_ENDPOINT=a2olbiowu565t4-ats.iot.eu-west-1.amazonaws.com \
  --dart-define=AWS_IOT_POLICY_NAME=SmartEnergyFlutterLiveSubscribePolicy \
  --dart-define=AWS_IOT_LIVE_TOPIC=homes/home_001/live/state

## Test

```bash
flutter test
```
