from datetime import datetime, timezone
import os
from decimal import Decimal, InvalidOperation

import boto3

from common import get_json_body, response


dynamodb = boto3.resource("dynamodb")
users_table = dynamodb.Table(os.environ["USERS_TABLE"])


def lambda_handler(event, context):
    try:
        path_params = event.get("pathParameters") or {}
        user_id = path_params.get("userId")
        body = get_json_body(event)
        threshold = body.get("spendingThreshold")

        if not user_id:
            return response(400, {"message": "userId path parameter is required"})
        if threshold is None:
            return response(400, {"message": "spendingThreshold is required"})

        try:
            threshold_value = Decimal(str(threshold))
        except (InvalidOperation, ValueError):
            return response(400, {"message": "spendingThreshold must be numeric"})

        if threshold_value <= 0:
            return response(400, {"message": "spendingThreshold must be greater than 0"})

        users_table.update_item(
            Key={"userId": user_id},
            UpdateExpression="SET spendingThreshold = :threshold, updatedAt = :updatedAt",
            ExpressionAttributeValues={
                ":threshold": threshold_value,
                ":updatedAt": datetime.now(timezone.utc).isoformat(),
            },
            ConditionExpression="attribute_exists(userId)",
            ReturnValues="ALL_NEW",
        )

        result = users_table.get_item(Key={"userId": user_id})
        return response(200, {"message": "Spending threshold updated", "user": result.get("Item", {})})
    except Exception as error:
        if getattr(error, "response", {}).get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return response(404, {"message": "User not found"})
        return response(500, {"message": "Failed to update spending threshold", "error": str(error)})
