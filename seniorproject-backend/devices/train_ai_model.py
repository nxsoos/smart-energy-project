from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score, classification_report, mean_absolute_error
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder


BASE_DIR = Path(__file__).resolve().parent
DATASET_PATH = BASE_DIR / "ai_ready_dataset_60_days.csv"
MODEL_DIR = BASE_DIR / "models"
MODEL_PATH = MODEL_DIR / "smart_energy_ai.joblib"
METRICS_PATH = MODEL_DIR / "smart_energy_ai_metrics.json"

TARGET_COLUMNS = [
    "waste_event",
    "anomaly_label",
    "recommendation_type",
    "next_hour_total_energy_kWh",
    "next_hour_total_cost_BHD",
]

IGNORED_COLUMNS = {
    "record_id",
    "timestamp_ms",
    "datetime_bahrain",
    "date",
    "data_source",
}


def load_dataset() -> pd.DataFrame:
    if not DATASET_PATH.exists():
        raise FileNotFoundError(f"Dataset not found: {DATASET_PATH}")

    data = pd.read_csv(DATASET_PATH)

    required = {"waste_event", "anomaly_label", "recommendation_type"}
    missing = required.difference(data.columns)
    if missing:
        raise ValueError(f"Dataset is missing required columns: {sorted(missing)}")

    data = data.sort_values("timestamp_ms").reset_index(drop=True)
    data["next_hour_total_energy_kWh"] = data["total_energy_kWh"].shift(-1)
    data["next_hour_total_cost_BHD"] = data["total_cost_BHD"].shift(-1)
    data = data.dropna(subset=["next_hour_total_energy_kWh", "next_hour_total_cost_BHD"])

    return data


def build_preprocessor(data: pd.DataFrame, feature_columns: list[str]) -> ColumnTransformer:
    numeric_features = [
        column
        for column in feature_columns
        if pd.api.types.is_numeric_dtype(data[column])
    ]
    categorical_features = [
        column for column in feature_columns if column not in numeric_features
    ]

    numeric_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
        ]
    )

    categorical_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore")),
        ]
    )

    return ColumnTransformer(
        transformers=[
            ("numeric", numeric_pipeline, numeric_features),
            ("categorical", categorical_pipeline, categorical_features),
        ]
    )


def build_classifier(preprocessor: ColumnTransformer) -> Pipeline:
    return Pipeline(
        steps=[
            ("preprocess", preprocessor),
            (
                "model",
                RandomForestClassifier(
                    n_estimators=120,
                    max_depth=None,
                    min_samples_leaf=2,
                    random_state=42,
                    class_weight="balanced",
                    n_jobs=-1,
                ),
            ),
        ]
    )


def build_regressor(preprocessor: ColumnTransformer) -> Pipeline:
    return Pipeline(
        steps=[
            ("preprocess", preprocessor),
            (
                "model",
                RandomForestRegressor(
                    n_estimators=120,
                    max_depth=None,
                    min_samples_leaf=2,
                    random_state=42,
                    n_jobs=-1,
                ),
            ),
        ]
    )


def train() -> dict[str, Any]:
    data = load_dataset()
    feature_columns = [
        column
        for column in data.columns
        if column not in TARGET_COLUMNS and column not in IGNORED_COLUMNS
    ]

    train_data, test_data = train_test_split(
        data,
        test_size=0.2,
        shuffle=False,
    )

    x_train = train_data[feature_columns]
    x_test = test_data[feature_columns]

    models: dict[str, Pipeline] = {}
    metrics: dict[str, Any] = {
        "dataset_rows": int(len(data)),
        "train_rows": int(len(train_data)),
        "test_rows": int(len(test_data)),
        "feature_columns": feature_columns,
        "targets": TARGET_COLUMNS,
    }

    for target in ["waste_event", "anomaly_label", "recommendation_type"]:
        preprocessor = build_preprocessor(data, feature_columns)
        model = build_classifier(preprocessor)
        model.fit(x_train, train_data[target])

        predictions = model.predict(x_test)
        metrics[target] = {
            "accuracy": round(float(accuracy_score(test_data[target], predictions)), 4),
            "report": classification_report(
                test_data[target],
                predictions,
                zero_division=0,
                output_dict=True,
            ),
        }
        models[target] = model

    for target in ["next_hour_total_energy_kWh", "next_hour_total_cost_BHD"]:
        preprocessor = build_preprocessor(data, feature_columns)
        model = build_regressor(preprocessor)
        model.fit(x_train, train_data[target])

        predictions = model.predict(x_test)
        metrics[target] = {
            "mean_absolute_error": round(
                float(mean_absolute_error(test_data[target], predictions)),
                6,
            )
        }
        models[target] = model

    bundle = {
        "model_name": "smart_energy_ai",
        "model_version": 1,
        "feature_columns": feature_columns,
        "models": models,
    }

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, MODEL_PATH, compress=3)
    METRICS_PATH.write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    return metrics


def main() -> None:
    metrics = train()

    print("Smart Energy AI trained successfully.")
    print(f"Model saved to: {MODEL_PATH}")
    print(f"Metrics saved to: {METRICS_PATH}")
    print()
    print("Key metrics:")
    print(f"- waste_event accuracy: {metrics['waste_event']['accuracy']}")
    print(f"- anomaly_label accuracy: {metrics['anomaly_label']['accuracy']}")
    print(
        "- recommendation_type accuracy: "
        f"{metrics['recommendation_type']['accuracy']}"
    )
    print(
        "- next_hour_total_energy_kWh MAE: "
        f"{metrics['next_hour_total_energy_kWh']['mean_absolute_error']}"
    )
    print(
        "- next_hour_total_cost_BHD MAE: "
        f"{metrics['next_hour_total_cost_BHD']['mean_absolute_error']}"
    )


if __name__ == "__main__":
    main()
