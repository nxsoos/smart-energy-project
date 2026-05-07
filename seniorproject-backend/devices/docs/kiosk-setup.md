# Raspberry Pi Kiosk Setup

The Pi dashboard is currently local-only and should open at:

```text
http://localhost:5001
```

Recommended environment values on the Pi:

```text
PI_ID=pi_unique_id
PI_DEVICE_TOKEN=random_secret_token
HOME_ID=home_id_after_pairing
CLOUD_BACKEND_ENABLED=true
KAHRABAIQ_API_URL=https://your-cloud-api
KIOSK_ADMIN_PASSWORD_HASH=sha256_password_hash
```

Chromium kiosk command:

```bash
chromium-browser --kiosk --noerrdialogs --disable-infobars http://localhost:5001
```

Admin unlock prototype:

- Tap the top-left logo/device area five times.
- Enter the configured kiosk admin password.
- The current implementation unlocks the dashboard UI. OS-level kiosk exit/reboot actions should be wired through systemd or a privileged local helper before production.

Production notes:

- Store only `PI_DEVICE_TOKEN` locally on the Pi.
- Store only the token hash in the backend.
- Later AWS deployment can reuse `X-Pi-Id` and `X-Device-Token` to restrict access to authorized Pi devices.
