from __future__ import annotations

import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.metrics import accuracy_score, mean_absolute_error


BASE_DIR = Path(__file__).resolve().parent
DATASET_PATH = BASE_DIR / "ai_ready_dataset_60_days.csv"
MODEL_PATH = BASE_DIR / "models" / "smart_energy_ai.joblib"


def evaluate() -> dict[str, object]:
    bundle = joblib.load(MODEL_PATH)
    data = pd.read_csv(DATASET_PATH).sort_values("timestamp_ms").reset_index(drop=True)
    if "next_hour_total_energy_kWh" not in data.columns:
        data["next_hour_total_energy_kWh"] = data["total_energy_kWh"].shift(-1)
    if "next_hour_total_cost_BHD" not in data.columns:
        data["next_hour_total_cost_BHD"] = data["total_cost_BHD"].shift(-1)
    data = data.dropna(subset=["next_hour_total_energy_kWh", "next_hour_total_cost_BHD"], how="any")
    feature_columns = bundle["feature_columns"]
    x = data[feature_columns]
    metrics: dict[str, object] = {"rows": int(len(data)), "model_version": bundle.get("model_version")}
    for target, model in bundle["models"].items():
        predictions = model.predict(x)
        if target in {"waste_event", "anomaly_label", "recommendation_type"}:
            metrics[target] = {"accuracy": round(float(accuracy_score(data[target], predictions)), 4)}
        else:
            metrics[target] = {"mean_absolute_error": round(float(mean_absolute_error(data[target], predictions)), 6)}
    return metrics


if __name__ == "__main__":
    print(json.dumps(evaluate(), indent=2))
