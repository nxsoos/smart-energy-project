import csv
import time
from pathlib import Path
from typing import Any

import firebase_admin
from firebase_admin import credentials, db


# ============================================================
# Firebase settings
# ============================================================

SERVICE_ACCOUNT_PATH = "serviceAccountKey.json"

DATABASE_URL = (
    "https://seniorproject-energy-default-rtdb.asia-southeast1."
    "firebasedatabase.app"
)

HOME_ID = "home_001"

# Put the CSV file in the same folder as this script
CSV_FILE = "ai_ready_dataset_60_days.csv"

UPLOAD_PATH = f"/homes/{HOME_ID}/ai_dataset/training/ready_dataset"


# ============================================================
# Helpers
# ============================================================

def convert_value(value: str) -> Any:
    """
    Converts CSV string values into correct Firebase-friendly types.
    """
    if value is None:
        return None

    value = value.strip()

    if value == "":
        return None

    if value.lower() == "true":
        return True

    if value.lower() == "false":
        return False

    if value.lower() == "null":
        return None

    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def initialize_firebase() -> None:
    """
    Initializes Firebase Admin SDK.
    """
    if not firebase_admin._apps:
        cred = credentials.Certificate(SERVICE_ACCOUNT_PATH)
        firebase_admin.initialize_app(
            cred,
            {
                "databaseURL": DATABASE_URL,
            },
        )


def import_dataset() -> None:
    initialize_firebase()

    csv_path = Path(CSV_FILE)

    if not csv_path.exists():
        raise FileNotFoundError(
            f"CSV file not found: {CSV_FILE}. "
            "Put the dataset CSV in the same folder as this script."
        )

    records = {}
    fieldnames = []

    with csv_path.open(mode="r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        fieldnames = reader.fieldnames or []

        for index, row in enumerate(reader):
            record = {
                key: convert_value(value)
                for key, value in row.items()
            }

            record_id = record.get("record_id")

            if not record_id:
                record_id = f"ready_{index + 1:05d}"
                record["record_id"] = record_id

            record["imported_at"] = int(time.time() * 1000)

            records[record_id] = record

    if not records:
        print("No records found in CSV.")
        return

    print(f"Preparing to upload {len(records)} records...")
    print(f"Upload path: {UPLOAD_PATH}")

    # This replaces/updates records under ready_dataset.
    db.reference(UPLOAD_PATH).update(records)

    metadata = {
        "dataset_name": "ai_ready_dataset_60_days",
        "record_count": len(records),
        "uploaded_at": int(time.time() * 1000),
        "source": "synthetic_ready_dataset",
        "path": UPLOAD_PATH,
        "schema_version": 2,
        "feature_columns": fieldnames,
        "noise_fields": {
            "raw_sensor_fields": ["sound_raw", "noise", "noise_text"],
            "dataset_columns": ["avg_sound_raw", "noise_count"],
        },
    }

    db.reference(f"/homes/{HOME_ID}/ai_dataset/metadata/ready_dataset").set(
        metadata
    )

    print("Dataset uploaded successfully.")
    print(metadata)


if __name__ == "__main__":
    import_dataset()
