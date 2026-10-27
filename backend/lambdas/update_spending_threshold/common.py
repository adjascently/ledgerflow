import json
import os
from decimal import Decimal
from typing import Any, Dict


def get_json_body(event: Dict[str, Any]) -> Dict[str, Any]:
    body = event.get("body")
    if not body:
        return {}
    if isinstance(body, str):
        return json.loads(body)
    return body


class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


def response(status_code: int, body: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Allow-Methods": "*",
        },
        "body": json.dumps(body, cls=DecimalEncoder),
    }


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value
