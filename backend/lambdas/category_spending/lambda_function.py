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

        result = transactions_table.query(
            KeyConditionExpression=Key("userId").eq(user_id) & Key("transactionDate").between(
                f"{month}-01#", f"{month}-31#zzzzzz"
            )
        )
        items = result.get("Items", [])
        if upload_id:
            items = [item for item in items if item.get("uploadId") == upload_id]

        category_totals = {}
        for item in items:
            category = item.get("category", "Miscellaneous")
            amount = item.get("amount", Decimal("0"))
            if amount < 0:
                category_totals[category] = category_totals.get(category, Decimal("0")) + abs(amount)

        formatted = [
            {"category": category, "amount": amount}
            for category, amount in sorted(category_totals.items(), key=lambda x: x[0])
        ]

        return response(200, {"userId": user_id, "month": month, "uploadId": upload_id, "categories": formatted})
    except Exception as error:
        return response(500, {"message": "Failed to compute category spending", "error": str(error)})
