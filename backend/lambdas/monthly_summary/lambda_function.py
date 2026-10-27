import os
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

from common import response


dynamodb = boto3.resource("dynamodb")
transactions_table = dynamodb.Table(os.environ["TRANSACTIONS_TABLE"])


def lambda_handler(event, context):
    try:
        path_params = event.get("pathParameters") or {}
        query_params = event.get("queryStringParameters") or {}
        user_id = path_params.get("userId")
        month = query_params.get("month")
        upload_id = query_params.get("uploadId")

        if not user_id or not month:
            return response(400, {"message": "userId path parameter and month query parameter are required"})

        start_date = f"{month}-01"
        end_date = f"{month}-31"

        result = transactions_table.query(
            KeyConditionExpression=Key("userId").eq(user_id) & Key("transactionDate").between(
                f"{start_date}#", f"{end_date}#zzzzzz"
            )
        )
        items = result.get("Items", [])
        if upload_id:
            items = [item for item in items if item.get("uploadId") == upload_id]

        total = Decimal("0")
        category_totals = {}
        for item in items:
            amount = item["amount"]
            category = item.get("category", "Miscellaneous")
            if amount < 0:
                spent = abs(amount)
                total += spent
                category_totals[category] = category_totals.get(category, Decimal("0")) + spent

        top_category = max(category_totals, key=category_totals.get) if category_totals else None

        return response(200, {
            "userId": user_id,
            "month": month,
            "uploadId": upload_id,
            "transactionCount": len(items),
            "totalSpent": total,
            "topCategory": top_category,
            "categories": category_totals,
        })
    except Exception as error:
        return response(500, {"message": "Failed to build monthly summary", "error": str(error)})
