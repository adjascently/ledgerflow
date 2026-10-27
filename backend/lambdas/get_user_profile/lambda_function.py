import os

import boto3

from common import response


dynamodb = boto3.resource("dynamodb")
users_table = dynamodb.Table(os.environ["USERS_TABLE"])


def lambda_handler(event, context):
    try:
        path_params = event.get("pathParameters") or {}
        user_id = path_params.get("userId")

        if not user_id:
            return response(400, {"message": "userId path parameter is required"})

        result = users_table.get_item(Key={"userId": user_id})
        item = result.get("Item")
        if not item:
            return response(404, {"message": "User not found"})

        return response(200, {"user": item})
    except Exception as error:
        return response(500, {"message": "Failed to fetch user profile", "error": str(error)})
