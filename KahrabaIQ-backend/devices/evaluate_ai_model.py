from __future__ import annotations

import json
from typing import Any

import joblib
import pandas as pd

try:
    from ai_pipeline import (
        CLASSIFICATION_TARGETS,
        CONFUSION_MATRICES_PATH,
        FEATURE_IMPORTANCE_PATH,
        METRICS_PATH,
        MODEL_PATH,
        REGRESSION_TARGETS,
        TEST_DATASET_PATH,
        classification_metrics,
        confusion_matrix_payload,
        extract_feature_importance,
        generated_at_iso,
        regression_metrics,
        write_json,
    )
    from train_ai_model import evaluate_segments, write_evaluation_report
except ModuleNotFoundError:
    from devices.ai_pipeline import (
        CLASSIFICATION_TARGETS,
        CONFUSION_MATRICES_PATH,
        FEATURE_IMPORTANCE_PATH,
        METRICS_PATH,
        MODEL_PATH,
        REGRESSION_TARGETS,
        TEST_DATASET_PATH,
        classification_metrics,
        confusion_matrix_payload,
        extract_feature_importance,
        generated_at_iso,
        regression_metrics,
        write_json,
    )
    from devices.train_ai_model import evaluate_segments, write_evaluation_report


def evaluate() -> dict[str, Any]:
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"Model not found: {MODEL_PATH}. Run train_ai_model.py first.")
    if not TEST_DATASET_PATH.exists():
        raise FileNotFoundError(f"Test dataset not found: {TEST_DATASET_PATH}. Run build_ai_dataset.py first.")

    bundle = joblib.load(MODEL_PATH)
    test = pd.read_csv(TEST_DATASET_PATH).sort_values("timestamp_ms").reset_index(drop=True)
    columns = bundle["feature_columns"]
    models = bundle["models"]
    training_metrics = bundle.get("evaluation_metrics", {})
    dataset_metadata = bundle.get("dataset_metadata", {})
    full_rows = (
        training_metrics.get("dataset_rows")
        or dataset_metadata.get("row_counts", {}).get("full")
        or len(test)
    )

    metrics: dict[str, Any] = {
        "model_name": bundle.get("model_name"),
        "model_version": bundle.get("model_version"),
        "trained_at": bundle.get("trained_at"),
        "evaluated_at": generated_at_iso(),
        "dataset_rows": int(full_rows),
        "train_rows": int(training_metrics.get("train_rows", 0)),
        "validation_rows": int(training_metrics.get("validation_rows", 0)),
        "test_rows": int(len(test)),
        "feature_columns": columns,
        "selected_models": bundle.get("selected_models", {}),
        "targets": {},
        "segment_metrics": {},
        "dataset_metadata": dataset_metadata,
        "data_origin_counts": test.get("data_origin", pd.Series(dtype=str)).value_counts(dropna=False).to_dict(),
        "scenario_family_counts": test.get("scenario_family", pd.Series(dtype=str)).value_counts(dropna=False).to_dict(),
        "warnings": list(bundle.get("evaluation_metrics", {}).get("warnings", [])),
        "limitations": [
            "Because real collected data is limited, the current model is trained using real prototype data plus synthetic scenario data. Metrics on synthetic data show behavior coverage, not guaranteed real-world accuracy.",
            "Labels are weakly supervised unless manual labels are supplied.",
        ],
    }
    confusion_matrices: dict[str, Any] = {}
    importance_rows: list[dict[str, Any]] = []

    for target in CLASSIFICATION_TARGETS:
        model = models[target]
        predictions = model.predict(test[columns])
        metrics["targets"][target] = {"test": classification_metrics(test[target], predictions)}
        confusion_matrices[target] = confusion_matrix_payload(test[target], predictions)
        importance_rows.extend(extract_feature_importance(model, columns, target, metrics["selected_models"].get(target, "unknown")))

    for target in REGRESSION_TARGETS:
        model = models[target]
        predictions = model.predict(test[columns])
        metrics["targets"][target] = {"test": regression_metrics(test[target], predictions)}
        importance_rows.extend(extract_feature_importance(model, columns, target, metrics["selected_models"].get(target, "unknown")))

    metrics["segment_metrics"] = evaluate_segments(test, columns, models)

    write_json(METRICS_PATH, metrics)
    write_json(CONFUSION_MATRICES_PATH, confusion_matrices)
    pd.DataFrame(importance_rows).to_csv(FEATURE_IMPORTANCE_PATH, index=False)
    write_evaluation_report(metrics)
    return metrics


if __name__ == "__main__":
    print(json.dumps(evaluate(), indent=2, default=str))
