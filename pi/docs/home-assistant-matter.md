# Home Assistant And Matter

The Pi runs Home Assistant and the Matter server locally so KahrabaIQ can control Matter devices even when commands are queued from AWS.

## Runtime Shape

```text
KahrabaIQ app/dashboard -> AWS API -> queued command -> Pi command runner -> Home Assistant -> Matter server -> Matter device
```

Home Assistant and Matter run as Docker containers using `pi/home-assistant/docker-compose.yml`.

## Setup

1. Install Docker and Docker Compose v2 on the Pi.
2. Run `KAHRABAIQ_REPO_DIR=/opt/kahrabaiq /opt/kahrabaiq/pi/scripts/setup-home-stack.sh`.
3. Open `http://<pi-ip>:8123` and finish Home Assistant onboarding.
4. In Home Assistant, create a long-lived access token.
5. Set `HOME_ASSISTANT_TOKEN` in `/etc/kahrabaiq/pi.env`.
6. Add the Matter integration in Home Assistant and pair the Matter devices.
7. Set `MATTER_SOCKET_SWITCH_ENTITY_ID` and `MATTER_AC_SWITCH_ENTITY_ID` in `/etc/kahrabaiq/pi.env` to the actual Home Assistant entity IDs.
8. Restart the command runner with `sudo systemctl restart kahrabaiq-command-runner`.

## Services

- `kahrabaiq-home-stack`: starts/stops the Home Assistant and Matter containers.
- `kahrabaiq-command-runner`: polls AWS-queued device commands and executes them locally through Tuya or Home Assistant.

## Checks

```bash
docker ps
curl http://127.0.0.1:8123/api/
sudo journalctl -u kahrabaiq-command-runner -f
```

The command runner needs `HOME_ASSISTANT_COMMAND_MODE=queue` for the cloud API path where the Pi executes Matter commands locally.
