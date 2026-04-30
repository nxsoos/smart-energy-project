# Smart Energy App

Flutter client for the Smart Energy project. It reads dashboard, sensor, device,
alert, and AI insight data from Firebase Realtime Database and calls the Cloud
Run AI backend for chatbot responses.

## Project Layout

```text
lib/
  config/      Runtime URLs and home ids
  models/      Data models parsed from Firebase/backend responses
  screens/     Main dashboard and AI screens
  services/    Firebase Realtime Database access
  utils/       Shared constants and helpers
  widgets/     Reusable UI widgets
```

## Configuration

Edit backend and Firebase values in:

```text
lib/config/app_config.dart
```

## Run

```powershell
flutter pub get
flutter emulators --launch Pixel_10_Pro
flutter run -d emulator-5554
```

## Test

```powershell
flutter test
```
