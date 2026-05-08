# KahrabaIQ ESP32 Firmware

Firmware lives in `esp32/firmware/ESP32_code.c`.

The ESP32 starts a setup hotspot when no Wi-Fi config is saved:

- SSID: `KahrabaIQ-ESP32-Setup`
- Password: `kahrabaiq123`
- Setup URL: `http://192.168.4.1`

After provisioning, it connects to home Wi-Fi, advertises `kahrabaiq-esp32.local`, and posts sensor payloads to the Pi receiver.

If no Wi-Fi/Pi config exists, the firmware stays in setup mode and does not spam upload attempts. After provisioning, it reboots into normal mode and posts sensor data every 3 seconds.

## Provisioning Example

Connect your phone or laptop to the setup hotspot, then send:

```bash
curl -X POST http://192.168.4.1/provision \
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

## HTTP Contract

- `GET /status`: returns Wi-Fi, setup, device, and sensor readiness status.
- `POST /provision`: saves Wi-Fi, Pi receiver URL, Pi ID, home ID, device ID, and device key, then reboots.
- `POST /reset`: clears saved config and reboots into setup mode.
