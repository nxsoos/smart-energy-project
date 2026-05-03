# Raspberry Pi Smart Energy Hub Setup

Final data flow:

```text
ESP32 sensors -> HTTP POST -> Raspberry Pi Flask server -> Firebase Realtime Database
Flutter/Pi dashboard -> Cloud Run API server -> Firebase Realtime Database
```

The Raspberry Pi preserves the original Firebase layout used by the app:

```text
homes/home_001/devices/esp32_01
homes/home_001/history/sensor_logs/{timestamp_key}
```

## Project Folder

The Pi project should live here:

```bash
/home/ali/smart-energy-hub/
```

Required files:

```text
main.py
firebase_tuya_cloud_controller.py
esp32_sensor_receiver.py
dashboard_server.py
tuya_breakers_to_firebase.py
requirements-ai.txt
serviceAccountKey.json
smart-energy-hub.service
venv/
```

`tuya_breakers_to_firebase.py` is optional and remains disabled in `main.py`
until continuous Tuya metering/history polling is confirmed necessary.

## Install Python Dependencies

```bash
cd /home/ali/smart-energy-hub
python3 -m venv venv
./venv/bin/pip install -r requirements-ai.txt
```

## Install Or Update The systemd Service

```bash
sudo cp /home/ali/smart-energy-hub/smart-energy-hub.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable smart-energy-hub.service
sudo systemctl restart smart-energy-hub.service
```

Watch logs:

```bash
journalctl -u smart-energy-hub.service -f
```

## ESP32 Endpoint

The ESP32 posts sensor JSON to:

```text
http://10.220.38.94:5000/api/sensors/room1
```

## UI API Endpoints

The shared FastAPI backend API runs on Cloud Run:

```text
https://smart-energy-api-qs7uzdqawq-as.a.run.app/api/health
https://smart-energy-api-qs7uzdqawq-as.a.run.app/api/home/home_001/dashboard
https://smart-energy-api-qs7uzdqawq-as.a.run.app/api/home/home_001/devices/breaker_01/command
```

The local touchscreen dashboard still runs on port `5001`, but it now gets
AI/summary data and sends breaker commands through the Cloud Run API layer.
It still overlays fast-changing sensor/device values directly from Firebase for
a live local display:

```text
http://<pi-ip>:5001
```

If the Pi is connected through a phone hotspot, this IP address may change.
Check the Pi IP with:

```bash
hostname -I
```

Then update `PI_SERVER_URL` in the ESP32 code if needed.

The previous ESP32 direct-to-Firebase URL and database paths are left as
disabled comments in `ESP32_code.c`. The full direct-send version is also
recoverable from git history if the project needs to compare behavior later.

## Firebase Paths

Latest ESP32 sensor data:

```text
homes/home_001/devices/esp32_01
```

Sensor history:

```text
homes/home_001/history/sensor_logs/{YYYYMMDD_HHMMSS_microseconds}
```

## Manual Test From Another Device On The Same Network

```bash
curl -X POST http://10.220.38.94:5000/api/sensors/room1 \
  -H "Content-Type: application/json" \
  -d '{"sensors":{"temperature":25.5,"humidity":50},"status":{"online":true}}'
```

Expected response:

```json
{"message":"Sensor data received and saved to Firebase","success":true}
```

## Service Checks

```bash
sudo systemctl status smart-energy-hub.service
journalctl -u smart-energy-hub.service -n 100
```

Restart after changing files:

```bash
sudo systemctl restart smart-energy-hub.service
```
