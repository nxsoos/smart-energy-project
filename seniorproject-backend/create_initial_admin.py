from __future__ import annotations

import argparse
import os
from typing import Any

import firebase_admin
from firebase_admin import credentials, db
from dotenv import load_dotenv

from timestamp_utils import ms_to_iso, now_ms


ROLE_PERMISSIONS = {
    "can_view": True,
    "can_control_devices": True,
    "can_change_settings": True,
    "can_manage_users": True,
    "can_manage_schedules": True,
    "can_change_control_mode": True,
    "can_use_ai_chat": True,
    "can_acknowledge_alerts": True,
}


def initialize_firebase() -> None:
    load_dotenv()
    if firebase_admin._apps:
        return
    database_url = os.environ.get("FIREBASE_DATABASE_URL")
    if not database_url:
        raise RuntimeError("FIREBASE_DATABASE_URL is required.")
    service_account_path = os.environ.get("SERVICE_ACCOUNT_PATH") or os.environ.get(
        "GOOGLE_APPLICATION_CREDENTIALS"
    )
    if service_account_path:
        firebase_admin.initialize_app(
            credentials.Certificate(service_account_path),
            {"databaseURL": database_url},
        )
    else:
        firebase_admin.initialize_app(options={"databaseURL": database_url})


def create_initial_admin(uid: str, email: str, display_name: str, home_id: str) -> dict[str, Any]:
    timestamp_ms = now_ms()
    timestamp_iso = ms_to_iso(timestamp_ms)
    user_profile = {
        "uid": uid,
        "email": email,
        "display_name": display_name,
        "default_home_id": home_id,
        "homes": {
            home_id: {
                "role": "admin",
                **ROLE_PERMISSIONS,
            }
        },
        "created_at_ms": timestamp_ms,
        "created_at_iso": timestamp_iso,
        "updated_at_ms": timestamp_ms,
        "updated_at_iso": timestamp_iso,
    }
    member = {
        "uid": uid,
        "email": email,
        "display_name": display_name,
        "role": "admin",
        "permissions": ROLE_PERMISSIONS,
        "added_at_ms": timestamp_ms,
        "added_at_iso": timestamp_iso,
        "updated_at_ms": timestamp_ms,
        "updated_at_iso": timestamp_iso,
    }
    db.reference(f"/users/{uid}").set(user_profile)
    db.reference(f"/homes/{home_id}/members/{uid}").set(member)
    return {"user": user_profile, "member": member}


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the first Smart Energy admin.")
    parser.add_argument("--uid", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", default="Demo Admin")
    parser.add_argument("--home-id", default="home_001")
    args = parser.parse_args()
    initialize_firebase()
    create_initial_admin(args.uid, args.email, args.name, args.home_id)
    print(f"Created admin {args.email} for {args.home_id}.")


if __name__ == "__main__":
    main()
