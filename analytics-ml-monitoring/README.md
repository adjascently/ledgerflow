# Analytics, ML, and Monitoring

This module groups the Person 4 assets:
- `dashboards/` for reporting notes and deferred QuickSight setup guidance
- `models/` for SageMaker training assets
- `monitoring/` for CloudWatch guidance
- `infra/` for deployment notes

## Important note
The actual AWS resources for analytics are provisioned from `../backend/infra` because the analytics Lambdas and API endpoints are part of the backend stack.

## Delivered analytics surface
- The primary reporting dashboard is the web app dashboard backed by AWS Lambda, DynamoDB, and RDS aggregates.
- CloudWatch is the primary AWS-native monitoring dashboard.
- QuickSight is treated as optional future work because the private RDS networking path adds significant operational overhead for this project.
- SageMaker now has a concrete deployment path under `models/`; once the endpoint is deployed and written into `ModelConfigSecretArn`, the existing `/ml/predictions` API invokes SageMaker instead of the local heuristic fallback.
