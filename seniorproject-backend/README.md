# KahrabaIQ Backend Workspace

Python workspace for the cloud API, AI service, Firebase deployment files, and Raspberry Pi edge code.

## Layout

```text
seniorproject-backend/
  api_server.py                 Cloud API for Flutter and Pi sync
  main.py                       AI service entry point
  home_assistant_controller.py  Shared Home Assistant integration
  occupancy_utils.py            Occupancy calculations
  timestamp_utils.py            Time helpers
  devices/                      Raspberry Pi dashboard/services/firmware
  docs/                         Deployment and AI reports
  functions/                    Firebase Cloud Functions
```

## Cloud API Local Run

```bash
pip install -r requirements.txt
uvicorn api_server:app --reload
```

## AI Service Local Run

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

## Docs

```text
docs/deployment/
docs/ai/
devices/docs/
```

## Secrets

Do not commit Firebase service account keys, API keys, `.env` files, Pi device tokens, or kiosk passwords. Use environment variables or a secret manager.
