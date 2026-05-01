# Smart Energy Backend

Backend workspace for the Smart Energy project.

## Parts

```text
main.py                 FastAPI AI service for Cloud Run
requirements.txt       Python dependencies for the AI service
Dockerfile             Cloud Run container build
devices/               AI scripts, local Firebase scripts, and model files
functions/             Firebase Cloud Functions project
README_DEPLOY.md       Cloud Run deployment guide
```

## Local AI Service

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:FIREBASE_DATABASE_URL="https://YOUR_DATABASE.firebaseio.com"
uvicorn main:app --reload
```

## Firebase Functions

```powershell
cd functions
npm install
npm run build
npm run serve
```

## Secrets

Do not commit Firebase service account keys or API keys. Cloud Run should use
Application Default Credentials, and Gemini keys should be set as environment
variables or stored in a secret manager.
