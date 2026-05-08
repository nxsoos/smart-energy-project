# Legacy Pi Dashboard Notes

The production touchscreen should open the deployed AWS-hosted kiosk dashboard. The local Pi browser must not receive the long-lived Pi token.

Use `pi/scripts/launch-kiosk.sh` and `pi/systemd/kahrabaiq-kiosk-browser.service` for Chromium kiosk startup.
