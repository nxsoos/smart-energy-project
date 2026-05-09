# Tuya Setup

Tuya credentials are required only on the Raspberry Pi runtime environment. Do not commit real Tuya secrets to this repository.

## Required Values

Set these in `/etc/kahrabaiq/pi.env` on the Pi:

```env
TUYA_ACCESS_ID=your_tuya_cloud_access_id
TUYA_ACCESS_SECRET=your_tuya_cloud_access_secret
TUYA_API_ENDPOINT=https://openapi.tuyaeu.com
TUYA_BREAKER_01_DEVICE_ID=your_switch_breaker_device_id
TUYA_BREAKER_02_DEVICE_ID=your_ac_breaker_device_id
TUYA_VERIFY_ATTEMPTS=7
```

## Where To Get Them

- `TUYA_ACCESS_ID`: Tuya IoT Platform project access ID.
- `TUYA_ACCESS_SECRET`: Tuya IoT Platform project access secret.
- `TUYA_API_ENDPOINT`: Tuya data center endpoint. Keep `https://openapi.tuyaeu.com` if your project is in the Europe data center.
- `TUYA_BREAKER_01_DEVICE_ID`: Tuya device ID for the switch breaker.
- `TUYA_BREAKER_02_DEVICE_ID`: Tuya device ID for the AC breaker.

## Apply Changes

After editing `/etc/kahrabaiq/pi.env`, restart the command runner:

```bash
sudo systemctl restart kahrabaiq-command-runner
sudo journalctl -u kahrabaiq-command-runner -f
```

The command runner uses these values for `breaker_01` and `breaker_02`. Matter devices continue to use Home Assistant entity IDs.
