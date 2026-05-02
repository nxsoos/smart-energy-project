import os
import signal
import subprocess
import time
from pathlib import Path


BASE_DIR = Path("/home/ali/smart-energy-hub")
PYTHON_BIN = BASE_DIR / "venv" / "bin" / "python"
RESTART_DELAY_SECONDS = 5


SCRIPTS = [
    "firebase_tuya_cloud_controller.py",
    "esp32_sensor_receiver.py",
    "dashboard_server.py",
    # Enable this only if the hub must continuously copy Tuya metering/status
    # into Firebase history in addition to processing breaker commands.
    # "tuya_breakers_to_firebase.py",
]


running_processes: dict[str, subprocess.Popen] = {}
shutting_down = False


def log(message: str) -> None:
    print(f"[MAIN] {message}", flush=True)


def start_script(script_name: str) -> subprocess.Popen:
    script_path = BASE_DIR / script_name
    if not script_path.exists():
        raise FileNotFoundError(f"Script not found: {script_path}")

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    log(f"Starting {script_name}")
    return subprocess.Popen(
        [str(PYTHON_BIN), str(script_path)],
        cwd=str(BASE_DIR),
        env=env,
    )


def stop_all_processes() -> None:
    global shutting_down
    shutting_down = True

    log("Stopping subprocesses...")
    for script_name, process in list(running_processes.items()):
        if process.poll() is None:
            log(f"Stopping {script_name}")
            process.terminate()

    deadline = time.time() + 10
    for script_name, process in list(running_processes.items()):
        if process.poll() is not None:
            continue

        remaining = max(0, deadline - time.time())
        try:
            process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            log(f"Force stopping {script_name}")
            process.kill()

    running_processes.clear()
    log("All subprocesses stopped")


def handle_shutdown(signum, frame) -> None:
    stop_all_processes()


def monitor_scripts() -> None:
    for script_name in SCRIPTS:
        running_processes[script_name] = start_script(script_name)

    while not shutting_down:
        for script_name, process in list(running_processes.items()):
            return_code = process.poll()
            if return_code is None:
                continue

            log(f"{script_name} stopped with exit code {return_code}")
            if shutting_down:
                continue

            log("Script stopped, restarting...")
            time.sleep(RESTART_DELAY_SECONDS)
            running_processes[script_name] = start_script(script_name)

        time.sleep(1)


def main() -> int:
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    log(f"Hub working directory: {BASE_DIR}")
    log(f"Using Python: {PYTHON_BIN}")

    try:
        monitor_scripts()
    except KeyboardInterrupt:
        stop_all_processes()
    except Exception as error:
        log(f"Fatal error: {error}")
        stop_all_processes()
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
