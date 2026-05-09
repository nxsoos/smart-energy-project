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

## Test

```bash
flutter test
```
