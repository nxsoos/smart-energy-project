import os
import time
from datetime import datetime

import requests


HOME_ID = os.environ.get("HOME_ID", "home_001")
SMART_ENERGY_API_URL = os.environ.get(
    "SMART_ENERGY_API_URL",
    "https://smart-energy-api-qs7uzdqawq-as.a.run.app",
).rstrip("/")
POLL_INTERVAL_SECONDS = 60


def log(message: str) -> None:
    print(f"[SCHEDULE RUNNER] {datetime.now().isoformat()} {message}", flush=True)


def run_due_schedules() -> None:
    response = requests.post(
        f"{SMART_ENERGY_API_URL}/api/home/{HOME_ID}/schedules/run-due",
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    count = payload.get("count", 0)
    if count:
        log(f"Processed {count} due schedule(s): {payload.get('results')}")


def main() -> int:
    log(f"Started for {HOME_ID}; API={SMART_ENERGY_API_URL}")
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
