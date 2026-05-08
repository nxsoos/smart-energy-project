# Legacy Pi Service Notes

Current Pi deployment assets live in the top-level `pi/` folder.

Use these files for production Pi setup:

- `pi/agent/pi_agent.py`
- `pi/agent/esp32_receiver.py`
- `pi/agent/summary_sync.py`
- `pi/systemd/*.service`
- `pi/.env.sample`

The Pi writes local SQLite state, syncs live state to the AWS backend, uploads summaries to DynamoDB, and executes deployed kiosk commands through the local agent.
