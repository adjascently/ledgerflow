# QuickSight Deferred / Future Work

This project stores reporting data in the `finance_reporting` MySQL database created by the backend CDK stack, but QuickSight is not part of the required deployment path for the current submission.

## Current reporting path
- The main analytics dashboard is the web app `/dashboard` page.
- Monitoring is provided through the CloudWatch dashboard `finance-tracker-analytics-ops`.
- RDS remains the reporting store for analytics APIs, snapshots, and future BI integration.

## Why QuickSight is deferred
- The RDS instance is private inside a VPC.
- QuickSight requires Enterprise Edition plus a VPC connection and additional security group wiring to reach that database.
- The project already delivers the required reporting value through the app dashboard and CloudWatch with less operational complexity.

## If you want to add QuickSight later
Use the notes below as a future-work path.

## Recommended QuickSight datasets
- `reporting_monthly_summary`
- `reporting_category_summary`
- `reporting_daily_spend`
- `prediction_snapshots`

## Suggested dashboard sheets

### 1. Executive spending overview
- KPI: current month `total_spent`
- KPI: `change_from_previous_pct`
- Line chart: `month_key` vs `total_spent`
- Table: `top_category`, `top_merchant`, `predicted_next_month_spend`

### 2. Category performance
- Bar chart: `category` vs `total_spent`
- Heat map: `month_key` vs `category` using `share_pct`
- Table: `average_amount`, `transaction_count`

### 3. Daily and anomaly monitoring
- Line chart: `spend_date` vs `total_spent`
- Table: `prediction_snapshots` showing `forecast_amount`, `anomaly_risk_level`, `anomaly_risk_score`

## Connection steps
1. Deploy the backend stack so the RDS instance and secrets exist.
2. In AWS QuickSight, create a new data source for MySQL.
3. Use the `ReportingDbEndpoint` stack output as the host.
4. Use the credentials in the `ReportingDbSecretArn` secret.
5. Import the four tables listed above.
6. Build the sheets using the suggested visuals.

## Notes
- Reporting data is refreshed when the backend analytics overview endpoint is called.
- Predictions are written to `prediction_snapshots` when the backend ML predictions endpoint is called.
- If you want scheduled refreshes for QuickSight, create a refresh schedule after the initial import.
