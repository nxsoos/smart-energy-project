# Backend Deployment

Deploy `api_server.py` as the KahrabaIQ AWS-facing API. The service stores app state in DynamoDB, verifies Cognito user tokens, accepts authenticated Pi sync calls, and issues short-lived kiosk sessions.

Required environment values:

```text
STORAGE_BACKEND=aws
AWS_REGION=eu-west-1
AWS_DYNAMODB_APP_TABLE=KahrabaIQApp
AWS_DYNAMODB_SUMMARIES_TABLE=SmartEnergySummaries
PLATFORM_ADMIN_EMAILS=admin@example.com
AI_SERVICE_URL=https://YOUR_AI_SERVICE_URL
INTERNAL_SERVICE_TOKEN=change_me
KIOSK_SESSION_SECRET=change_me_to_a_long_random_secret
KIOSK_SESSION_TTL_SECONDS=600
KIOSK_COMMAND_TTL_SECONDS=300
HOME_MEMBER_LIMIT=3
PAIRING_TOKEN_TTL_SECONDS=900
HOME_INVITE_TTL_SECONDS=604800
COGNITO_USER_POOL_ID=
COGNITO_APP_CLIENT_ID=
COGNITO_ADMIN_GROUP=SmartEnergyAdmins
COGNITO_MEMBER_GROUP=SmartEnergyMembers
```

The Pi authenticates with `X-Pi-Id` and `X-Device-Token`. The deployed kiosk dashboard must use the local Pi agent session bridge, not the long-lived Pi token.
