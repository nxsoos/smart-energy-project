# KahrabaIQ ESP32 Firmware

Firmware lives in `esp32/firmware/ESP32_code.c`.

The ESP32 starts a setup hotspot when no Wi-Fi config is saved:

- SSID: `KahrabaIQ-ESP32-Setup`
- Password: `kahrabaiq123`
- Setup URL: `http://192.168.4.1`

After provisioning, it connects to home Wi-Fi, advertises `kahrabaiq-esp32.local`, and posts sensor payloads to the Pi receiver.

## HTTP Contract

- `GET /status`: returns Wi-Fi, setup, device, and sensor readiness status.
- `POST /provision`: saves Wi-Fi, Pi receiver URL, Pi ID, home ID, device ID, and device key, then reboots.
- `POST /reset`: clears saved config and reboots into setup mode.
