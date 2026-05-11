# KahrabaIQ ESP32 Firmware

Firmware lives in `esp32/firmware/ESP32_code.c`.

The ESP32 starts a setup hotspot when no Wi-Fi config is saved:

- SSID: `KahrabaIQ-ESP32-Setup`
- Password: `kahrabaiq123`
- Setup URL: detected by the Pi from the ESP32 hotspot gateway

After provisioning, it connects to home Wi-Fi, advertises `kahrabaiq-esp32.local`, and posts sensor payloads to the Pi receiver.

If no Wi-Fi/Pi config exists, the firmware stays in setup mode and does not spam upload attempts. After provisioning, it reboots into normal mode and posts sensor data every 3 seconds.

## Recommended Pi-Led Provisioning Flow

In the deployed system, the Raspberry Pi provisions the ESP32 before the locked dashboard starts. The Pi uses two Wi-Fi interfaces:

```text
wlan0 = built-in Pi Wi-Fi connected to the home Wi-Fi
wlan1 = TL-WN725N USB adapter used temporarily for setup/provisioning
```

Sequence:

1. ESP32 starts in setup mode and exposes `KahrabaIQ-ESP32-Setup`.
2. Pi first-boot setup collects the home Wi-Fi SSID/password from the installer.
3. Pi connects `wlan0` to the home Wi-Fi.
4. Pi displays a QR pairing code after internet is available.
5. The mobile app scans the QR and the backend returns the real `home_id`.
6. Pi connects `wlan1` to `KahrabaIQ-ESP32-Setup`.
7. Pi detects the ESP32 setup gateway from `wlan1` and sends `POST http://<detected-gateway>/provision` with the home Wi-Fi credentials, real `home_id`, and Pi receiver URL.
8. ESP32 saves the config, reboots, joins the same home Wi-Fi as the Pi, and starts sending sensor data.
9. Pi turns `wlan1` off and starts the locked dashboard only after provisioning completes.

The Pi-side implementation is in `pi/agent/pi_provisioning.py`. The dashboard is blocked until `/var/lib/kahrabaiq/provisioned.json` exists.

## Provisioning Example

Connect your phone or laptop to the setup hotspot, detect the hotspot gateway from your device network settings, then send:

```bash
curl -X POST http://<detected-gateway>/provision \
  -H "Content-Type: application/json" \
  -d '{
    "ssid":"YOUR_WIFI_NAME",
    "password":"YOUR_WIFI_PASSWORD",
    "pi_sensor_url":"http://10.220.38.94:5000/api/sensors/room1",
    "home_id":"home_001",
    "pi_id":"pi_home_001",
    "device_id":"esp32_01",
    "device_key":"esp32_01_key_123"
  }'
```

The `device_key` must match `ESP32_DEVICE_KEY` in the Pi environment file.

The normal production path is for the Pi to send this request automatically. Manual `curl` provisioning is mainly for firmware testing or recovery.

## HTTP Contract

- `GET /status`: returns Wi-Fi, setup, device, and sensor readiness status.
- `POST /provision`: saves Wi-Fi, Pi receiver URL, Pi ID, home ID, device ID, and device key, then reboots.
- `POST /reset`: clears saved config and reboots into setup mode.
