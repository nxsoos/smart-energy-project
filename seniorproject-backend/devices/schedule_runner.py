import os
import time
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[2] / ".env.local")
load_dotenv()

HOME_ID = os.environ.get("HOME_ID", "home_001")
KAHRABAIQ_API_URL = os.environ.get(
    "KAHRABAIQ_API_URL",
    os.environ.get(
        "SMART_ENERGY_API_URL",
        "https://smart-energy-api-qs7uzdqawq-as.a.run.app",
    ),
).rstrip("/")
POLL_INTERVAL_SECONDS = 60
INTERNAL_SERVICE_TOKEN = os.environ.get("INTERNAL_SERVICE_TOKEN", "")
PI_DASHBOARD_TOKEN = os.environ.get("PI_DASHBOARD_TOKEN", "")


def log(message: str) -> None:
    print(f"[SCHEDULE RUNNER] {datetime.now().isoformat()} {message}", flush=True)


def run_due_schedules() -> None:
    headers = {}
    if INTERNAL_SERVICE_TOKEN:
        headers["X-Service-Token"] = INTERNAL_SERVICE_TOKEN
    elif PI_DASHBOARD_TOKEN:
        headers["X-Device-Token"] = PI_DASHBOARD_TOKEN
    response = requests.post(
        f"{KAHRABAIQ_API_URL}/api/home/{HOME_ID}/schedules/run-due",
        headers=headers,
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    count = payload.get("count", 0)
    if count:
        log(f"Processed {count} due schedule(s): {payload.get('results')}")


def main() -> int:
    log(f"Started for {HOME_ID}; API={KAHRABAIQ_API_URL}")
    while True:
        started = time.time()
        try:
            run_due_schedules()
        except Exception as error:
            log(f"Run failed: {error}")

        elapsed = time.time() - started
        time.sleep(max(5, POLL_INTERVAL_SECONDS - elapsed))


if __name__ == "__main__":
    raise SystemExit(main())
