import os
from datetime import datetime, timezone
from decimal import Decimal

import boto3

from common import get_json_body, response


dynamodb = boto3.resource("dynamodb")
transactions_table = dynamodb.Table(os.environ["TRANSACTIONS_TABLE"])


def _normalize_amount(value):
    return Decimal(str(value))


def lambda_handler(event, context):
    try:
        body = get_json_body(event)
        user_id = body.get("userId")
        transactions = body.get("transactions", [])

        if not user_id:
            return response(400, {"message": "userId is required"})
        if not isinstance(transactions, list) or not transactions:
            return response(400, {"message": "transactions must be a non-empty list"})

        saved_count = 0
        with transactions_table.batch_writer() as batch:
            for txn in transactions:
                date = txn.get("date")
                transaction_id = txn.get("transactionId")
                merchant = txn.get("merchant")
                amount = txn.get("amount")
                category = txn.get("category", "Miscellaneous")
                payment_method = txn.get("paymentMethod", "Unknown")
                upload_id = txn.get("uploadId", "")

                if not all([date, transaction_id, merchant]) or amount is None:
                    continue

                item = {
                    "userId": user_id,
                    "transactionDate": f"{date}#{transaction_id}",
                    "date": date,
                    "transactionId": transaction_id,
                    "merchant": merchant,
                    "amount": _normalize_amount(amount),
                    "category": category,
                    "paymentMethod": payment_method,
                    "uploadId": upload_id,
                    "createdAt": datetime.now(timezone.utc).isoformat(),
                }
                batch.put_item(Item=item)
                saved_count += 1

        return response(201, {"message": "Transactions saved", "savedCount": saved_count})
    except Exception as error:
        return response(500, {"message": "Failed to save transactions", "error": str(error)})
