# Tuya Setup

Tuya Cloud is backup only. The final breaker command path should use Home Assistant entities, not direct Tuya Cloud calls from the Pi. Do not commit real Tuya secrets to this repository.

For normal operation, keep:

```env
USE_HOME_ASSISTANT_FOR_BREAKERS=true
USE_TUYA_CLOUD_FOR_BREAKERS=false
```

And disable the legacy poller:

```bash
sudo systemctl stop kahrabaiq-tuya-breaker-poller
sudo systemctl disable kahrabaiq-tuya-breaker-poller
```

## Backup Values

Only set these in `/etc/kahrabaiq/pi.env` if you intentionally re-enable Tuya Cloud backup control:

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

The command runner uses these values only when `USE_TUYA_CLOUD_FOR_BREAKERS=true`. By default, `breaker_01` and `breaker_02` use Home Assistant.
