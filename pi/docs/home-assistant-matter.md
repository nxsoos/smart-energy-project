# Home Assistant Breakers And Matter

The Pi runs Home Assistant and the Matter server locally so KahrabaIQ can control breakers and Matter devices even when commands are queued from AWS.

## Runtime Shape

```text
KahrabaIQ app/dashboard -> AWS API -> queued command -> Pi command runner -> Home Assistant -> breaker or Matter device
```

Home Assistant and Matter run as Docker containers using `pi/home-assistant/docker-compose.yml`.

## Setup

1. Install Docker and Docker Compose v2 on the Pi.
2. Run `KAHRABAIQ_REPO_DIR=/opt/kahrabaiq /opt/kahrabaiq/pi/scripts/setup-home-stack.sh`.
3. Open `http://<pi-ip>:8123` and finish Home Assistant onboarding.
4. In Home Assistant, create a long-lived access token.
5. Set `HOME_ASSISTANT_TOKEN` in `/etc/kahrabaiq/pi.env`.
6. Add the Matter integration in Home Assistant and pair the Matter devices.
7. Set breaker and Matter entity IDs in `/etc/kahrabaiq/pi.env`.
8. Restart the command runner with `sudo systemctl restart kahrabaiq-command-runner`.

## Breaker Entity IDs

For the current Home Assistant setup:

```env
USE_HOME_ASSISTANT_FOR_BREAKERS=true
USE_TUYA_CLOUD_FOR_BREAKERS=false
AC_BREAKER_ENTITY_ID=switch.ac_breaker_switch
SOCKET_BREAKER_ENTITY_ID=switch.socket_breaker_switch
MATTER_AC_SWITCH_ENTITY_ID=switch.ac_breaker_switch
MATTER_SOCKET_SWITCH_ENTITY_ID=switch.socket_breaker_switch
```

Optional metering sensor entity IDs:

```env
AC_BREAKER_CURRENT_ENTITY_ID=sensor.ac_breaker_current
AC_BREAKER_POWER_ENTITY_ID=sensor.ac_breaker_power
AC_BREAKER_VOLTAGE_ENTITY_ID=sensor.ac_breaker_voltage
AC_BREAKER_ENERGY_ENTITY_ID=sensor.ac_breaker_energy
SOCKET_BREAKER_CURRENT_ENTITY_ID=sensor.socket_breaker_current
SOCKET_BREAKER_POWER_ENTITY_ID=sensor.socket_breaker_power
SOCKET_BREAKER_VOLTAGE_ENTITY_ID=sensor.socket_breaker_voltage
SOCKET_BREAKER_ENERGY_ENTITY_ID=sensor.socket_breaker_energy
```

## Services

- `kahrabaiq-home-stack`: starts/stops the Home Assistant and Matter containers.
- `kahrabaiq-command-runner`: polls AWS-queued device commands and executes them locally through Tuya or Home Assistant.

## Checks

```bash
docker ps
curl http://127.0.0.1:8123/api/
curl -H "Authorization: Bearer $HOME_ASSISTANT_TOKEN" http://127.0.0.1:8123/api/
curl -X POST -H "Authorization: Bearer $HOME_ASSISTANT_TOKEN" -H "Content-Type: application/json" -d '{"entity_id":"switch.ac_breaker_switch"}' http://127.0.0.1:8123/api/services/switch/turn_on
curl -X POST -H "Authorization: Bearer $HOME_ASSISTANT_TOKEN" -H "Content-Type: application/json" -d '{"entity_id":"switch.socket_breaker_switch"}' http://127.0.0.1:8123/api/services/switch/turn_off
sudo journalctl -u kahrabaiq-command-runner -f
```

The command runner needs `HOME_ASSISTANT_COMMAND_MODE=queue` for the cloud API path where the Pi executes commands locally through Home Assistant.
