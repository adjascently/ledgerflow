# SageMaker Training Assets

This folder contains a starter training script for Person 4.

## Intended workflow
1. Refresh reporting data through the backend analytics endpoints, then export the reporting tables from the MySQL RDS instance.
2. Upload the CSV to S3.
3. Run the training script inside SageMaker Studio or a SageMaker Processing/Training job.
4. Package the trained artifacts behind a SageMaker inference endpoint.
5. Put the endpoint name into the `ModelConfigSecretArn` secret so `/ml/predictions` starts invoking SageMaker instead of the fallback heuristic.

## What is now integrated

This repo now includes a complete SageMaker deployment path:

- `train_sagemaker_models.py`
  trains the regression, category, and anomaly models from exported reporting data.
- `sagemaker_inference.py`
  implements the live inference contract expected by the backend `/ml/predictions` Lambda.
- `deploy_sagemaker_endpoint.py`
  packages model artifacts, uploads them to S3, creates or updates the SageMaker model and endpoint, and writes the endpoint name into `ModelConfigSecretArn`.

Once that secret is updated, the existing backend Lambda will automatically invoke SageMaker instead of the local heuristic fallback.

## Deployment flow

1. Refresh reporting data through the backend analytics endpoints.
2. Export `reporting_monthly_summary` to CSV.
3. Train the model artifacts:

```bash
cd /Users/shreya.chavan/Desktop/cloud-computing/project/smart-personal-finance-tracker/analytics-ml-monitoring/models
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python train_sagemaker_models.py \
  --input /path/to/reporting_monthly_summary.csv \
  --output /Users/shreya.chavan/Desktop/cloud-computing/project/smart-personal-finance-tracker/analytics-ml-monitoring/models/trained_artifacts
```

4. Deploy the endpoint and update the secret:

```bash
python deploy_sagemaker_endpoint.py \
  --region us-west-2 \
  --artifact-bucket <an-s3-bucket-you-control> \
  --execution-role-arn <SageMakerExecutionRoleArn output> \
  --model-config-secret-arn <ModelConfigSecretArn output>
```

Optional overrides:
- `--endpoint-name`
- `--endpoint-config-name`
- `--model-name`
- `--instance-type`
- `--image-uri`

## Notes

- The deployment script defaults to the official SageMaker scikit-learn inference image for `us-west-2`.
- If `trained_artifacts/` is empty, the endpoint still deploys and serves a SageMaker-hosted heuristic fallback.
- The backend contract does not change. `/ml/predictions/{userId}` continues returning the same response shape; only the prediction source switches from `heuristic` to `sagemaker`.

## Expected input columns
- `month_key`
- `total_spent`
- `transaction_count`
- `average_transaction`
- `top_category`
- `top_merchant`
- `change_from_previous_pct`

## Models
- Regression model for next-month spending prediction
- Classifier for top-category suggestion
- Isolation Forest for anomaly scoring
