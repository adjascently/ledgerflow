import json
import os
import csv
import io
import re
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List

import boto3
from pypdf import PdfReader

sns = boto3.client("sns")
s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")

SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN", "")
DEFAULT_THRESHOLD = float(os.environ.get("DEFAULT_THRESHOLD", "1000"))
TRANSACTIONS_TABLE = os.environ.get("TRANSACTIONS_TABLE", "")
UPLOADS_TABLE = os.environ.get("UPLOADS_TABLE", "")
USERS_TABLE = os.environ.get("USERS_TABLE", "")
transactions_table = dynamodb.Table(TRANSACTIONS_TABLE) if TRANSACTIONS_TABLE else None
uploads_table = dynamodb.Table(UPLOADS_TABLE) if UPLOADS_TABLE else None
users_table = dynamodb.Table(USERS_TABLE) if USERS_TABLE else None
AMOUNT_TOKEN = re.compile(r"\(?-?\$?\d[\d,]*\.\d{2}\)?")


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _build_summary(transactions: List[Dict[str, Any]]) -> Dict[str, float]:
    category_totals: Dict[str, float] = {}

    for txn in transactions:
        amount = _safe_float(txn.get("amount", 0))
        if amount >= 0:
            continue
        category = txn.get("category", "Miscellaneous")
        category_totals[category] = category_totals.get(category, 0.0) + abs(amount)

    return category_totals


def _publish_sns(subject: str, message: Dict[str, Any]) -> None:
    if not SNS_TOPIC_ARN:
        print("SNS_TOPIC_ARN not configured. Skipping SNS publish.")
        return

    sns.publish(
        TopicArn=SNS_TOPIC_ARN,
        Subject=subject,
        Message=json.dumps(message, indent=2, default=str),
    )


def _user_topic_name(user_id: str) -> str:
    safe_suffix = re.sub(r"[^A-Za-z0-9_-]", "-", user_id)[:80]
    return f"finance-tracker-user-alert-{safe_suffix}"


def _get_user_profile(user_id: str) -> Dict[str, Any]:
    if not users_table or not user_id or user_id == "unknown-user":
        return {}
    result = users_table.get_item(Key={"userId": user_id})
    return result.get("Item") or {}


def _ensure_user_alert_topic(user_id: str) -> str:
    user = _get_user_profile(user_id)
    topic_arn = user.get("alertTopicArn")
    if topic_arn:
        return topic_arn

    email = user.get("email")
    if not email:
        return ""

    topic = sns.create_topic(Name=_user_topic_name(user_id))
    topic_arn = topic["TopicArn"]
    subscription = sns.subscribe(
        TopicArn=topic_arn,
        Protocol="email",
        Endpoint=email,
        ReturnSubscriptionArn=True,
    )

    if users_table:
        users_table.update_item(
            Key={"userId": user_id},
            UpdateExpression="SET alertTopicArn = :topicArn, alertSubscriptionArn = :subscriptionArn",
            ExpressionAttributeValues={
                ":topicArn": topic_arn,
                ":subscriptionArn": subscription.get("SubscriptionArn", "PendingConfirmation"),
            },
        )

    return topic_arn


def _publish_user_notification(user_id: str, subject: str, message: Dict[str, Any]) -> None:
    topic_arn = _ensure_user_alert_topic(user_id)
    if topic_arn:
        sns.publish(
            TopicArn=topic_arn,
            Subject=subject,
            Message=json.dumps(message, indent=2, default=str),
        )
        return
    _publish_sns(subject, message)


def _get_mock_transactions() -> List[Dict[str, Any]]:
    return [
        {"transactionId": "txn-001", "date": "2026-04-01", "merchant": "Trader Joe's", "amount": 48.12, "category": "Groceries", "paymentMethod": "Credit Card"},
        {"transactionId": "txn-002", "date": "2026-04-02", "merchant": "Uber", "amount": 22.50, "category": "Transport", "paymentMethod": "Credit Card"},
        {"transactionId": "txn-003", "date": "2026-04-03", "merchant": "Target", "amount": 120.00, "category": "Shopping", "paymentMethod": "Debit Card"},
        {"transactionId": "txn-004", "date": "2026-04-04", "merchant": "Airbnb", "amount": 950.00, "category": "Travel", "paymentMethod": "Credit Card"}
    ]


def _normalize_event(event: Any) -> Dict[str, Any]:
    if isinstance(event, dict):
        return event

    if isinstance(event, str):
        try:
            parsed = json.loads(event)
        except json.JSONDecodeError:
            return {"rawEvent": event}
        if isinstance(parsed, dict):
            return parsed
        return {"rawEvent": parsed}

    return {"rawEvent": event}


def _parse_key_context(file_key: str) -> tuple[str, str]:
    match = re.match(r"^statements/([^/]+)/([^/.]+)", file_key or "")
    if not match:
        return "unknown-user", "unknown-upload"
    return match.group(1), match.group(2)


def _clean_amount(value: str) -> float:
    normalized = value.strip().replace("$", "").replace(",", "")
    if normalized.startswith("(") and normalized.endswith(")"):
        normalized = f"-{normalized[1:-1]}"
    return float(Decimal(normalized))


def _normalize_date(value: str) -> str:
    raw = value.strip()
    now = datetime.utcnow()
    formats = [
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%m/%d/%y",
        "%m-%d-%Y",
        "%m-%d-%y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue

    if re.fullmatch(r"\d{2}/\d{2}", raw):
        inferred = datetime.strptime(f"{raw}/{now.year}", "%m/%d/%Y")
        # Statements often omit the year. If the inferred date lands far in the future
        # relative to when the file is processed, treat it as the previous calendar year.
        if inferred.date() > (now.date() + timedelta(days=45)):
            inferred = inferred.replace(year=inferred.year - 1)
        return inferred.date().isoformat()

    return raw


def _infer_category(merchant: str) -> str:
    merchant_lower = " ".join(merchant.lower().split())
    rules = [
        (
            "Income",
            [
                "payment from",
                "transfer from",
                "online transfer from",
                "deposit",
                "refund",
                "interest payment",
                "incoming wire",
                "zelle payment from",
            ],
        ),
        (
            "Transfers",
            [
                "payment to",
                "transfer to",
                "online transfer to",
                "zelle payment to",
                "venmo",
                "paypal transfer",
            ],
        ),
        (
            "Housing",
            [
                "rent",
                "bilt payment",
                "modera",
                "biltrent",
            ],
        ),
        (
            "Fees",
            [
                "fee",
                "wire fee",
                "incoming wire fee",
                "late fee",
                "service fee",
            ],
        ),
        (
            "Groceries",
            [
                "trader joe",
                "whole foods",
                "safeway",
                "kroger",
                "aldi",
                "costco",
                "instacart",
                "grocery",
            ],
        ),
        (
            "Dining",
            [
                "restaurant",
                "cafe",
                "coffee",
                "doordash",
                "uber eats",
                "grubhub",
                "starbucks",
                "gelato",
                "pizza",
                "urban momo",
                "dumont",
                "popeyes",
            ],
        ),
        (
            "Transport",
            [
                "uber",
                "lyft",
                "shell",
                "chevron",
                "exxon",
                "transit",
                "metro",
                "parking",
                "clipper",
                "7-eleven",
            ],
        ),
        (
            "Entertainment",
            [
                "cinemark",
                "movie",
                "theater",
                "concert",
                "ticketmaster",
            ],
        ),
        (
            "Travel",
            [
                "airbnb",
                "hotel",
                "airline",
                "delta",
                "united",
                "southwest",
                "booking",
                "flywire",
            ],
        ),
        (
            "Shopping",
            [
                "amazon",
                "target",
                "walmart",
                "best buy",
                "macys",
                "nike",
                "old navy",
                "calvin klein",
                "coach",
                "world market",
                "rihoas",
                "paypal *old navy",
                "paypal *rihoas",
            ],
        ),
        (
            "Utilities",
            [
                "comcast",
                "pg&e",
                "verizon",
                "at&t",
                "water",
                "electric",
                "internet",
                "wireless",
            ],
        ),
    ]
    for category, keywords in rules:
        if any(keyword in merchant_lower for keyword in keywords):
            return category
    return "Miscellaneous"


def _infer_amount_sign(merchant: str, amount: float) -> float:
    if amount < 0:
        return amount

    merchant_lower = merchant.lower()

    credit_markers = [
        "payment from",
        "transfer from",
        "online transfer from",
        "interest payment",
        "deposit",
        "refund",
        "credit",
    ]
    debit_markers = [
        "payment to",
        "transfer to",
        "online transfer to",
        "card purchase",
        "card purchase with pin",
        "rent",
        "fee",
        "bilt payment",
        "withdrawal",
        "atm",
        "venmo",
        "paypal",
        "instacart",
        "clipper",
    ]

    if any(marker in merchant_lower for marker in credit_markers):
        return amount
    if any(marker in merchant_lower for marker in debit_markers):
        return -amount

    return amount


def _csv_value(row: Dict[str, Any], *candidates: str) -> Any:
    lower_row = {str(key).strip().lower(): value for key, value in row.items()}
    for candidate in candidates:
        if candidate in lower_row and lower_row[candidate] not in (None, ""):
            return lower_row[candidate]
    return None


def _parse_csv_transactions(content: bytes, upload_id: str) -> List[Dict[str, Any]]:
    decoded = content.decode("utf-8-sig", errors="ignore")
    reader = csv.DictReader(io.StringIO(decoded))
    transactions: List[Dict[str, Any]] = []

    for index, row in enumerate(reader, start=1):
        date_value = _csv_value(row, "date", "transaction date", "posted date")
        merchant = _csv_value(row, "merchant", "description", "details", "payee")
        amount_value = _csv_value(row, "amount", "debit", "transaction amount")
        category = _csv_value(row, "category")
        payment_method = _csv_value(row, "paymentmethod", "payment method")

        if not date_value or not merchant or amount_value in (None, ""):
            continue

        try:
            amount = _clean_amount(str(amount_value))
        except (InvalidOperation, ValueError):
            continue

        transactions.append(
            {
                "transactionId": f"{upload_id}-csv-{index}",
                "date": _normalize_date(str(date_value)),
                "merchant": str(merchant).strip(),
                "amount": amount,
                "category": str(category).strip() if category else _infer_category(str(merchant)),
                "paymentMethod": str(payment_method).strip() if payment_method else "Unknown",
            }
        )

    return transactions


def _parse_pdf_transactions(content: bytes, upload_id: str) -> List[Dict[str, Any]]:
    reader = PdfReader(io.BytesIO(content))
    lines: List[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        lines.extend(part.strip() for part in text.splitlines() if part.strip())

    line_pattern = re.compile(r"^(?P<date>\d{2}[/-]\d{2}(?:[/-]\d{2,4})?|\d{4}-\d{2}-\d{2})\s+(?P<body>.+)$")

    transactions: List[Dict[str, Any]] = []
    for index, line in enumerate(lines, start=1):
        match = line_pattern.match(line)
        if not match:
            continue

        body = match.group("body").strip()
        amount_matches = list(AMOUNT_TOKEN.finditer(body))
        if not amount_matches:
            continue

        # Bank statements typically end with "transaction amount" + "running balance".
        # Use the second-to-last amount when two values are present; otherwise use the only value.
        amount_match = amount_matches[-2] if len(amount_matches) >= 2 else amount_matches[-1]
        merchant = body[:amount_match.start()].strip(" -")
        if not merchant:
            continue

        try:
            amount = _clean_amount(amount_match.group(0))
        except (InvalidOperation, ValueError):
            continue

        amount = _infer_amount_sign(merchant, amount)

        transactions.append(
            {
                "transactionId": f"{upload_id}-pdf-{index}",
                "date": _normalize_date(match.group("date")),
                "merchant": merchant,
                "amount": amount,
                "category": _infer_category(merchant),
                "paymentMethod": "Statement",
            }
        )

    return transactions


def _load_transactions_from_statement(bucket_name: str, file_key: str, upload_id: str) -> List[Dict[str, Any]]:
    obj = s3.get_object(Bucket=bucket_name, Key=file_key)
    content = obj["Body"].read()
    lower_key = file_key.lower()

    if lower_key.endswith(".csv"):
        return _parse_csv_transactions(content, upload_id)
    if lower_key.endswith(".pdf"):
        return _parse_pdf_transactions(content, upload_id)
    raise ValueError(f"Unsupported statement format for parsing: {file_key}")


def _persist_transactions(user_id: str, upload_id: str, transactions: List[Dict[str, Any]]) -> int:
    if not transactions_table:
        return 0

    saved_count = 0
    with transactions_table.batch_writer() as batch:
        for txn in transactions:
            date = txn.get("date")
            transaction_id = txn.get("transactionId")
            merchant = txn.get("merchant")
            amount = txn.get("amount")
            category = txn.get("category", "Miscellaneous")
            payment_method = txn.get("paymentMethod", "Unknown")

            if not all([date, transaction_id, merchant]) or amount is None:
                continue

            batch.put_item(
                Item={
                    "userId": user_id,
                    "transactionDate": f"{date}#{transaction_id}",
                    "date": date,
                    "transactionId": transaction_id,
                    "merchant": merchant,
                    "amount": Decimal(str(amount)),
                    "category": category,
                    "paymentMethod": payment_method,
                    "uploadId": upload_id,
                    "createdAt": datetime.utcnow().isoformat(),
                }
            )
            saved_count += 1

    return saved_count


def _update_upload_status(upload_id: str, status: str, **attributes: Any) -> None:
    if not uploads_table or not upload_id or upload_id == "unknown-upload":
        return

    update_parts = ["#status = :status", "processedAt = :processedAt"]
    expression_names = {"#status": "status"}
    expression_values = {
        ":status": status,
        ":processedAt": datetime.utcnow().isoformat(),
    }

    for key, value in attributes.items():
        if value is None:
            continue
        update_parts.append(f"{key} = :{key}")
        expression_values[f":{key}"] = value

    uploads_table.update_item(
        Key={"uploadId": upload_id},
        UpdateExpression="SET " + ", ".join(update_parts),
        ExpressionAttributeNames=expression_names,
        ExpressionAttributeValues=expression_values,
    )


def _get_user_threshold(user_id: str) -> float | None:
    item = _get_user_profile(user_id)
    threshold = item.get("spendingThreshold")
    if threshold is None:
        return None
    return _safe_float(threshold)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    event = _normalize_event(event)
    print("Received event:")
    print(json.dumps(event, indent=2))

    file_key = event.get("fileKey", "unknown-file")
    bucket_name = event.get("bucketName", "")
    derived_user_id, derived_upload_id = _parse_key_context(file_key)
    user_id = event.get("userId") or derived_user_id
    upload_id = event.get("uploadId") or derived_upload_id
    if user_id == "unknown":
        user_id = derived_user_id
    if upload_id == "auto":
        upload_id = derived_upload_id
    threshold = _safe_float(
        event.get("threshold")
        or _get_user_threshold(user_id)
        or DEFAULT_THRESHOLD
    )

    transactions = event.get("transactions")
    if not isinstance(transactions, list) or not transactions:
        if bucket_name and file_key not in ("", "unknown-file"):
            transactions = _load_transactions_from_statement(bucket_name, file_key, upload_id)
        else:
            transactions = _get_mock_transactions()

    try:
        if not transactions:
            raise ValueError(f"No transactions could be parsed from uploaded statement: {file_key}")

        total_spending = sum(
            abs(_safe_float(txn.get("amount", 0)))
            for txn in transactions
            if _safe_float(txn.get("amount", 0)) < 0
        )
        transaction_count = len(transactions)
        category_summary = _build_summary(transactions)
        threshold_exceeded = total_spending > threshold
        saved_count = _persist_transactions(user_id, upload_id, transactions)
        _update_upload_status(
            upload_id,
            "PROCESSED",
            processedFileKey=file_key,
            transactionCount=saved_count,
            userId=user_id,
        )

        result = {
            "statusCode": 200,
            "status": "SUCCESS",
            "eventType": event.get("eventType", "statement.uploaded"),
            "userId": user_id,
            "uploadId": upload_id,
            "fileKey": file_key,
            "transactionCount": transaction_count,
            "totalSpending": round(total_spending, 2),
            "threshold": threshold,
            "thresholdExceeded": threshold_exceeded,
            "categorySummary": category_summary,
            "savedCount": saved_count,
            "transactions": transactions,
        }

        if threshold_exceeded:
            _publish_user_notification(
                user_id,
                subject="Finance Tracker - Spending Threshold Exceeded",
                message={
                    "status": "ALERT",
                    "userId": user_id,
                    "uploadId": upload_id,
                    "fileKey": file_key,
                    "message": "Uploaded statement exceeded the configured spending threshold.",
                    "totalSpending": round(total_spending, 2),
                    "threshold": threshold,
                    "categorySummary": category_summary,
                },
            )
        else:
            _publish_user_notification(
                user_id,
                subject="Finance Tracker - Statement Processed Successfully",
                message={
                    "status": "SUCCESS",
                    "userId": user_id,
                    "uploadId": upload_id,
                    "fileKey": file_key,
                    "message": "Statement processed successfully.",
                    "transactionCount": transaction_count,
                    "totalSpending": round(total_spending, 2),
                    "categorySummary": category_summary,
                },
            )

        return result

    except Exception as exc:
        error_message = f"Unexpected processing error: {str(exc)}"
        print(error_message)
        _update_upload_status(
            upload_id,
            "FAILED",
            processedFileKey=file_key,
            failureReason=error_message,
            userId=user_id,
        )

        _publish_user_notification(
            user_id,
            subject="Finance Tracker - Statement Processing Failed",
            message={
                "status": "FAILED",
                "userId": user_id,
                "uploadId": upload_id,
                "fileKey": file_key,
                "reason": error_message,
            },
        )

        return {
            "statusCode": 500,
            "status": "FAILED",
            "error": error_message,
        }
