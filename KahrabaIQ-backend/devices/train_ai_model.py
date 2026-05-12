from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

try:
    from ai_pipeline import (
        CLASSIFICATION_TARGETS,
        DATASET_METADATA_PATH,
        EVALUATION_REPORT_PATH,
        FEATURE_IMPORTANCE_PATH,
        FULL_DATASET_PATH,
        LEGACY_DATASET_PATH,
        METRICS_PATH,
        MODEL_DIR,
        MODEL_PATH,
        MODEL_VERSION,
        REGRESSION_TARGETS,
        TARGET_COLUMNS,
        TEST_DATASET_PATH,
        TRAIN_DATASET_PATH,
        VALIDATION_DATASET_PATH,
        build_preprocessor,
        candidate_classifiers,
        candidate_regressors,
        classification_metrics,
        confusion_matrix_payload,
        extract_feature_importance,
        feature_columns,
        generated_at_iso,
        regression_metrics,
        split_grouped_by_variant,
        write_json,
        add_engineered_features,
    )
except ModuleNotFoundError:
    from devices.ai_pipeline import (
        CLASSIFICATION_TARGETS,
        DATASET_METADATA_PATH,
        EVALUATION_REPORT_PATH,
        FEATURE_IMPORTANCE_PATH,
        FULL_DATASET_PATH,
        LEGACY_DATASET_PATH,
        METRICS_PATH,
        MODEL_DIR,
        MODEL_PATH,
        MODEL_VERSION,
        REGRESSION_TARGETS,
        TARGET_COLUMNS,
        TEST_DATASET_PATH,
        TRAIN_DATASET_PATH,
        VALIDATION_DATASET_PATH,
        build_preprocessor,
        candidate_classifiers,
        candidate_regressors,
        classification_metrics,
        confusion_matrix_payload,
        extract_feature_importance,
        feature_columns,
        generated_at_iso,
        regression_metrics,
        split_grouped_by_variant,
        write_json,
        add_engineered_features,
    )


def load_split_or_build() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    metadata: dict[str, Any] = {}
    if DATASET_METADATA_PATH.exists():
        metadata = json.loads(DATASET_METADATA_PATH.read_text(encoding="utf-8"))
    if TRAIN_DATASET_PATH.exists() and VALIDATION_DATASET_PATH.exists() and TEST_DATASET_PATH.exists():
        train = pd.read_csv(TRAIN_DATASET_PATH)
        validation = pd.read_csv(VALIDATION_DATASET_PATH)
        test = pd.read_csv(TEST_DATASET_PATH)
        full = pd.concat([train, validation, test], ignore_index=True).sort_values("timestamp_ms").reset_index(drop=True)
        return full, train, validation, test, metadata

    source_path = FULL_DATASET_PATH if FULL_DATASET_PATH.exists() else LEGACY_DATASET_PATH
    if not source_path.exists():
        raise FileNotFoundError(f"Dataset not found. Run devices/build_ai_dataset.py first. Missing: {source_path}")
    full = pd.read_csv(source_path).sort_values("timestamp_ms").reset_index(drop=True)
    missing_targets = [target for target in TARGET_COLUMNS if target not in full.columns]
    if missing_targets:
        full = add_engineered_features(full)
    train, validation, test = split_grouped_by_variant(full)
    return full, train, validation, test, metadata


def train_classifier_target(
    target: str,
    full: pd.DataFrame,
    train: pd.DataFrame,
    validation: pd.DataFrame,
    test: pd.DataFrame,
    columns: list[str],
) -> tuple[str, Any, dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    x_train = train[columns]
    x_validation = validation[columns]
    x_test = test[columns]
    class_count = int(train[target].nunique())
    candidates = candidate_classifiers(build_preprocessor(full, columns), class_count, len(train))
    candidate_metrics: dict[str, Any] = {}
    fitted: dict[str, Any] = {}

    for name, model in candidates.items():
        try:
            model.fit(x_train, train[target])
            predictions = model.predict(x_validation)
            metrics = classification_metrics(validation[target], predictions)
            candidate_metrics[name] = metrics
            fitted[name] = model
        except Exception as error:
            candidate_metrics[name] = {"error": str(error)}

    valid_names = [name for name, metrics in candidate_metrics.items() if "f1_macro" in metrics]
    best_name = max(valid_names, key=lambda name: candidate_metrics[name]["f1_macro"]) if valid_names else next(iter(fitted))
    best_model = fitted[best_name]
    test_predictions = best_model.predict(x_test)
    test_metrics = classification_metrics(test[target], test_predictions)
    confusion = confusion_matrix_payload(test[target], test_predictions)
    importance = extract_feature_importance(best_model, columns, target, best_name)
    return best_name, best_model, {"validation": candidate_metrics, "test": test_metrics}, confusion, importance


def train_regression_target(
    target: str,
    full: pd.DataFrame,
    train: pd.DataFrame,
    validation: pd.DataFrame,
    test: pd.DataFrame,
    columns: list[str],
) -> tuple[str, Any, dict[str, Any], list[dict[str, Any]]]:
    x_train = train[columns]
    x_validation = validation[columns]
    x_test = test[columns]
    candidates = candidate_regressors(build_preprocessor(full, columns), len(train))
    candidate_metrics: dict[str, Any] = {}
    fitted: dict[str, Any] = {}

    for name, model in candidates.items():
        try:
            model.fit(x_train, train[target])
            predictions = model.predict(x_validation)
            metrics = regression_metrics(validation[target], predictions)
            candidate_metrics[name] = metrics
            fitted[name] = model
        except Exception as error:
            candidate_metrics[name] = {"error": str(error)}

    valid_names = [name for name, metrics in candidate_metrics.items() if "mae" in metrics]
    best_name = min(valid_names, key=lambda name: candidate_metrics[name]["mae"]) if valid_names else next(iter(fitted))
    best_model = fitted[best_name]
    test_predictions = best_model.predict(x_test)
    test_metrics = regression_metrics(test[target], test_predictions)
    importance = extract_feature_importance(best_model, columns, target, best_name)
    return best_name, best_model, {"validation": candidate_metrics, "test": test_metrics}, importance


def write_evaluation_report(metrics: dict[str, Any]) -> None:
    lines = [
        "# KahrabaIQ Smart Energy AI Evaluation",
        "",
        f"Generated at: {metrics['trained_at']}",
        f"Model version: {metrics['model_version']}",
        "",
        "## Dataset",
        "",
        f"- Full rows: {metrics['dataset_rows']}",
        f"- Train rows: {metrics['train_rows']}",
        f"- Validation rows: {metrics['validation_rows']}",
        f"- Test rows: {metrics['test_rows']}",
        f"- Feature count: {len(metrics['feature_columns'])}",
        f"- Data origin counts: `{json.dumps(metrics.get('data_origin_counts', {}))}`",
        "",
        "## Selected Models",
        "",
    ]
    for target, name in metrics["selected_models"].items():
        lines.append(f"- `{target}`: {name}")
    lines.extend(["", "## Test Metrics", ""])
    for target, target_metrics in metrics["targets"].items():
        lines.append(f"### {target}")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(target_metrics["test"], indent=2))
        lines.append("```")
        lines.append("")
    if metrics.get("segment_metrics"):
        lines.extend(["## Segment Metrics", ""])
        for segment_name, segment_payload in metrics["segment_metrics"].items():
            lines.append(f"### {segment_name}")
            lines.append("")
            lines.append("```json")
            lines.append(json.dumps(segment_payload, indent=2))
            lines.append("```")
            lines.append("")
    lines.extend(
        [
            "## Limitations",
            "",
            "Because real collected data is limited, the current model is trained using real prototype data plus synthetic scenario data. Metrics on synthetic data show behavior coverage, not guaranteed real-world accuracy.",
            "",
            "KahrabaIQ currently uses weakly supervised labels generated from transparent domain rules. "
            "This is suitable for a prototype and allows the system to train on collected smart-home data, "
            "but future work should include manually labeled events from real users to improve accuracy and reduce bias.",
        ]
    )
    EVALUATION_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    EVALUATION_REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def evaluate_segments(test: pd.DataFrame, columns: list[str], models: dict[str, Any]) -> dict[str, Any]:
    segments: dict[str, pd.DataFrame] = {"all_test_data": test}
    if "data_origin" in test.columns:
        for origin, subset in test.groupby("data_origin"):
            if len(subset) >= 3:
                segments[f"origin:{origin}"] = subset
    if "scenario_family" in test.columns:
        for family, subset in test.groupby("scenario_family"):
            if len(subset) >= 3:
                segments[f"scenario_family:{family}"] = subset

    payload: dict[str, Any] = {}
    for segment_name, subset in segments.items():
        segment_targets: dict[str, Any] = {"rows": int(len(subset))}
        for target in CLASSIFICATION_TARGETS:
            predictions = models[target].predict(subset[columns])
            segment_targets[target] = classification_metrics(subset[target], predictions)
        for target in REGRESSION_TARGETS:
            predictions = models[target].predict(subset[columns])
            segment_targets[target] = regression_metrics(subset[target], predictions)
        payload[segment_name] = segment_targets
    return payload


def train() -> dict[str, Any]:
    full, train, validation, test, dataset_metadata = load_split_or_build()
    columns = feature_columns(full)
    if not columns:
        raise RuntimeError("No feature columns were found.")

    models: dict[str, Any] = {}
    selected_models: dict[str, str] = {}
    target_metrics: dict[str, Any] = {}
    confusion_matrices: dict[str, Any] = {}
    importance_rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    if len(full) < 100:
        warnings.append("Dataset too small for robust model comparison.")

    for target in CLASSIFICATION_TARGETS:
        best_name, model, metrics, confusion, importance = train_classifier_target(target, full, train, validation, test, columns)
        models[target] = model
        selected_models[target] = best_name
        target_metrics[target] = metrics
        confusion_matrices[target] = confusion
        importance_rows.extend(importance)

    for target in REGRESSION_TARGETS:
        best_name, model, metrics, importance = train_regression_target(target, full, train, validation, test, columns)
        models[target] = model
        selected_models[target] = best_name
        target_metrics[target] = metrics
        importance_rows.extend(importance)

    metrics_payload = {
        "model_name": "smart_energy_ai",
        "model_version": MODEL_VERSION,
        "trained_at": generated_at_iso(),
        "dataset_rows": int(len(full)),
        "train_rows": int(len(train)),
        "validation_rows": int(len(validation)),
        "test_rows": int(len(test)),
        "feature_columns": columns,
        "targets": target_metrics,
        "segment_metrics": evaluate_segments(test, columns, models),
        "selected_models": selected_models,
        "data_origin_counts": full.get("data_origin", pd.Series(dtype=str)).value_counts(dropna=False).to_dict(),
        "scenario_family_counts": full.get("scenario_family", pd.Series(dtype=str)).value_counts(dropna=False).to_dict(),
        "dataset_metadata": dataset_metadata,
        "warnings": warnings,
        "limitations": [
            "Because real collected data is limited, the current model is trained using real prototype data plus synthetic scenario data. Metrics on synthetic data show behavior coverage, not guaranteed real-world accuracy.",
            "Labels are weakly supervised unless manual labels are supplied.",
        ],
    }
    bundle = {
        "model_name": "smart_energy_ai",
        "model_version": MODEL_VERSION,
        "trained_at": metrics_payload["trained_at"],
        "feature_columns": columns,
        "target_columns": TARGET_COLUMNS,
        "classification_targets": CLASSIFICATION_TARGETS,
        "regression_targets": REGRESSION_TARGETS,
        "models": models,
        "selected_models": selected_models,
        "dataset_metadata": dataset_metadata,
        "evaluation_metrics": metrics_payload,
        "preprocessing": {
            "numeric": "median imputation",
            "categorical": "most_frequent imputation + one_hot_encoding",
        },
    }

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, MODEL_PATH, compress=3)
    write_json(METRICS_PATH, metrics_payload)
    write_json(Path(str(METRICS_PATH).replace("_metrics.json", "_confusion_matrices.json")), confusion_matrices)
    pd.DataFrame(importance_rows).to_csv(FEATURE_IMPORTANCE_PATH, index=False)
    write_evaluation_report(metrics_payload)
    return metrics_payload


def main() -> None:
    metrics = train()
    print("KahrabaIQ Intelligence trained successfully.")
    print(f"Model saved to: {MODEL_PATH}")
    print(f"Metrics saved to: {METRICS_PATH}")
    print(f"Evaluation report saved to: {EVALUATION_REPORT_PATH}")
    print()
    print("Selected models:")
    for target, model_name in metrics["selected_models"].items():
        print(f"- {target}: {model_name}")
    print()
    print("Test metrics:")
    for target, target_metrics in metrics["targets"].items():
        print(f"- {target}: {json.dumps(target_metrics['test'], default=str)}")


if __name__ == "__main__":
    main()
