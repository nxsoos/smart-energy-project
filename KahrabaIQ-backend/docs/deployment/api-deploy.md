# API Deployment

The KahrabaIQ API exposes app, pairing, home, Pi sync, and kiosk endpoints from `api_server.py`.

Core deployment checks:

- Set `STORAGE_BACKEND=aws`.
- Configure `AWS_DYNAMODB_APP_TABLE` and `AWS_DYNAMODB_SUMMARIES_TABLE`.
- Configure Cognito pool/client IDs for phone app users.
- Configure `KIOSK_SESSION_SECRET` with a long random secret.
- Do not expose `PI_DEVICE_TOKEN` to browsers or mobile clients.

Useful local command:

```bash
uvicorn api_server:app --reload
```
