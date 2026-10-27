# Infrastructure and Deployment Notes

## Purpose

This file documents the AWS resources and deployment steps for the workflow and event-processing module.

This stack depends on the backend infrastructure being deployed first, because it reuses the statements S3 bucket created by the backend stack as the event source.

## Region

Deploy this stack in the same region as the backend stack.

Current recommended region:
`us-west-2`

## Main Resources Used

The workflow module uses the following AWS resources:

- S3 bucket from the backend stack
- EventBridge rule
- Step Functions state machine
- SQS queue
- Lambda function
- SNS topic
- CloudWatch logs for the state machine

## Deployment Order

The resources should be configured in the following order:

1. Deploy backend infrastructure
2. Copy the backend `StatementsBucketName` output
3. Deploy the workflow CDK stack with the bucket name and alert email as parameters
4. Confirm the SNS email subscription
5. Test by uploading a file to S3

## Backend Dependency

The workflow deployment requires the real S3 bucket name created by the backend deployment.

Example command:

```bash
cd /Users/shreya.chavan/Desktop/cloud-computing/project/smart-personal-finance-tracker/workflow-events-notifications/infra
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cdk deploy \
  --parameters StatementsBucketName=<backend bucket name> \
  --parameters AlertEmail=<your email address> \
  --parameters DefaultThreshold=1000 \
  --require-approval never
```

## Testing Flow

After all resources are created:

1. Upload a file to the deployed S3 bucket
2. EventBridge detects the upload
3. Step Functions starts automatically
4. Lambda processes the event
5. SNS sends an email alert

## Important Notes

- The backend must be deployed before setting up EventBridge
- The EventBridge rule must match the exact deployed bucket name
- EventBridge notifications are enabled by the workflow stack through a custom resource
- For automatic S3-triggered events, placeholder values such as `userId = unknown` and `uploadId = auto` are acceptable for demo purposes
