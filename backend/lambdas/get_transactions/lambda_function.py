import os

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
        start_date = query_params.get("startDate", "0000-01-01")
        end_date = query_params.get("endDate", "9999-12-31")
        upload_id = query_params.get("uploadId")

        if not user_id:
            return response(400, {"message": "userId path parameter is required"})

        result = transactions_table.query(
            KeyConditionExpression=Key("userId").eq(user_id) & Key("transactionDate").between(
                f"{start_date}#", f"{end_date}#zzzzzz"
            ),
            ScanIndexForward=False,
        )

        items = result.get("Items", [])
        if upload_id:
            items = [item for item in items if item.get("uploadId") == upload_id]
        return response(200, {"transactions": items, "count": len(items)})
    except Exception as error:
        return response(500, {"message": "Failed to fetch transactions", "error": str(error)})
