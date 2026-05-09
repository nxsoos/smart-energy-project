# KahrabaIQ Manual Checks

Use these checks after deploying the EC2 FastAPI backend and restarting the Pi services.

## 1. Pi Heartbeat

Run from the Pi:

```bash
curl -X POST "$KAHRABAIQ_API_URL/api/pi/$PI_ID/heartbeat" \
  -H "X-Pi-Id: $PI_ID" \
  -H "X-Device-Token: $PI_DEVICE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"status":"online","agent_version":"manual-check"}'
```

Expected result:

- HTTP `200`
- `success=true`
- returned `pi_id` matches the Pi

## 2. Pi State Upload

Run from the Pi:

```bash
curl -X POST "$KAHRABAIQ_API_URL/api/pi/$PI_ID/sensor-state" \
  -H "X-Pi-Id: $PI_ID" \
  -H "X-Device-Token: $PI_DEVICE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "home_id":"home_001",
    "room":{"temperature":24.5,"humidity":55,"smoke":false,"smoke_text":"Clear","online":true},
    "devices":{"breaker_01":{"state":"off","online":true}},
    "alerts":[],
    "safety":{"smoke_state":{"status":"clear","last_clear_at_ms":1710000000000}}
  }'
```

Expected result:

- HTTP `200`
- `latest_state` for the home updates

## 3. App Command Creation

Run with a valid Cognito bearer token:

```bash
curl -X POST "$KAHRABAIQ_API_URL/api/home/home_001/cloud/commands" \
  -H "Authorization: Bearer $ID_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"device_id":"breaker_01","command":"turn_on","requested_by":"flutter_app","source":"manual_test"}'
```

Expected result:

- HTTP `200`
- `status` is `PENDING`
- the device record shows `command_in_progress=true`

## 4. Pi Command Poll And Claim

Run from the Pi:

```bash
curl "$KAHRABAIQ_API_URL/api/pi/$PI_ID/remote-commands?limit=10" \
  -H "X-Pi-Id: $PI_ID" \
  -H "X-Device-Token: $PI_DEVICE_TOKEN"
```

Expected result:

- pending command appears with `status=PENDING`

Then claim it:

```bash
curl -X POST "$KAHRABAIQ_API_URL/api/pi/$PI_ID/remote-commands/$COMMAND_ID/claim" \
  -H "X-Pi-Id: $PI_ID" \
  -H "X-Device-Token: $PI_DEVICE_TOKEN"
```

Expected result:

- `status=CLAIMED`

## 5. Command Executing And Completion

```bash
curl -X POST "$KAHRABAIQ_API_URL/api/pi/$PI_ID/remote-commands/$COMMAND_ID/executing" \
  -H "X-Pi-Id: $PI_ID" \
  -H "X-Device-Token: $PI_DEVICE_TOKEN"
```

Expected result:

- `status=EXECUTING`

Complete success:

```bash
curl -X POST "$KAHRABAIQ_API_URL/api/pi/$PI_ID/remote-commands/$COMMAND_ID/complete" \
  -H "X-Pi-Id: $PI_ID" \
  -H "X-Device-Token: $PI_DEVICE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"success":true,"message":"Command completed.","result":{"success":true,"actual_state":"on"}}'
```

Expected result:

- `status=SUCCEEDED`
- device `command_in_progress=false`
- device `last_command_status=SUCCEEDED`

## 6. Smoke/Gas Alert Create

Send Pi state with a smoke alert:

```bash
curl -X POST "$KAHRABAIQ_API_URL/api/pi/$PI_ID/sensor-state" \
  -H "X-Pi-Id: $PI_ID" \
  -H "X-Device-Token: $PI_DEVICE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "home_id":"home_001",
    "room":{"smoke":true,"smoke_text":"Detected","online":true},
    "devices":{"esp32_01":{"sensors":{"smoke":true,"smoke_text":"Detected","timestamp_ms":1710000005000}}},
    "alerts":[{"alert_id":"smoke_detected_room1","alert_type":"smoke_detected","severity":"critical","status":"OPEN","title":"Smoke/Gas Detected","message":"Smoke or gas was detected in Room 1."}],
    "safety":{"smoke_state":{"status":"confirmed","last_clear_at_ms":null},"emergency_mode":{"active":true}}
  }'
```

Expected result:

- active alert exists once
- a notification is created for home members
- Flutter app shows popup
- Pi dashboard shows popup

## 7. Duplicate Alert Prevention

Repeat the same smoke upload while the alert is still open.

Expected result:

- same active alert is updated
- no second active smoke alert appears

## 8. Auto Resolve After 15 Seconds Clear

Send a clear Pi state with `smoke=false` and a `last_clear_at_ms` older than 15 seconds.

Expected result:

- active smoke alert disappears
- history keeps the alert with `status=AUTO_RESOLVED`
- Flutter popup disappears
- Pi dashboard popup disappears

## 9. Notifications API

List notifications:

```bash
curl "$KAHRABAIQ_API_URL/api/users/me/notifications" \
  -H "Authorization: Bearer $ID_TOKEN"
```

Mark one read:

```bash
curl -X POST "$KAHRABAIQ_API_URL/api/users/me/notifications/$NOTIFICATION_ID/read" \
  -H "Authorization: Bearer $ID_TOKEN"
```

Mark all read:

```bash
curl -X POST "$KAHRABAIQ_API_URL/api/users/me/notifications/read-all" \
  -H "Authorization: Bearer $ID_TOKEN"
```

## 10. Summaries And Insights

```bash
curl "$KAHRABAIQ_API_URL/api/homes/home_001/summaries/hourly" -H "Authorization: Bearer $ID_TOKEN"
curl "$KAHRABAIQ_API_URL/api/homes/home_001/summaries/daily" -H "Authorization: Bearer $ID_TOKEN"
curl "$KAHRABAIQ_API_URL/api/homes/home_001/insights" -H "Authorization: Bearer $ID_TOKEN"
curl "$KAHRABAIQ_API_URL/api/homes/home_001/recommendations" -H "Authorization: Bearer $ID_TOKEN"
```

Expected result:

- hourly and daily summaries come from Pi-generated DynamoDB records
- insights include peak usage, trends, alert repetition, and command reliability when data exists
- recommendations are derived from insights and existing backend recommendations
