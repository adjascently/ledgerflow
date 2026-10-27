from __future__ import annotations

import json
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd


ZERO = Decimal("0")
HUNDRED = Decimal("100")

FEATURE_COLUMNS = [
    "transaction_count",
    "average_transaction",
    "change_from_previous_pct",
    "top_category",
    "top_merchant",
]


def _to_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _to_money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _safe_average(total: Decimal, count: int) -> Decimal:
    if count <= 0:
        return ZERO
    return total / Decimal(str(count))


def _percentage_change(current: Decimal, previous: Decimal | None):
    if previous is None or previous <= ZERO:
        return None
    return ((current - previous) / previous) * HUNDRED


def _heuristic_prediction(payload: dict[str, Any]) -> dict[str, Any]:
    ordered_months = [_to_decimal(value) for value in payload.get("monthlyTotals", [])]
    category_amounts = {
        category: _to_decimal(amount)
        for category, amount in (payload.get("categoryTotals") or {}).items()
    }
    focus_total = _to_decimal(payload.get("focusMonthTotal", 0))
    previous_total = _to_decimal(payload.get("previousMonthTotal", 0))
    anomaly_count = int(payload.get("anomalyCount", 0))

    recent = [total for total in ordered_months if total > ZERO][-3:]
    if not recent:
        forecast = ZERO
        confidence = "low"
    elif len(recent) == 1:
        forecast = recent[0]
        confidence = "low"
    elif len(recent) == 2:
        forecast = (recent[1] * Decimal("0.65")) + (recent[0] * Decimal("0.35"))
        confidence = "medium"
    else:
        forecast = (
            (recent[2] * Decimal("0.50"))
            + (recent[1] * Decimal("0.30"))
            + (recent[0] * Decimal("0.20"))
        )
        confidence = "medium"

    total_category_spend = sum(category_amounts.values(), ZERO)
    sorted_categories = sorted(category_amounts.items(), key=lambda item: item[1], reverse=True)[:3]
    category_suggestions = []
    for category, amount in sorted_categories:
        share = (amount / total_category_spend * HUNDRED) if total_category_spend > ZERO else ZERO
        confidence_score = min(0.95, max(0.35, float(share / Decimal("100")) + 0.2))
        category_suggestions.append({
            "category": category,
            "confidence": round(confidence_score, 2),
            "reason": f"{category} has been one of the strongest spending categories in the recent history.",
        })

    change_pct = _percentage_change(focus_total, previous_total)
    anomaly_score = Decimal("0.15")
    if change_pct is not None and change_pct > Decimal("20"):
        anomaly_score += Decimal("0.30")
    if anomaly_count > 0:
        anomaly_score += min(Decimal("0.40"), Decimal(str(anomaly_count)) * Decimal("0.10"))

    anomaly_score = min(Decimal("0.95"), anomaly_score)
    if anomaly_score >= Decimal("0.70"):
        level = "high"
    elif anomaly_score >= Decimal("0.40"):
        level = "medium"
    else:
        level = "low"

    return {
        "modelName": "sagemaker-baseline-fallback",
        "forecastAmount": float(_to_money(forecast)),
        "forecastConfidence": confidence,
        "predictedTopCategories": category_suggestions,
        "anomalyRisk": {
            "level": level,
            "score": float(anomaly_score.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            "reason": "Derived from month-over-month changes and unusually large transactions.",
        },
    }


def _build_feature_frame(payload: dict[str, Any]) -> pd.DataFrame:
    monthly_totals = [_to_decimal(value) for value in payload.get("monthlyTotals", [])]
    category_totals = payload.get("categoryTotals") or {}
    focus_total = _to_decimal(payload.get("focusMonthTotal", 0))
    previous_total = _to_decimal(payload.get("previousMonthTotal", 0))

    positive_months = [value for value in monthly_totals if value > ZERO]
    transaction_count = max(1, len(positive_months))
    average_transaction = _safe_average(focus_total, transaction_count)
    change_pct = _percentage_change(focus_total, previous_total)
    top_category = "Miscellaneous"
    if category_totals:
        top_category = max(category_totals.items(), key=lambda item: float(item[1]))[0]

    feature_row = {
        "transaction_count": transaction_count,
        "average_transaction": float(_to_money(average_transaction)),
        "change_from_previous_pct": float(_to_money(change_pct or ZERO)),
        "top_category": top_category,
        "top_merchant": payload.get("topMerchant", "Unknown"),
    }
    return pd.DataFrame([feature_row], columns=FEATURE_COLUMNS)


def model_fn(model_dir: str) -> dict[str, Any]:
    path = Path(model_dir)
    assets = {
        "preprocessor": path / "preprocessor.joblib",
        "spend_regressor": path / "spend_regressor.joblib",
        "category_classifier": path / "category_classifier.joblib",
        "anomaly_detector": path / "anomaly_detector.joblib",
        "metadata": path / "metadata.json",
    }

    if not all(asset.exists() for key, asset in assets.items() if key != "metadata"):
        return {"mode": "heuristic"}

    metadata = {}
    if assets["metadata"].exists():
        metadata = json.loads(assets["metadata"].read_text())

    return {
        "mode": "trained",
        "preprocessor": joblib.load(assets["preprocessor"]),
        "spend_regressor": joblib.load(assets["spend_regressor"]),
        "category_classifier": joblib.load(assets["category_classifier"]),
        "anomaly_detector": joblib.load(assets["anomaly_detector"]),
        "metadata": metadata,
    }


def input_fn(request_body: str, request_content_type: str) -> dict[str, Any]:
    if request_content_type != "application/json":
        raise ValueError("Only application/json is supported")
    return json.loads(request_body)


def predict_fn(input_data: dict[str, Any], model: dict[str, Any]) -> dict[str, Any]:
    if model.get("mode") != "trained":
        return _heuristic_prediction(input_data)

    feature_frame = _build_feature_frame(input_data)
    transformed = model["preprocessor"].transform(feature_frame)

    forecast_raw = float(model["spend_regressor"].predict(transformed)[0])
    forecast_amount = float(_to_money(_to_decimal(max(0.0, forecast_raw))))

    category_prediction = model["category_classifier"].predict(transformed)[0]
    category_proba = model["category_classifier"].predict_proba(transformed)[0]
    labels = list(model["category_classifier"].classes_)
    ranked = sorted(zip(labels, category_proba), key=lambda item: item[1], reverse=True)[:3]
    suggestions = [
        {
            "category": label,
            "confidence": round(float(probability), 2),
            "reason": "Predicted by the SageMaker category classifier from recent user behavior.",
        }
        for label, probability in ranked
    ]

    anomaly_score = float(-model["anomaly_detector"].score_samples(transformed)[0])
    normalized_score = max(0.0, min(0.95, round(anomaly_score, 2)))
    if normalized_score >= 0.7:
        level = "high"
    elif normalized_score >= 0.4:
        level = "medium"
    else:
        level = "low"

    return {
        "modelName": model.get("metadata", {}).get("model_name", "sagemaker-random-forest-stack"),
        "forecastAmount": forecast_amount,
        "forecastConfidence": "high" if forecast_amount > 0 else "medium",
        "predictedTopCategories": suggestions or [{
            "category": str(category_prediction),
            "confidence": 0.5,
            "reason": "Predicted by the SageMaker category classifier.",
        }],
        "anomalyRisk": {
            "level": level,
            "score": normalized_score,
            "reason": "Predicted by the SageMaker anomaly detector from recent user behavior.",
        },
    }


def output_fn(prediction: dict[str, Any], accept: str) -> str:
    return json.dumps(prediction)
