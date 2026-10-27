# Workflow & Event Processing

## Overview

This module deploys the event-driven processing pipeline for the Smart Personal Finance Tracker with AWS CDK.

The workflow path is:

```text
S3 Upload -> EventBridge -> Step Functions -> SQS -> Lambda -> SNS
```

The stack creates:

- EventBridge rule for new statement uploads
- Step Functions state machine for orchestration
- SQS queue for async buffering
- Processor Lambda
- SNS topic and email subscription for alerts
- S3 EventBridge enablement on the backend statements bucket

## Prerequisites

Before deploying this stack:

1. Deploy the backend stack first from [backend/infra](/Users/shreya.chavan/Desktop/cloud-computing/project/smart-personal-finance-tracker/backend/infra).
2. Use the same AWS account and same region for backend and workflow.
3. Keep the project in `us-west-2` if that is the region you are already using.
4. Have Docker running locally, because the processor Lambda is bundled in a container.

You need the backend stack output:

- `StatementsBucketName`

## Deploy

From [workflow-events-notifications/infra](/Users/shreya.chavan/Desktop/cloud-computing/project/smart-personal-finance-tracker/workflow-events-notifications/infra):

```bash
cd /Users/shreya.chavan/Desktop/cloud-computing/project/smart-personal-finance-tracker/workflow-events-notifications/infra
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cdk bootstrap aws://$(aws sts get-caller-identity --query Account --output text)/us-west-2
cdk deploy \
  --parameters StatementsBucketName=<backend StatementsBucketName output> \
  --parameters AlertEmail=<your email address> \
  --parameters DefaultThreshold=1000 \
  --require-approval never
```

If you already bootstrapped `us-west-2`, you can skip the `cdk bootstrap` command.

## What the Stack Creates

After deploy, the workflow stack creates:

- SNS topic: `finance-tracker-alert-topic`
- SQS queue: `finance-tracker-statement-queue`
- Lambda: `finance-tracker-processor-lambda`
- Step Functions state machine: `finance-tracker-workflow`
- EventBridge rule: `finance-tracker-s3-trigger`

The stack also enables EventBridge notifications on the existing statements bucket automatically through a custom resource. You do not need to turn that on manually in the S3 console.

## Outputs

The stack exports:

- `WorkflowStatementsBucketName`
- `WorkflowSnsTopicArn`
- `WorkflowSqsQueueUrl`
- `WorkflowProcessorLambdaArn`
- `WorkflowStateMachineArn`
- `WorkflowEventRuleName`

## Test the Pipeline

1. Confirm the SNS subscription email and accept it.
2. Upload a file to the backend statements bucket.
3. Check EventBridge for matched events.
4. Check Step Functions for a new execution.
5. Check the processor Lambda logs in CloudWatch.
6. Confirm the SNS email alert is delivered.

## Notes

- The EventBridge payload uses `userId = unknown` and `uploadId = auto` for S3-originated uploads, which is acceptable for the current demo workflow.
- The processor Lambda uses mock transactions when no extracted transaction list is supplied.
- If you later connect real statement parsing, that payload can be extended without replacing the infrastructure stack.

## Troubleshooting

- If the rule does not fire, verify that `StatementsBucketName` exactly matches the backend output and that both stacks are in the same region.
- If no email arrives, confirm the SNS subscription and inspect the Step Functions execution path.
- If deployment fails on Lambda bundling, check that Docker is running locally.

---

## 📌 Notes

* `userId` and `uploadId` are placeholders in EventBridge-triggered flow
* In full integration, backend APIs will populate these values
* This module focuses on **event-driven automation**

---
