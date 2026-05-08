# KahrabaIQ Backend Workspace

Python workspace for the AWS cloud API and AI service.

## Layout

```text
seniorproject-backend/
  api_server.py                 Cloud API for Flutter and Pi sync
  main.py                       AI service entry point
  aws_cloud_store.py            DynamoDB path-store helpers
  home_assistant_controller.py  Shared Home Assistant integration
  occupancy_utils.py            Occupancy calculations
  timestamp_utils.py            Time helpers
  devices/                      Legacy Pi dashboard reference code
  docs/                         Deployment and AI reports
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

## Secrets

Do not commit API keys, `.env` files, Pi device tokens, kiosk secrets, or passwords. Use environment variables or a secret manager.
