# ESP32 Provisioning Contract

`POST /provision` accepts JSON:

```json
{
  "ssid": "Home WiFi",
  "password": "wifi-password",
  "pi_base_url": "http://192.168.1.55:5010",
  "pi_sensor_url": "http://192.168.1.55:5000/api/sensors/room1",
  "home_id": "home_001",
  "pi_id": "pi_unique_id",
  "device_id": "esp32_01",
  "device_key": "shared-device-key"
}
```

Required fields are `ssid`, `password`, and either `pi_sensor_url` or `pi_base_url`.

The Pi normally fills `pi_base_url` and `pi_sensor_url` from its current Wi-Fi IP at provisioning time. Do not hardcode stale Pi LAN IPs in production config.

The ESP32 sends `X-Device-Key` with every sensor POST to the Pi receiver.
