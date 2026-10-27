# Monitoring

Operational monitoring is provisioned through the backend CDK stack.

## Current coverage
- CloudWatch dashboard: `finance-tracker-analytics-ops`
- Lambda error alarms for analytics overview and ML predictions
- RDS CPU alarm for the reporting database

## Source of truth
See `../../backend/infra/backend_stack.py` for the actual CloudWatch resources.
