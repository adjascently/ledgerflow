import os
import uuid
from datetime import datetime, timezone

import boto3

from common import get_json_body, response


s3_client = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")
uploads_table = dynamodb.Table(os.environ["UPLOADS_TABLE"])
BUCKET = os.environ["STATEMENTS_BUCKET"]

SUPPORTED = {
    "application/pdf": ".pdf",
    "text/csv": ".csv",
    "application/vnd.ms-excel": ".csv",
}


def lambda_handler(event, context):
    try:
        body = get_json_body(event)
        user_id = body.get("userId")
        file_name = body.get("fileName", "statement.pdf")
        content_type = body.get("contentType", "application/pdf")

        if not user_id:
            return response(400, {"message": "userId is required"})
        if content_type not in SUPPORTED:
            return response(400, {"message": f"Unsupported contentType: {content_type}"})

        upload_id = str(uuid.uuid4())
        extension = os.path.splitext(file_name)[1] or SUPPORTED[content_type]
        s3_key = f"statements/{user_id}/{upload_id}{extension}"

        upload_url = s3_client.generate_presigned_url(
            ClientMethod="put_object",
            Params={
                "Bucket": BUCKET,
                "Key": s3_key,
                "ContentType": content_type,
            },
            ExpiresIn=900,
        )

        record = {
            "uploadId": upload_id,
            "userId": user_id,
            "fileName": file_name,
            "s3Key": s3_key,
            "status": "PENDING_UPLOAD",
            "uploadedAt": datetime.now(timezone.utc).isoformat(),
            "contentType": content_type,
        }
        uploads_table.put_item(Item=record)

        return response(200, {
            "uploadId": upload_id,
            "s3Key": s3_key,
            "uploadUrl": upload_url,
            "expiresIn": 900,
        })
    except Exception as error:
        return response(500, {"message": "Failed to generate upload URL", "error": str(error)})
