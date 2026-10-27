# Backend APIs and Core Data — Swathi

This starter implements the backend layer for the Smart Personal Finance Tracker.

## Services used
- API Gateway
- AWS Lambda
- DynamoDB
- S3
- RDS MySQL
- SageMaker integration hook
- Secrets Manager
- CloudWatch
- IAM

## Features included
- Create user profile
- Generate pre-signed upload URL for statement upload
- Save transactions
- Fetch transactions for a user
- Get monthly summary
- Get category spending summary
- Get analytics overview with trends, merchant leaders, and anomaly candidates
- Persist reporting aggregates into RDS for downstream dashboards and future BI exports
- Generate ML-oriented predictions with a SageMaker-compatible endpoint contract
- Invoke a live SageMaker endpoint when `ModelConfigSecretArn` contains a deployed endpoint name
- Provision CloudWatch dashboard and alarms for analytics operations

## Folder structure
- `lambdas/` — Lambda handlers
- `api-docs/` — API docs and sample requests
- `data-models/` — DynamoDB table design
- `infra/` — AWS CDK stack

Person 4 documentation and model assets now live under `../analytics-ml-monitoring/`.

## Local setup
```bash
cd backend/infra
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
Docker must be running because Lambda dependencies are bundled during `cdk deploy`.
cdk bootstrap
cdk deploy
```

## Environment variables used by Lambdas
- `USERS_TABLE`
- `TRANSACTIONS_TABLE`
- `UPLOADS_TABLE`
- `STATEMENTS_BUCKET`
- `AWS_REGION`
- `REPORTING_DB_SECRET_ARN`
- `REPORTING_DB_HOST`
- `REPORTING_DB_NAME`
- `ML_CONFIG_SECRET_ARN`

## API endpoints
- `POST /user`
- `POST /statement/upload`
- `POST /transactions`
- `GET /transactions/{userId}`
- `GET /summary/monthly/{userId}?month=YYYY-MM`
- `GET /analytics/category/{userId}?month=YYYY-MM`
- `GET /analytics/overview/{userId}?month=YYYY-MM&months=6`
- `GET /ml/predictions/{userId}?month=YYYY-MM&months=6`

## Example flow
1. Frontend calls `POST /user`
2. Frontend calls `POST /statement/upload`
3. Backend returns a pre-signed S3 URL
4. Frontend uploads the PDF or CSV directly to S3
5. Workflow team can process the uploaded file later
6. Parsed transactions are stored with `POST /transactions`
7. Frontend fetches transactions and summaries using the GET endpoints
8. Person 4 analytics can call the overview endpoint for trend charts and simple forecasting
9. RDS stores reporting aggregates for the web dashboard, analytics APIs, and model snapshots

## Person 4 resources created by CDK
- VPC for analytics services
- MySQL RDS instance for reporting tables
- Secrets Manager secrets for DB credentials and ML config
- IAM role for SageMaker execution
- CloudWatch dashboard and alarms for analytics Lambda health
