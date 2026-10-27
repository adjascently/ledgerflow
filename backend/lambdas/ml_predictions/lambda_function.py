import json
import os
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

import boto3
from boto3.dynamodb.conditions import Key
import pymysql

from common import response


dynamodb = boto3.resource("dynamodb")
secretsmanager = boto3.client("secretsmanager")
sagemaker_runtime = boto3.client("sagemaker-runtime")
transactions_table = dynamodb.Table(os.environ["TRANSACTIONS_TABLE"])

ZERO = Decimal("0")
HUNDRED = Decimal("100")


def _parse_month(value: str) -> date:
    return datetime.strptime(value, "%Y-%m").date().replace(day=1)


def _shift_month(base: date, offset: int) -> date:
    month_index = (base.year * 12 + (base.month - 1)) + offset
    year = month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)


def _last_day_of_month(value: date) -> date:
    return _shift_month(value, 1) - timedelta(days=1)


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


def _query_transactions(user_id: str, start_month: date, end_month: date):
    items = []
    start_key = f"{start_month.isoformat()}#"
    end_key = f"{_last_day_of_month(end_month).isoformat()}#zzzzzz"
    last_evaluated_key = None

    while True:
        query_args = {
            "KeyConditionExpression": Key("userId").eq(user_id) & Key("transactionDate").between(start_key, end_key)
        }
        if last_evaluated_key:
            query_args["ExclusiveStartKey"] = last_evaluated_key

        result = transactions_table.query(**query_args)
        items.extend(result.get("Items", []))
        last_evaluated_key = result.get("LastEvaluatedKey")
        if not last_evaluated_key:
            return items


def _get_db_connection():
    secret_arn = os.getenv("REPORTING_DB_SECRET_ARN")
    host = os.getenv("REPORTING_DB_HOST")
    database_name = os.getenv("REPORTING_DB_NAME", "finance_reporting")
    if not secret_arn or not host:
        return None

    secret = secretsmanager.get_secret_value(SecretId=secret_arn)
    payload = json.loads(secret["SecretString"])
    return pymysql.connect(
        host=host,
        user=payload["username"],
        password=payload["password"],
        database=database_name,
        port=int(payload.get("port", 3306)),
        connect_timeout=5,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def _ensure_schema(connection):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS prediction_snapshots (
                user_id VARCHAR(128) NOT NULL,
                month_key CHAR(7) NOT NULL,
                model_name VARCHAR(255) NOT NULL,
                forecast_amount DECIMAL(12, 2) NOT NULL,
                anomaly_risk_level VARCHAR(32) NOT NULL,
                anomaly_risk_score DECIMAL(5, 2) NOT NULL,
                suggestions_json TEXT NOT NULL,
                source VARCHAR(32) NOT NULL,
                refreshed_at DATETIME NOT NULL,
                PRIMARY KEY (user_id, month_key)
            )
            """
        )


def _get_model_config():
    secret_arn = os.getenv("ML_CONFIG_SECRET_ARN")
    if not secret_arn:
        return {}

    secret = secretsmanager.get_secret_value(SecretId=secret_arn)
    return json.loads(secret["SecretString"])


def _local_prediction(monthly_totals, category_amounts, focus_total, previous_total, anomaly_count):
    recent = [total for total in monthly_totals if total > ZERO][-3:]
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
        "source": "heuristic",
        "modelName": "baseline-ml-fallback-v1",
        "forecastAmount": _to_money(forecast),
        "forecastConfidence": confidence,
        "predictedTopCategories": category_suggestions,
        "anomalyRisk": {
            "level": level,
            "score": float(anomaly_score.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            "reason": "Derived from month-over-month changes and unusually large transactions.",
        },
    }


def _invoke_sagemaker(config, payload, fallback_result):
    endpoint_name = config.get("sagemakerEndpointName") or os.getenv("SAGEMAKER_ENDPOINT_NAME")
    if not endpoint_name:
        return fallback_result

    try:
        response_payload = sagemaker_runtime.invoke_endpoint(
            EndpointName=endpoint_name,
            ContentType="application/json",
            Body=json.dumps(payload).encode("utf-8"),
        )
        body = response_payload["Body"].read().decode("utf-8")
        parsed = json.loads(body)
        return {
            "source": "sagemaker",
            "modelName": parsed.get("modelName", endpoint_name),
            "forecastAmount": Decimal(str(parsed.get("forecastAmount", fallback_result["forecastAmount"]))),
            "forecastConfidence": parsed.get("forecastConfidence", fallback_result["forecastConfidence"]),
            "predictedTopCategories": parsed.get("predictedTopCategories", fallback_result["predictedTopCategories"]),
            "anomalyRisk": parsed.get("anomalyRisk", fallback_result["anomalyRisk"]),
        }
    except Exception:
        return fallback_result


def _store_prediction_snapshot(connection, user_id, month, prediction):
    if not connection:
        return {"status": "skipped"}

    _ensure_schema(connection)
    refreshed_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO prediction_snapshots (
                user_id, month_key, model_name, forecast_amount,
                anomaly_risk_level, anomaly_risk_score, suggestions_json, source, refreshed_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                model_name = VALUES(model_name),
                forecast_amount = VALUES(forecast_amount),
                anomaly_risk_level = VALUES(anomaly_risk_level),
                anomaly_risk_score = VALUES(anomaly_risk_score),
                suggestions_json = VALUES(suggestions_json),
                source = VALUES(source),
                refreshed_at = VALUES(refreshed_at)
            """,
            (
                user_id,
                month,
                prediction["modelName"],
                float(_to_money(Decimal(str(prediction["forecastAmount"])))),
                prediction["anomalyRisk"]["level"],
                float(Decimal(str(prediction["anomalyRisk"]["score"])).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
                json.dumps(prediction["predictedTopCategories"]),
                prediction["source"],
                refreshed_at,
            ),
        )
    return {"status": "stored", "database": "rds-mysql"}


def lambda_handler(event, context):
    connection = None
    try:
        path_params = event.get("pathParameters") or {}
        query_params = event.get("queryStringParameters") or {}
        user_id = path_params.get("userId")
        focus_month = query_params.get("month")
        history_months = int(query_params.get("months", "6"))

        if not user_id or not focus_month:
            return response(400, {"message": "userId path parameter and month query parameter are required"})
        if history_months < 2 or history_months > 12:
            return response(400, {"message": "months query parameter must be between 2 and 12"})

        focus_date = _parse_month(focus_month)
        start_month = _shift_month(focus_date, -(history_months - 1))
        items = _query_transactions(user_id, start_month, focus_date)

        populated_months = {
            item.get("date", "")[:7]
            for item in items
            if item.get("date")
        }
        focus_month_transactions = [
            item
            for item in items
            if item.get("date", "")[:7] == focus_month
        ]

        if not focus_month_transactions or len(populated_months) < 2:
            return response(200, {
                "userId": user_id,
                "focusMonth": focus_month,
                "prediction": None,
                "recommendedActions": [],
                "predictionStore": {
                    "status": "skipped",
                    "message": "Not enough transaction history for prediction.",
                },
            })

        monthly_totals = defaultdict(lambda: ZERO)
        category_amounts = defaultdict(lambda: ZERO)
        focus_total = ZERO
        previous_total = None
        anomaly_count = 0
        historical_category_averages = defaultdict(list)

        for item in items:
            transaction_date = item.get("date", "")
            month = transaction_date[:7]
            amount = item.get("amount", ZERO)
            category = item.get("category", "Miscellaneous")
            monthly_totals[month] += amount
            category_amounts[category] += amount
            historical_category_averages[category].append(amount)
            if month == focus_month:
                focus_total += amount

        previous_key = _shift_month(focus_date, -1).strftime("%Y-%m")
        if previous_key in monthly_totals:
            previous_total = monthly_totals[previous_key]

        global_avg = _safe_average(sum(monthly_totals.values(), ZERO), len(items))
        for item in items:
            if item.get("date", "")[:7] != focus_month:
                continue
            amount = item.get("amount", ZERO)
            category = item.get("category", "Miscellaneous")
            category_history = historical_category_averages.get(category, [])
            category_avg = _safe_average(sum(category_history, ZERO), len(category_history))
            threshold = max(global_avg * Decimal("2.2"), category_avg * Decimal("1.8"), Decimal("75"))
            if amount >= threshold:
                anomaly_count += 1

        ordered_months = [
            monthly_totals[_shift_month(start_month, offset).strftime("%Y-%m")]
            for offset in range(history_months)
        ]
        fallback_result = _local_prediction(
            ordered_months,
            category_amounts,
            focus_total,
            previous_total,
            anomaly_count,
        )

        payload = {
            "userId": user_id,
            "focusMonth": focus_month,
            "monthlyTotals": [float(value) for value in ordered_months],
            "categoryTotals": {category: float(amount) for category, amount in category_amounts.items()},
            "focusMonthTotal": float(focus_total),
            "previousMonthTotal": float(previous_total or ZERO),
            "anomalyCount": anomaly_count,
        }
        config = _get_model_config()
        prediction = _invoke_sagemaker(config, payload, fallback_result)

        recommended_actions = [
            "Refresh the web dashboard after new statement uploads so the analytics APIs and reporting tables stay current.",
            "Review high-value or unusual transactions before the month closes.",
        ]
        if prediction["anomalyRisk"]["level"] == "high":
            recommended_actions.insert(0, "Set or tighten a spending alert threshold for the most active categories.")

        prediction["forecastAmount"] = _to_money(Decimal(str(prediction["forecastAmount"])))

        prediction_store = {"status": "unavailable"}
        try:
            connection = _get_db_connection()
            prediction_store = _store_prediction_snapshot(connection, user_id, focus_month, prediction)
        except Exception as store_error:
            prediction_store = {"status": "failed", "message": str(store_error)}

        return response(200, {
            "userId": user_id,
            "focusMonth": focus_month,
            "prediction": prediction,
            "recommendedActions": recommended_actions,
            "predictionStore": prediction_store,
        })
    except ValueError:
        return response(400, {"message": "month query parameter must use YYYY-MM format and months must be numeric"})
    except Exception as error:
        return response(500, {"message": "Failed to generate predictions", "error": str(error)})
    finally:
        if connection:
            connection.close()
