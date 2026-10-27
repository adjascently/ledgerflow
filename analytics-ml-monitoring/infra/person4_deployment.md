# Person 4 Deployment

This is the AWS-native analytics, ML, reports, and monitoring slice.

## What gets deployed
- RDS MySQL for reporting aggregates
- Secrets Manager secrets for DB credentials and model config
- SageMaker execution role
- Analytics overview Lambda with RDS sync
- ML predictions Lambda with SageMaker endpoint hook
- CloudWatch dashboard and alarms

## Deploy
```bash
cd backend/infra
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
npm install -g aws-cdk
aws configure
cdk bootstrap
cdk deploy
```

## Important outputs
- `FinanceApiEndpoint`
- `ReportingDbEndpoint`
- `ReportingDbSecretArn`
- `ModelConfigSecretArn`
- `SageMakerExecutionRoleArn`
- `CloudWatchDashboardName`

## After deploy
1. Open the secret in `ModelConfigSecretArn`.
2. To activate the live SageMaker integration, deploy the endpoint from `../models` and let the deployment script update `sagemakerEndpointName` in that secret automatically.
3. Invoke:
   - `GET /analytics/overview/{userId}?month=YYYY-MM&months=6` to refresh RDS reporting tables
   - `GET /ml/predictions/{userId}?month=YYYY-MM&months=6` to create prediction snapshots
4. Use the web dashboard as the primary analytics view and CloudWatch as the primary monitoring view.
5. Treat [quicksight_setup.md](../dashboards/quicksight_setup.md) as optional future work, not a required deployment step.

## SageMaker endpoint activation
```bash
cd /Users/shreya.chavan/Desktop/cloud-computing/project/smart-personal-finance-tracker/analytics-ml-monitoring/models
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python deploy_sagemaker_endpoint.py \
  --region us-west-2 \
  --artifact-bucket <an-s3-bucket-you-control> \
  --execution-role-arn <SageMakerExecutionRoleArn> \
  --model-config-secret-arn <ModelConfigSecretArn>
```

If `trained_artifacts/` contains trained model files, the endpoint serves trained predictions. If it is empty, the endpoint still deploys and serves a SageMaker-hosted baseline fallback using the same API contract.

## Monitoring
- CloudWatch dashboard: `finance-tracker-analytics-ops`
- Alarms:
  - analytics overview Lambda errors
  - ML predictions Lambda errors
  - reporting database CPU above 80%
