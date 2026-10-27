import os
import re
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

from common import get_json_body, response


dynamodb = boto3.resource("dynamodb")
sns = boto3.client("sns")
users_table = dynamodb.Table(os.environ["USERS_TABLE"])


def _topic_name_for_user(user_id: str) -> str:
    safe_suffix = re.sub(r"[^A-Za-z0-9_-]", "-", user_id)[:80]
    return f"finance-tracker-user-alert-{safe_suffix}"


def _create_user_alert_subscription(user_id: str, email: str) -> tuple[str, str]:
    topic = sns.create_topic(Name=_topic_name_for_user(user_id))
    topic_arn = topic["TopicArn"]
    subscription = sns.subscribe(
        TopicArn=topic_arn,
        Protocol="email",
        Endpoint=email,
        ReturnSubscriptionArn=True,
    )
    return topic_arn, subscription.get("SubscriptionArn", "PendingConfirmation")


def lambda_handler(event, context):
    try:
        body = get_json_body(event)
        user_id = body.get("userId")
        email = body.get("email")
        currency = body.get("currencyPreference", "USD")

        if not user_id or not email:
            return response(400, {"message": "userId and email are required"})

        alert_topic_arn, alert_subscription_arn = _create_user_alert_subscription(user_id, email)

        item = {
            "userId": user_id,
            "email": email,
            "currencyPreference": currency,
            "spendingThreshold": 1000,
            "alertTopicArn": alert_topic_arn,
            "alertSubscriptionArn": alert_subscription_arn,
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }

        users_table.put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(userId)",
        )
        return response(201, {"message": "User created", "user": item})

    except ClientError as error:
        if error.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return response(409, {"message": "User already exists"})
        return response(500, {"message": "Failed to create user", "error": str(error)})
    except Exception as error:
        return response(500, {"message": "Unexpected error", "error": str(error)})
