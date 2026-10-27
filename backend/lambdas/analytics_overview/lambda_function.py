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


def _month_key(value: date) -> str:
    return value.strftime("%Y-%m")


def _last_day_of_month(value: date) -> date:
    return _shift_month(value, 1) - timedelta(days=1)


def _to_money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _to_percent(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def _safe_average(total: Decimal, count: int) -> Decimal:
    if count <= 0:
        return ZERO
    return total / Decimal(str(count))


def _calculate_prediction(monthly_totals):
    recent = [total for total in monthly_totals if total > ZERO][-3:]
    if not recent:
        return ZERO
    if len(recent) == 1:
        return recent[0]
    if len(recent) == 2:
        return (recent[1] * Decimal("0.65")) + (recent[0] * Decimal("0.35"))
    return (
        (recent[2] * Decimal("0.50"))
        + (recent[1] * Decimal("0.30"))
        + (recent[0] * Decimal("0.20"))
    )


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


def _month_bucket():
    return {
        "total": ZERO,
        "count": 0,
        "categories": defaultdict(lambda: {"amount": ZERO, "count": 0}),
        "merchants": defaultdict(lambda: {"amount": ZERO, "count": 0}),
        "daily": defaultdict(lambda: ZERO),
        "transactions": [],
    }


def _anomaly_candidates(focus_transactions, historical_category_avgs, historical_global_avg):
    candidates = []
    baseline = historical_global_avg if historical_global_avg > ZERO else Decimal("35")

    for txn in focus_transactions:
        amount = txn["amount"]
        category_avg = historical_category_avgs.get(txn["category"], baseline)
        threshold = max(category_avg * Decimal("1.8"), baseline * Decimal("2.2"), Decimal("75"))
        if amount < threshold:
            continue

        multiple = amount / (category_avg if category_avg > ZERO else baseline)
        candidates.append({
            "transactionId": txn["transactionId"],
            "date": txn["date"],
            "merchant": txn["merchant"],
            "category": txn["category"],
            "amount": _to_money(amount),
            "reason": f"{multiple.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)}x higher than your usual {txn['category'].lower()} spend",
        })

    candidates.sort(key=lambda item: item["amount"], reverse=True)
    return candidates[:3]


def _build_alerts(current_total, previous_total, top_category, top_category_share, anomalies):
    alerts = []
    change = _percentage_change(current_total, previous_total)

    if change is not None and change >= Decimal("20"):
        alerts.append({
            "type": "spending-increase",
            "severity": "warning",
            "title": "Monthly spending is trending up",
            "message": f"You are up {_to_percent(change)}% versus last month.",
        })

    if top_category and top_category_share >= Decimal("45"):
        alerts.append({
            "type": "category-concentration",
            "severity": "info",
            "title": f"{top_category} is dominating this month",
            "message": f"{top_category} accounts for {_to_percent(top_category_share)}% of total spend.",
        })

    if anomalies:
        alerts.append({
            "type": "anomaly-candidate",
            "severity": "critical",
            "title": "Unusual transactions detected",
            "message": f"{len(anomalies)} transactions are significantly above your normal spend pattern.",
        })

    return alerts


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
    statements = [
        """
        CREATE TABLE IF NOT EXISTS reporting_monthly_summary (
            user_id VARCHAR(128) NOT NULL,
            month_key CHAR(7) NOT NULL,
            total_spent DECIMAL(12, 2) NOT NULL,
            transaction_count INT NOT NULL,
            average_transaction DECIMAL(12, 2) NOT NULL,
            top_category VARCHAR(255) NULL,
            top_merchant VARCHAR(255) NULL,
            predicted_next_month_spend DECIMAL(12, 2) NULL,
            previous_month_total_spent DECIMAL(12, 2) NULL,
            change_from_previous_pct DECIMAL(8, 2) NULL,
            refreshed_at DATETIME NOT NULL,
            PRIMARY KEY (user_id, month_key)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS reporting_category_summary (
            user_id VARCHAR(128) NOT NULL,
            month_key CHAR(7) NOT NULL,
            category VARCHAR(255) NOT NULL,
            total_spent DECIMAL(12, 2) NOT NULL,
            transaction_count INT NOT NULL,
            average_amount DECIMAL(12, 2) NOT NULL,
            share_pct DECIMAL(8, 2) NOT NULL,
            refreshed_at DATETIME NOT NULL,
            PRIMARY KEY (user_id, month_key, category)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS reporting_merchant_summary (
            user_id VARCHAR(128) NOT NULL,
            month_key CHAR(7) NOT NULL,
            merchant VARCHAR(255) NOT NULL,
            total_spent DECIMAL(12, 2) NOT NULL,
            transaction_count INT NOT NULL,
            refreshed_at DATETIME NOT NULL,
            PRIMARY KEY (user_id, month_key, merchant)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS reporting_daily_spend (
            user_id VARCHAR(128) NOT NULL,
            spend_date DATE NOT NULL,
            month_key CHAR(7) NOT NULL,
            total_spent DECIMAL(12, 2) NOT NULL,
            refreshed_at DATETIME NOT NULL,
            PRIMARY KEY (user_id, spend_date)
        )
        """,
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
        """,
    ]

    with connection.cursor() as cursor:
        for statement in statements:
            cursor.execute(statement)


def _sync_reporting_store(connection, user_id, focus_month, month_keys, buckets, prediction_amount):
    if not connection:
        return {"status": "skipped", "message": "RDS reporting store not configured"}

    refreshed_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    previous_month_key = month_keys[-2] if len(month_keys) > 1 else None
    range_start = month_keys[0]
    range_end = month_keys[-1]
    date_start = f"{range_start}-01"
    date_end = _last_day_of_month(_parse_month(range_end)).isoformat()

    _ensure_schema(connection)

    monthly_rows = []
    category_rows = []
    merchant_rows = []
    daily_rows = []

    for month in month_keys:
        bucket = buckets[month]
        sorted_categories = sorted(bucket["categories"].items(), key=lambda item: item[1]["amount"], reverse=True)
        sorted_merchants = sorted(bucket["merchants"].items(), key=lambda item: item[1]["amount"], reverse=True)
        previous_total = buckets[previous_month_key]["total"] if previous_month_key and month == focus_month else None
        change_pct = _percentage_change(bucket["total"], previous_total)

        monthly_rows.append((
            user_id,
            month,
            float(_to_money(bucket["total"])),
            bucket["count"],
            float(_to_money(_safe_average(bucket["total"], bucket["count"]))),
            sorted_categories[0][0] if sorted_categories else None,
            sorted_merchants[0][0] if sorted_merchants else None,
            float(_to_money(prediction_amount)) if month == focus_month else None,
            float(_to_money(previous_total)) if previous_total is not None else None,
            float(_to_percent(change_pct)) if change_pct is not None else None,
            refreshed_at,
        ))

        for category, stats in bucket["categories"].items():
            share = (stats["amount"] / bucket["total"] * HUNDRED) if bucket["total"] > ZERO else ZERO
            category_rows.append((
                user_id,
                month,
                category,
                float(_to_money(stats["amount"])),
                stats["count"],
                float(_to_money(_safe_average(stats["amount"], stats["count"]))),
                float(_to_percent(share)),
                refreshed_at,
            ))

        for merchant, stats in bucket["merchants"].items():
            merchant_rows.append((
                user_id,
                month,
                merchant,
                float(_to_money(stats["amount"])),
                stats["count"],
                refreshed_at,
            ))

        for spend_date, total in bucket["daily"].items():
            daily_rows.append((
                user_id,
                spend_date,
                month,
                float(_to_money(total)),
                refreshed_at,
            ))

    with connection.cursor() as cursor:
        cursor.execute(
            "DELETE FROM reporting_category_summary WHERE user_id = %s AND month_key BETWEEN %s AND %s",
            (user_id, range_start, range_end),
        )
        cursor.execute(
            "DELETE FROM reporting_merchant_summary WHERE user_id = %s AND month_key BETWEEN %s AND %s",
            (user_id, range_start, range_end),
        )
        cursor.execute(
            "DELETE FROM reporting_daily_spend WHERE user_id = %s AND spend_date BETWEEN %s AND %s",
            (user_id, date_start, date_end),
        )

        cursor.executemany(
            """
            INSERT INTO reporting_monthly_summary (
                user_id, month_key, total_spent, transaction_count, average_transaction,
                top_category, top_merchant, predicted_next_month_spend,
                previous_month_total_spent, change_from_previous_pct, refreshed_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                total_spent = VALUES(total_spent),
                transaction_count = VALUES(transaction_count),
                average_transaction = VALUES(average_transaction),
                top_category = VALUES(top_category),
                top_merchant = VALUES(top_merchant),
                predicted_next_month_spend = VALUES(predicted_next_month_spend),
                previous_month_total_spent = VALUES(previous_month_total_spent),
                change_from_previous_pct = VALUES(change_from_previous_pct),
                refreshed_at = VALUES(refreshed_at)
            """,
            monthly_rows,
        )

        if category_rows:
            cursor.executemany(
                """
                INSERT INTO reporting_category_summary (
                    user_id, month_key, category, total_spent,
                    transaction_count, average_amount, share_pct, refreshed_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                category_rows,
            )

        if merchant_rows:
            cursor.executemany(
                """
                INSERT INTO reporting_merchant_summary (
                    user_id, month_key, merchant, total_spent, transaction_count, refreshed_at
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                merchant_rows,
            )

        if daily_rows:
            cursor.executemany(
                """
                INSERT INTO reporting_daily_spend (
                    user_id, spend_date, month_key, total_spent, refreshed_at
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                daily_rows,
            )

    return {"status": "synced", "database": "rds-mysql", "monthsSynced": len(month_keys)}


def lambda_handler(event, context):
    connection = None
    try:
        path_params = event.get("pathParameters") or {}
        query_params = event.get("queryStringParameters") or {}
        user_id = path_params.get("userId")
        focus_month = query_params.get("month")
        history_months_raw = query_params.get("months", "6")

        if not user_id or not focus_month:
            return response(400, {"message": "userId path parameter and month query parameter are required"})

        try:
            history_months = int(history_months_raw)
        except (TypeError, ValueError):
            return response(400, {"message": "months query parameter must be a number"})

        if history_months < 2 or history_months > 12:
            return response(400, {"message": "months query parameter must be between 2 and 12"})

        focus_date = _parse_month(focus_month)
        start_month = _shift_month(focus_date, -(history_months - 1))
        month_keys = [_month_key(_shift_month(start_month, i)) for i in range(history_months)]
        buckets = {month: _month_bucket() for month in month_keys}

        items = _query_transactions(user_id, start_month, focus_date)

        historical_total = ZERO
        historical_count = 0
        historical_category_totals = defaultdict(lambda: {"amount": ZERO, "count": 0})

        for item in items:
            amount = item.get("amount", ZERO)
            month = item.get("date", "")[:7]
            if month not in buckets:
                continue

            merchant = item.get("merchant", "Unknown merchant")
            category = item.get("category", "Miscellaneous")
            bucket = buckets[month]
            bucket["total"] += amount
            bucket["count"] += 1
            bucket["categories"][category]["amount"] += amount
            bucket["categories"][category]["count"] += 1
            bucket["merchants"][merchant]["amount"] += amount
            bucket["merchants"][merchant]["count"] += 1
            bucket["daily"][item["date"]] += amount
            bucket["transactions"].append({
                "transactionId": item.get("transactionId"),
                "date": item.get("date"),
                "merchant": merchant,
                "category": category,
                "amount": amount,
            })

            if month != focus_month:
                historical_total += amount
                historical_count += 1
                historical_category_totals[category]["amount"] += amount
                historical_category_totals[category]["count"] += 1

        focus_bucket = buckets[focus_month]
        previous_month_key = month_keys[-2] if len(month_keys) > 1 else None
        previous_bucket = buckets.get(previous_month_key) if previous_month_key else None

        category_breakdown = []
        for category, stats in focus_bucket["categories"].items():
            share = (stats["amount"] / focus_bucket["total"] * HUNDRED) if focus_bucket["total"] > ZERO else ZERO
            category_breakdown.append({
                "category": category,
                "amount": _to_money(stats["amount"]),
                "transactionCount": stats["count"],
                "averageAmount": _to_money(_safe_average(stats["amount"], stats["count"])),
                "share": _to_percent(share),
            })
        category_breakdown.sort(key=lambda item: item["amount"], reverse=True)

        top_merchants = [
            {
                "merchant": merchant,
                "amount": _to_money(stats["amount"]),
                "transactionCount": stats["count"],
            }
            for merchant, stats in focus_bucket["merchants"].items()
        ]
        top_merchants.sort(key=lambda item: item["amount"], reverse=True)
        top_merchants = top_merchants[:5]

        monthly_trend = []
        for month in month_keys:
            month_bucket = buckets[month]
            top_category = None
            if month_bucket["categories"]:
                top_category = max(
                    month_bucket["categories"].items(),
                    key=lambda item: item[1]["amount"],
                )[0]

            monthly_trend.append({
                "month": month,
                "totalSpent": _to_money(month_bucket["total"]),
                "transactionCount": month_bucket["count"],
                "averageTransaction": _to_money(_safe_average(month_bucket["total"], month_bucket["count"])),
                "topCategory": top_category,
            })

        daily_spend = [
            {"date": day, "amount": _to_money(amount)}
            for day, amount in sorted(focus_bucket["daily"].items())
        ]

        top_category = category_breakdown[0]["category"] if category_breakdown else None
        top_category_share = Decimal(str(category_breakdown[0]["share"])) if category_breakdown else ZERO
        largest_transaction = None
        if focus_bucket["transactions"]:
            largest = max(focus_bucket["transactions"], key=lambda item: item["amount"])
            largest_transaction = {
                "transactionId": largest["transactionId"],
                "date": largest["date"],
                "merchant": largest["merchant"],
                "category": largest["category"],
                "amount": _to_money(largest["amount"]),
            }

        historical_category_avgs = {
            category: _safe_average(stats["amount"], stats["count"])
            for category, stats in historical_category_totals.items()
        }
        historical_global_avg = _safe_average(historical_total, historical_count)
        anomalies = _anomaly_candidates(
            focus_bucket["transactions"],
            historical_category_avgs,
            historical_global_avg,
        )

        previous_total = previous_bucket["total"] if previous_bucket else None
        change_pct = _percentage_change(focus_bucket["total"], previous_total)
        prediction = _calculate_prediction([bucket["total"] for bucket in buckets.values()])
        alerts = _build_alerts(focus_bucket["total"], previous_total, top_category, top_category_share, anomalies)

        reporting_store = {"status": "unavailable"}
        try:
            connection = _get_db_connection()
            reporting_store = _sync_reporting_store(connection, user_id, focus_month, month_keys, buckets, prediction)
        except Exception as store_error:
            reporting_store = {"status": "failed", "message": str(store_error)}

        return response(200, {
            "userId": user_id,
            "focusMonth": focus_month,
            "historyStartMonth": month_keys[0],
            "monthsAnalyzed": history_months,
            "totals": {
                "totalSpent": _to_money(focus_bucket["total"]),
                "transactionCount": focus_bucket["count"],
                "averageTransaction": _to_money(_safe_average(focus_bucket["total"], focus_bucket["count"])),
                "topCategory": top_category,
                "topMerchant": top_merchants[0]["merchant"] if top_merchants else None,
                "largestTransaction": largest_transaction,
                "previousMonthTotalSpent": _to_money(previous_total) if previous_total is not None else None,
                "changeFromPreviousMonthPct": _to_percent(change_pct) if change_pct is not None else None,
                "predictedNextMonthSpend": _to_money(prediction),
            },
            "monthlyTrend": monthly_trend,
            "dailySpend": daily_spend,
            "categoryBreakdown": category_breakdown,
            "topMerchants": top_merchants,
            "anomalyCandidates": anomalies,
            "alerts": alerts,
            "reportingStore": reporting_store,
            "modelInfo": {
                "name": "baseline-moving-average-v1",
                "description": "Dashboard metrics are stored in RDS for reporting and QuickSight. This heuristic forecast can be replaced by a SageMaker endpoint later.",
            },
        })
    except ValueError:
        return response(400, {"message": "month query parameter must use YYYY-MM format"})
    except Exception as error:
        return response(500, {"message": "Failed to build analytics overview", "error": str(error)})
    finally:
        if connection:
            connection.close()
