# API Deployment

The KahrabaIQ API exposes app, pairing, home, Pi sync, and kiosk endpoints from `api_server.py`.

Core deployment checks:

- Set `STORAGE_BACKEND=aws`.
- Configure `AWS_DYNAMODB_APP_TABLE` and `AWS_DYNAMODB_SUMMARIES_TABLE`.
- Configure Cognito pool/client IDs for phone app users.
- Configure `KIOSK_SESSION_SECRET` with a long random secret.
- Do not expose `PI_DEVICE_TOKEN` to browsers or mobile clients.
- Point `api.kahrabaiq.com` and `dashboard.kahrabaiq.com` to the EC2 public IP.
- Proxy both domains to the backend and pass `X-Real-IP` plus `X-Forwarded-For`; dashboard access is checked against Pi public IPs learned from heartbeat.
- Set `DASHBOARD_ALLOWED_HEARTBEAT_AGE_SECONDS=900` and `DASHBOARD_ACCESS_DEFAULT_ENABLED=true` unless you want platform admins to enable each Pi manually.

Nginx must preserve the real client IP:

```nginx
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
```

Recommended DNS:

```text
api.kahrabaiq.com        A -> EC2_PUBLIC_IP
dashboard.kahrabaiq.com  A -> EC2_PUBLIC_IP
```

Useful local command:

```bash
uvicorn api_server:app --reload
```
