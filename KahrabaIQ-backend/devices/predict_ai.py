from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

try:
    from ai_pipeline import MODEL_PATH, as_number
except ModuleNotFoundError:
    from devices.ai_pipeline import MODEL_PATH, as_number


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
        "ac_avg_power_W": 80.0,
        "total_avg_power_W": 100.0,
        "total_peak_power_W": 170.0,
        "total_energy_kWh": 0.1,
        "total_cost_BHD": 0.0032,
        "tariff_BHD_per_kWh": 0.032,
    }


def confidence_from_model(model: Any, row: pd.DataFrame, prediction: Any) -> float | None:
    estimator = model.named_steps.get("model")
    if not hasattr(estimator, "predict_proba"):
        return None
    probabilities = model.predict_proba(row)[0]
    classes = list(estimator.classes_)
    if prediction not in classes:
        return None
    return round(float(probabilities[classes.index(prediction)]), 4)


def top_factors(bundle: dict[str, Any], payload: dict[str, Any], limit: int = 5) -> list[dict[str, Any]]:
    metrics = bundle.get("evaluation_metrics") or {}
    columns = bundle.get("feature_columns") or []
    factors = []
    for column in columns:
        value = payload.get(column)
        if value in {None, "", False}:
            continue
        numeric = abs(as_number(value, 0))
        if numeric <= 0 and not isinstance(value, str):
            continue
        factors.append({"feature": column, "value": value, "reason": "available_runtime_feature"})
    return factors[:limit]


def confidence_label(confidence: float | None) -> str:
    if confidence is None:
        return "unknown"
    if confidence >= 0.8:
        return "high"
    if confidence >= 0.55:
        return "medium"
    return "low"


def predict(payload: dict[str, Any]) -> dict[str, Any]:
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"Model not found: {MODEL_PATH}. Run train_ai_model.py first.")

    bundle = joblib.load(MODEL_PATH)
    feature_columns: list[str] = bundle["feature_columns"]
    models: dict[str, Any] = bundle["models"]
    row = pd.DataFrame([{column: payload.get(column) for column in feature_columns}])
    result: dict[str, Any] = {
        "model_name": bundle["model_name"],
        "model_version": bundle["model_version"],
        "ai_mode": "full_ml",
        "predictions": {},
        "top_factors": top_factors(bundle, payload),
        "data_source": payload.get("data_source", "manual_payload"),
    }

    confidences: list[float] = []
    for target, model in models.items():
        prediction = model.predict(row)[0]
        value: Any = prediction.item() if hasattr(prediction, "item") else prediction
        item = {"value": value, "model": bundle.get("selected_models", {}).get(target)}
        confidence = confidence_from_model(model, row, prediction)
        if confidence is not None:
            item["confidence"] = confidence
            confidences.append(confidence)
        result["predictions"][target] = item
        result[target] = item

    confidence = round(sum(confidences) / len(confidences), 4) if confidences else None
    result["confidence"] = {"value": confidence, "label": confidence_label(confidence)}
    result["energy_efficiency_score"] = calculate_efficiency_score(result, payload)
    result["explanation"] = build_explanation(result, payload)
    return result


def build_explanation(result: dict[str, Any], payload: dict[str, Any]) -> str:
    waste = bool(result["waste_event"]["value"])
    anomaly = str(result["anomaly_label"]["value"])
    recommendation = str(result["recommendation_type"]["value"])
    if waste and as_number(payload.get("occupancy_score"), 1) < 0.2:
        return "Energy waste is likely because power is active while occupancy evidence is low."
    if anomaly not in {"normal", "low_usage_normal"}:
        return f"AI detected {anomaly} and recommends {recommendation}."
    return "Current usage looks normal for the available features."


def calculate_efficiency_score(result: dict[str, Any], payload: dict[str, Any]) -> int:
    score = 100
    if bool(result["waste_event"]["value"]):
        score -= 30
    if str(result["anomaly_label"]["value"]) not in {"normal", "low_usage_normal"}:
        score -= 20
    if as_number(payload.get("occupancy_score"), 1) < 0.2 and as_number(payload.get("total_avg_power_W")) > 20:
        score -= 20
    return max(0, min(100, score))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run KahrabaIQ Intelligence prediction.")
    parser.add_argument("--payload", help="JSON string or path to a JSON file. If omitted, a demo payload is used.")
    args = parser.parse_args()
    print(json.dumps(predict(load_payload(args.payload)), indent=2, default=str))


if __name__ == "__main__":
    main()
