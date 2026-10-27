import argparse
import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import IsolationForest, RandomForestClassifier, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder


FEATURE_COLUMNS = [
    "transaction_count",
    "average_transaction",
    "change_from_previous_pct",
    "top_category",
    "top_merchant",
]


def build_feature_pipeline():
    numeric_features = ["transaction_count", "average_transaction", "change_from_previous_pct"]
    categorical_features = ["top_category", "top_merchant"]

    numeric_pipeline = Pipeline(steps=[
        ("imputer", SimpleImputer(strategy="median")),
    ])
    categorical_pipeline = Pipeline(steps=[
        ("imputer", SimpleImputer(strategy="most_frequent")),
        ("encoder", OneHotEncoder(handle_unknown="ignore")),
    ])

    return ColumnTransformer(transformers=[
        ("numeric", numeric_pipeline, numeric_features),
        ("categorical", categorical_pipeline, categorical_features),
    ])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="CSV exported from reporting_monthly_summary")
    parser.add_argument("--output", required=True, help="Directory for model artifacts")
    args = parser.parse_args()

    data = pd.read_csv(args.input)
    data = data.sort_values("month_key")
    data["next_month_total_spent"] = data.groupby("user_id")["total_spent"].shift(-1)
    data["next_top_category"] = data.groupby("user_id")["top_category"].shift(-1)

    trainable = data.dropna(subset=["next_month_total_spent", "next_top_category"]).copy()
    if trainable.empty:
        raise RuntimeError("Not enough rows to train. Export more monthly summary data first.")

    features = trainable[FEATURE_COLUMNS]
    preprocessor = build_feature_pipeline()
    transformed = preprocessor.fit_transform(features)

    spend_regressor = RandomForestRegressor(n_estimators=150, random_state=42)
    spend_regressor.fit(transformed, trainable["next_month_total_spent"])

    category_classifier = RandomForestClassifier(n_estimators=150, random_state=42)
    category_classifier.fit(transformed, trainable["next_top_category"])

    anomaly_detector = IsolationForest(contamination=0.1, random_state=42)
    anomaly_detector.fit(transformed)

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(preprocessor, output_dir / "preprocessor.joblib")
    joblib.dump(spend_regressor, output_dir / "spend_regressor.joblib")
    joblib.dump(category_classifier, output_dir / "category_classifier.joblib")
    joblib.dump(anomaly_detector, output_dir / "anomaly_detector.joblib")

    metadata = {
        "feature_columns": FEATURE_COLUMNS,
        "models": [
            "spend_regressor.joblib",
            "category_classifier.joblib",
            "anomaly_detector.joblib",
        ],
    }
    (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
