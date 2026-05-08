# Kiosk Setup

Set `KIOSK_DASHBOARD_URL` to the deployed AWS URL, normally `https://YOUR_CLOUD_API_URL/api/kiosk/dashboard`.

The kiosk browser must start after the local agent. The dashboard calls the local agent at `127.0.0.1:${PI_AGENT_PORT}` to get a short-lived kiosk token. If the agent is down or the Pi token is invalid, the dashboard should show an unavailable state instead of a login screen.

Useful checks:

```bash
curl http://127.0.0.1:5010/api/agent/status
curl http://127.0.0.1:5010/api/kiosk/session
sudo journalctl -u kahrabaiq-agent -f
```
