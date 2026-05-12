from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

try:
    from aws_cloud_store import query_summaries_between
except Exception as import_error:
    query_summaries_between = None
    AWS_IMPORT_ERROR = import_error
else:
    AWS_IMPORT_ERROR = None

try:
    from ai_pipeline import (
        DATASET_METADATA_PATH,
        FULL_DATASET_PATH,
        LEGACY_DATASET_PATH,
        TEST_DATASET_PATH,
        TRAIN_DATASET_PATH,
        VALIDATION_DATASET_PATH,
        add_engineered_features,
        feature_columns,
        generate_synthetic_scenario_rows,
        generated_at_iso,
        row_from_summary,
        split_grouped_by_variant,
        write_json,
        LABEL_RULE_VERSION,
        TARGET_COLUMNS,
    )
except ModuleNotFoundError:
    from devices.ai_pipeline import (
        DATASET_METADATA_PATH,
        FULL_DATASET_PATH,
        LEGACY_DATASET_PATH,
        TEST_DATASET_PATH,
        TRAIN_DATASET_PATH,
        VALIDATION_DATASET_PATH,
        add_engineered_features,
        feature_columns,
        generate_synthetic_scenario_rows,
        generated_at_iso,
        row_from_summary,
        split_grouped_by_variant,
        write_json,
        LABEL_RULE_VERSION,
        TARGET_COLUMNS,
    )


DEFAULT_HOME_ID = "home_001"


def load_real_rows(
    home_id: str,
    limit: int,
    fallback_csv: Path | None,
    skip_dynamodb: bool = False,
) -> tuple[list[dict[str, Any]], str]:
    if skip_dynamodb:
        print("[AI DATASET] Skipping DynamoDB read by request.", flush=True)
    elif query_summaries_between is not None:
        try:
            summaries = query_summaries_between(home_id, "hourly", limit=limit)
            if summaries:
                return [row_from_summary(summary) for summary in reversed(summaries)], "dynamodb_hourly_summaries"
        except Exception as error:
            print(f"[AI DATASET] DynamoDB read failed, trying CSV fallback: {error}", flush=True)
    elif AWS_IMPORT_ERROR is not None:
        print(f"[AI DATASET] AWS store unavailable, using CSV/synthetic data: {AWS_IMPORT_ERROR}", flush=True)

    fallback = fallback_csv
    if fallback and fallback.exists():
        data = pd.read_csv(fallback)
        rows = data.to_dict("records")
        for index, row in enumerate(rows):
            row.setdefault("data_origin", "real_dynamodb" if "dynamodb" in str(fallback).lower() else "manual_test")
            row.setdefault("scenario_family", "real_home" if row["data_origin"] == "real_dynamodb" else "manual_test")
            row.setdefault("scenario_variant_id", str(row.get("record_id") or row.get("timestamp_ms") or f"manual_{index}"))
        return rows, f"csv_fallback:{fallback}"

    return [], "no_real_rows"


def metadata_for(data: pd.DataFrame, train: pd.DataFrame, validation: pd.DataFrame, test: pd.DataFrame, source: str, home_id: str) -> dict[str, Any]:
    missing_counts = {column: int(data[column].isna().sum()) for column in data.columns if int(data[column].isna().sum()) > 0}
    date_range = {
        "start_timestamp_ms": int(data["timestamp_ms"].min()) if "timestamp_ms" in data.columns and not data.empty else None,
        "end_timestamp_ms": int(data["timestamp_ms"].max()) if "timestamp_ms" in data.columns and not data.empty else None,
    }
    return {
        "generated_at": generated_at_iso(),
        "source": source,
        "home_id": home_id,
        "row_counts": {
            "full": int(len(data)),
            "train": int(len(train)),
            "validation": int(len(validation)),
            "test": int(len(test)),
        },
        "data_origin_counts": data.get("data_origin", pd.Series(dtype=str)).value_counts(dropna=False).to_dict(),
        "scenario_family_counts": data.get("scenario_family", pd.Series(dtype=str)).value_counts(dropna=False).to_dict(),
        "split_origin_counts": {
            "train": train.get("data_origin", pd.Series(dtype=str)).value_counts(dropna=False).to_dict(),
            "validation": validation.get("data_origin", pd.Series(dtype=str)).value_counts(dropna=False).to_dict(),
            "test": test.get("data_origin", pd.Series(dtype=str)).value_counts(dropna=False).to_dict(),
        },
        "date_range": date_range,
        "feature_count": len(feature_columns(data)),
        "feature_columns": feature_columns(data),
        "target_columns": TARGET_COLUMNS,
        "split_strategy": "grouped_by_scenario_variant_70_15_15_with_unseen_test_variants",
        "missing_data_counts": missing_counts,
        "label_generation_rules_version": LABEL_RULE_VERSION,
        "manual_label_override_file": "devices/datasets/manual_labels.csv",
        "notes": [
            "Real DynamoDB hourly summaries are kept when available.",
            "Synthetic scenario hourly summaries are generated because prototype real data is limited.",
            "Labels are weakly supervised from transparent domain rules unless manual_labels.csv overrides them.",
            "Regression targets use the next chronological hour.",
            "Scenario variants are grouped so one variant does not appear in both train and test.",
        ],
    }


def build(
    home_id: str = DEFAULT_HOME_ID,
    limit: int = 1440,
    fallback_csv: Path | None = None,
    synthetic_rows: int = 1200,
    synthetic_seed: int = 42,
    skip_dynamodb: bool = False,
) -> dict[str, Path]:
    real_rows, source = load_real_rows(home_id, limit, fallback_csv, skip_dynamodb=skip_dynamodb)
    synthetic = generate_synthetic_scenario_rows(synthetic_rows, seed=synthetic_seed) if synthetic_rows > 0 else []
    rows = real_rows + synthetic
    data = pd.DataFrame(rows)
    if data.empty:
        raise RuntimeError("Dataset source produced zero rows.")
    if "timestamp_ms" not in data.columns:
        raise RuntimeError("Dataset rows must include timestamp_ms.")

    data = add_engineered_features(data)
    train, validation, test = split_grouped_by_variant(data)

    FULL_DATASET_PATH.parent.mkdir(parents=True, exist_ok=True)
    data.to_csv(FULL_DATASET_PATH, index=False)
    train.to_csv(TRAIN_DATASET_PATH, index=False)
    validation.to_csv(VALIDATION_DATASET_PATH, index=False)
    test.to_csv(TEST_DATASET_PATH, index=False)
    # Compatibility for older commands/docs.
    data.to_csv(LEGACY_DATASET_PATH, index=False)

    metadata = metadata_for(data, train, validation, test, source, home_id)
    write_json(DATASET_METADATA_PATH, metadata)

    return {
        "full": FULL_DATASET_PATH,
        "train": TRAIN_DATASET_PATH,
        "validation": VALIDATION_DATASET_PATH,
        "test": TEST_DATASET_PATH,
        "metadata": DATASET_METADATA_PATH,
        "legacy": LEGACY_DATASET_PATH,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build KahrabaIQ AI dataset from hourly summaries.")
    parser.add_argument("--home-id", default=DEFAULT_HOME_ID)
    parser.add_argument("--limit", type=int, default=1440)
    parser.add_argument("--fallback-csv", type=Path)
    parser.add_argument("--synthetic-rows", type=int, default=1200)
    parser.add_argument("--synthetic-seed", type=int, default=42)
    parser.add_argument("--no-synthetic", action="store_true")
    parser.add_argument("--skip-dynamodb", action="store_true", help="Build from CSV/synthetic data without querying DynamoDB.")
    args = parser.parse_args()
    outputs = build(
        args.home_id,
        args.limit,
        args.fallback_csv,
        synthetic_rows=0 if args.no_synthetic else args.synthetic_rows,
        synthetic_seed=args.synthetic_seed,
        skip_dynamodb=args.skip_dynamodb,
    )
    print(json.dumps({key: str(path) for key, path in outputs.items()}, indent=2))


if __name__ == "__main__":
    main()
