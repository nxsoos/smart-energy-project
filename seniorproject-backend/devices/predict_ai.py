from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import joblib
import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
MODEL_PATH = BASE_DIR / "models" / "smart_energy_ai.joblib"


def load_payload(payload_arg: str | None) -> dict[str, Any]:
    if payload_arg:
        payload_path = Path(payload_arg)
        if payload_path.exists():
            return json.loads(payload_path.read_text(encoding="utf-8"))
        return json.loads(payload_arg)

    return {
        "hour_of_day": 18,
        "day_of_week": "Thursday",
        "is_weekend": False,
        "sample_count": 350,
        "avg_temperature": 27.5,
        "avg_humidity": 55.0,
        "avg_sound_raw": 780,
        "motion_count": 2,
        "bright_count": 300,
        "smoke_count": 0,
        "noise_count": 1,
        "high_temp_count": 20,
        "occupancy_score": 0.05,
        "switch_avg_power_W": 20.0,
        "switch_peak_power_W": 50.0,
        "switch_energy_kWh": 0.02,
        "ac_avg_power_W": 80.0,
        "ac_peak_power_W": 120.0,
        "ac_energy_kWh": 0.08,
        "total_avg_power_W": 100.0,
        "total_peak_power_W": 170.0,
        "total_energy_kWh": 0.1,
        "total_cost_BHD": 0.0032,
        "tariff_BHD_per_kWh": 0.032,
    }


def confidence_from_model(model: Any, row: pd.DataFrame, prediction: Any) -> float | None:
    classifier = model.named_steps.get("model")
    if not hasattr(classifier, "predict_proba"):
        return None

    probabilities = model.predict_proba(row)[0]
    classes = list(classifier.classes_)
    predicted_index = classes.index(prediction)
    return round(float(probabilities[predicted_index]), 4)


def build_explanation(result: dict[str, Any], payload: dict[str, Any]) -> str:
    waste = result["waste_event"]["value"]
    anomaly = result["anomaly_label"]["value"]
    recommendation = result["recommendation_type"]["value"]

    if waste:
        if payload.get("occupancy_score", 1) < 0.2 and payload.get("total_avg_power_W", 0) > 0:
            return "Energy waste is likely because power usage is active while occupancy appears low."
        return "Energy waste is likely based on the current power, room, and time pattern."

    if anomaly != "normal":
        return f"Abnormal usage pattern detected: {anomaly}."

    if recommendation != "none":
        return f"The AI recommends a {recommendation} action based on the current pattern."

    return "Current usage looks normal compared with the training pattern."


def predict(payload: dict[str, Any]) -> dict[str, Any]:
    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"Model not found: {MODEL_PATH}. Run train_ai_model.py first."
        )

    bundle = joblib.load(MODEL_PATH)
    feature_columns: list[str] = bundle["feature_columns"]
    models: dict[str, Any] = bundle["models"]

    row = pd.DataFrame([{column: payload.get(column) for column in feature_columns}])

    result: dict[str, Any] = {
        "model_name": bundle["model_name"],
        "model_version": bundle["model_version"],
    }

    for target, model in models.items():
        prediction = model.predict(row)[0]
        value: Any = prediction.item() if hasattr(prediction, "item") else prediction

        result[target] = {
            "value": value,
        }

        confidence = confidence_from_model(model, row, prediction)
        if confidence is not None:
            result[target]["confidence"] = confidence

    result["energy_efficiency_score"] = calculate_efficiency_score(result, payload)
    result["explanation"] = build_explanation(result, payload)

    return result


def calculate_efficiency_score(result: dict[str, Any], payload: dict[str, Any]) -> int:
    score = 100

    if result["waste_event"]["value"]:
        score -= 30

    if result["anomaly_label"]["value"] != "normal":
        score -= 20

    if payload.get("high_temp_count", 0) > 0 and payload.get("ac_avg_power_W", 0) > 0:
        score -= 10

    if payload.get("occupancy_score", 1) < 0.2 and payload.get("total_avg_power_W", 0) > 0:
        score -= 20

    return max(0, min(100, score))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Smart Energy AI prediction.")
    parser.add_argument(
        "--payload",
        help="JSON string or path to a JSON file. If omitted, a demo payload is used.",
    )
    args = parser.parse_args()

    payload = load_payload(args.payload)
    result = predict(payload)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
