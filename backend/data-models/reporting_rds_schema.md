# Reporting RDS Schema

The analytics extension stores reporting-friendly aggregates in MySQL so the web dashboard, analytics APIs, and ML jobs do not need to scan DynamoDB directly. The same schema can support QuickSight later if that integration is added.

## reporting_monthly_summary
- **PK**: `(user_id, month_key)`
- Fields:
  - `total_spent`
  - `transaction_count`
  - `average_transaction`
  - `top_category`
  - `top_merchant`
  - `predicted_next_month_spend`
  - `previous_month_total_spent`
  - `change_from_previous_pct`
  - `refreshed_at`

## reporting_category_summary
- **PK**: `(user_id, month_key, category)`
- Fields:
  - `total_spent`
  - `transaction_count`
  - `average_amount`
  - `share_pct`
  - `refreshed_at`

## reporting_merchant_summary
- **PK**: `(user_id, month_key, merchant)`
- Fields:
  - `total_spent`
  - `transaction_count`
  - `refreshed_at`

## reporting_daily_spend
- **PK**: `(user_id, spend_date)`
- Fields:
  - `month_key`
  - `total_spent`
  - `refreshed_at`

## prediction_snapshots
- **PK**: `(user_id, month_key)`
- Fields:
  - `model_name`
  - `forecast_amount`
  - `anomaly_risk_level`
  - `anomaly_risk_score`
  - `suggestions_json`
  - `source`
  - `refreshed_at`
