# Raspberry Pi KahrabaIQ Hub Setup

Final data flow:

```text
ESP32 sensors -> HTTP POST -> Raspberry Pi Flask server -> local SQLite
Tuya breakers -> Raspberry Pi poller -> local SQLite
Matter switches -> Home Assistant -> Raspberry Pi server -> local SQLite
Flutter/Pi dashboard -> Raspberry Pi local API for live data/control
Raspberry Pi -> AWS DynamoDB for hourly/daily summaries only
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

`tuya_breakers_to_firebase.py` is now the local Tuya breaker telemetry poller
when `FIREBASE_ENABLED=false`. `aws_summary_sync.py` is optional and only runs
when `ENABLE_AWS_SUMMARY_SYNC=true`.

## Install Python Dependencies

```bash
cd /home/ali/smart-energy-hub
python3 -m venv venv
./venv/bin/pip install -r requirements-ai.txt
```

## Configure ESP32 Device Key

The Pi receiver rejects sensor uploads unless the ESP32 sends the same shared
key in the `X-Device-Key` HTTP header.

Create a local environment file on the Raspberry Pi:

```bash
cat >/home/ali/smart-energy-hub/.env <<'EOF'
ESP32_DEVICE_KEY=replace-with-a-long-random-device-key
HOME_ID=home_001
FIREBASE_ENABLED=false
ENABLE_AWS_SUMMARY_SYNC=true
ENABLE_AWS_REMOTE_COMMANDS=true
ENABLE_AWS_IOT_LIVE=true
AWS_REGION=eu-west-1
AWS_DYNAMODB_SUMMARIES_TABLE=SmartEnergySummaries
AWS_IOT_ENDPOINT=your-iot-endpoint-ats.iot.eu-west-1.amazonaws.com
AWS_IOT_CERT_PATH=/home/ali/smart-energy-hub/certs/device.pem.crt
AWS_IOT_KEY_PATH=/home/ali/smart-energy-hub/certs/private.pem.key
AWS_IOT_CA_PATH=/home/ali/smart-energy-hub/certs/AmazonRootCA1.pem
EOF
chmod 600 /home/ali/smart-energy-hub/.env
```

Use that same value in `ESP32_DEVICE_KEY` inside `ESP32_code.c`, then flash the
ESP32.

## Configure AWS Summary Uploads

The Pi uploader uses normal AWS SDK credentials. Configure the restricted
`smart-energy-pi-uploader` access key on the Raspberry Pi:

```bash
./venv/bin/pip install -r requirements-ai.txt
aws configure --profile smart-energy-pi-uploader
```

Then add this to `/home/ali/smart-energy-hub/.env`:

```bash
AWS_PROFILE=smart-energy-pi-uploader
ENABLE_AWS_SUMMARY_SYNC=true
ENABLE_AWS_REMOTE_COMMANDS=true
AWS_REGION=eu-west-1
AWS_DYNAMODB_SUMMARIES_TABLE=SmartEnergySummaries
```

The uploader writes only compact items like:

```text
PK = HOME#home_001
SK = SUMMARY#HOURLY#2026-05-08T14
SK = SUMMARY#DAILY#2026-05-08
```

It does not upload raw sensor readings, raw breaker polls, or live device
states.

## Configure AWS Remote Commands

When `ENABLE_AWS_REMOTE_COMMANDS=true`, the Pi polls DynamoDB for remote command
requests written by the cloud API:

```text
PK = HOME#home_001
SK = COMMAND#REMOTE#...
```

The Pi executes pending commands locally through Tuya Cloud or Home Assistant,
then writes the command result back to the same DynamoDB item. This lets the
mobile app request control from outside the home without exposing the Pi to the
public internet.

## Configure AWS IoT Core Live Data

When `ENABLE_AWS_IOT_LIVE=true`, the Pi publishes compact live state to AWS IoT
Core MQTT:

```text
homes/home_001/live/state
```

This is for live dashboard data outside the home network. It publishes only the
latest compact state every 15 seconds, not raw history.

Required `.env` values:

```bash
ENABLE_AWS_IOT_LIVE=true
AWS_IOT_ENDPOINT=your-iot-endpoint-ats.iot.eu-west-1.amazonaws.com
AWS_IOT_CLIENT_ID=smart-energy-pi-home_001
AWS_IOT_LIVE_TOPIC=homes/home_001/live/state
AWS_IOT_LIVE_INTERVAL_SECONDS=15
AWS_IOT_CERT_PATH=/home/ali/smart-energy-hub/certs/device.pem.crt
AWS_IOT_KEY_PATH=/home/ali/smart-energy-hub/certs/private.pem.key
AWS_IOT_CA_PATH=/home/ali/smart-energy-hub/certs/AmazonRootCA1.pem
```

The Pi certificate policy needs permission to connect and publish to:

```text
homes/home_001/live/state
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
  -H "X-Device-Key: replace-with-a-long-random-device-key" \
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
