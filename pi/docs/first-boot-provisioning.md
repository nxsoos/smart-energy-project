# First-Boot Pi and ESP32 Provisioning

This flow uses the Raspberry Pi built-in Wi-Fi for the home network and the TL-WN725N USB Wi-Fi adapter for temporary setup/provisioning.

```text
wlan0 = built-in Pi Wi-Fi, normal home Wi-Fi
wlan1 = TL-WN725N USB Wi-Fi, temporary setup only
```

## First Boot

1. The Pi starts `kahrabaiq-provisioning.service` before the dashboard.
2. If `/var/lib/kahrabaiq/provisioned.json` does not exist, the Pi starts `KahrabaIQ-Pi-Setup` on `wlan1`.
3. Connect a phone or laptop to `KahrabaIQ-Pi-Setup`.
4. Open the setup gateway, commonly `http://10.42.0.1:8080`, or the gateway shown by the device.
5. Enter the home Wi-Fi SSID/password and optional ESP32 device values.
6. The Pi connects `wlan0` to the home Wi-Fi and reaches the backend.
7. The Pi displays a QR pairing code on the locked setup screen.
8. Scan the QR with the mobile app. The scanning user becomes `home_admin`.
9. The Pi waits until the backend returns the real `home_id`.
10. The setup screen shows `Home paired successfully. Waiting for sensors to connect to the Pi...`.
11. The Pi stops the setup AP, connects `wlan1` to `KahrabaIQ-ESP32-Setup`, detects the `wlan1` gateway, and posts to `http://<detected-gateway>/provision` with the real `home_id`.
12. The ESP32 saves the same home Wi-Fi credentials, reboots, and joins the home Wi-Fi.
13. The Pi turns `wlan1` off.
14. The Pi writes `/var/lib/kahrabaiq/provisioned.json` and the normal services/dashboard start.

The dashboard does not start until provisioning succeeds.

The ESP32 setup server IP is not hardcoded in the Pi flow. `ESP32_SETUP_URL` should normally stay empty; the Pi detects the setup gateway from `wlan1`. If the gateway cannot be detected, provisioning fails instead of falling back to a fixed IP.

The ESP32 is not provisioned until QR pairing returns a real `home_id`. This ensures sensor payloads are linked to the correct backend home.

## Normal Boot

If `/var/lib/kahrabaiq/provisioned.json` exists:

```text
wlan0 connects to home Wi-Fi
wlan1 stays off
dashboard starts directly
```

## Admin Unlock

The local dashboard at `http://127.0.0.1:5010/dashboard` has a hidden admin unlock:

```text
Long press the top-right corner for 5 seconds
or press Ctrl+Alt+A with a keyboard
```

Admin can:

- Lock the dashboard again without rebooting.
- View Pi/ESP32 status.
- Restart the kiosk service.
- Start maintenance provisioning mode.

The installer adds a limited `/etc/sudoers.d/kahrabaiq-admin` rule so the local Pi agent can restart the kiosk and start provisioning without giving broad root access.

Set credentials in `/etc/kahrabaiq/pi.env`:

```env
KIOSK_ADMIN_USERNAME=admin
KIOSK_ADMIN_PASSWORD=change_this_admin_password
KIOSK_ADMIN_PIN=
```

For production, use `KIOSK_ADMIN_PASSWORD_HASH` or `KIOSK_ADMIN_PIN_HASH`. The hash is a SHA-256 hex digest.

## Maintenance

To reconfigure Wi-Fi or ESP32:

1. Unlock admin mode from the dashboard.
2. Press `Enter Maintenance`.
3. The kiosk service stops and `kahrabaiq-provisioning.service` starts.
4. Complete provisioning again.
5. `wlan1` turns off and the dashboard can start again.

If setup must be forced over SSH:

```bash
sudo rm -f /var/lib/kahrabaiq/provisioned.json
sudo systemctl restart kahrabaiq-provisioning.service
```

## Requirements

The provisioning service uses NetworkManager:

```bash
nmcli device status
```

Install NetworkManager if `nmcli` is unavailable. Be careful when changing networking over SSH because it can disconnect the session.
