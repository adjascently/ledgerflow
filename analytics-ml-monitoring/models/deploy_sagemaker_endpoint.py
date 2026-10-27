from __future__ import annotations

import argparse
import json
import tarfile
import tempfile
from pathlib import Path

import boto3


IMAGE_URI_BY_REGION = {
    "us-east-1": "683313688378.dkr.ecr.us-east-1.amazonaws.com/sagemaker-scikit-learn:1.2-1-cpu-py3",
    "us-east-2": "257758044811.dkr.ecr.us-east-2.amazonaws.com/sagemaker-scikit-learn:1.2-1-cpu-py3",
    "us-west-1": "632365934929.dkr.ecr.us-west-1.amazonaws.com/sagemaker-scikit-learn:1.2-1-cpu-py3",
    "us-west-2": "246618743249.dkr.ecr.us-west-2.amazonaws.com/sagemaker-scikit-learn:1.2-1-cpu-py3",
}


ROOT = Path(__file__).resolve().parent
INFERENCE_SCRIPT = ROOT / "sagemaker_inference.py"


def package_model_artifact(artifact_dir: Path) -> Path:
    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as temp_file:
        bundle_path = Path(temp_file.name)

    with tempfile.TemporaryDirectory() as temp_dir:
        staging = Path(temp_dir)
        if artifact_dir.exists():
            for item in artifact_dir.iterdir():
                if item.is_file():
                    (staging / item.name).write_bytes(item.read_bytes())

        metadata_path = staging / "metadata.json"
        if not metadata_path.exists():
            metadata_path.write_text(json.dumps({"model_name": "sagemaker-baseline-fallback"}, indent=2))

        with tarfile.open(bundle_path, "w:gz") as tar:
            for item in staging.rglob("*"):
                tar.add(item, arcname=item.relative_to(staging))

    return bundle_path


def package_source_bundle() -> Path:
    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as temp_file:
        bundle_path = Path(temp_file.name)

    with tempfile.TemporaryDirectory() as temp_dir:
        staging = Path(temp_dir)
        (staging / "inference.py").write_text(INFERENCE_SCRIPT.read_text())

        with tarfile.open(bundle_path, "w:gz") as tar:
            for item in staging.rglob("*"):
                tar.add(item, arcname=item.relative_to(staging))

    return bundle_path


def upload_artifact(s3_client, bucket: str, key: str, artifact_path: Path) -> str:
    s3_client.upload_file(str(artifact_path), bucket, key)
    return f"s3://{bucket}/{key}"


def upsert_endpoint(
    region: str,
    model_name: str,
    endpoint_name: str,
    endpoint_config_name: str,
    execution_role_arn: str,
    model_data_url: str,
    source_bundle_url: str,
    instance_type: str,
    image_uri: str,
):
    sm = boto3.client("sagemaker", region_name=region)

    primary_container = {
        "Image": image_uri,
        "ModelDataUrl": model_data_url,
        "Environment": {
            "SAGEMAKER_PROGRAM": "inference.py",
            "SAGEMAKER_SUBMIT_DIRECTORY": source_bundle_url,
        },
    }

    try:
        sm.describe_model(ModelName=model_name)
    except sm.exceptions.ClientError:
        sm.create_model(
            ModelName=model_name,
            ExecutionRoleArn=execution_role_arn,
            PrimaryContainer=primary_container,
        )

    try:
        sm.describe_endpoint_config(EndpointConfigName=endpoint_config_name)
    except sm.exceptions.ClientError:
        sm.create_endpoint_config(
            EndpointConfigName=endpoint_config_name,
            ProductionVariants=[{
                "VariantName": "AllTraffic",
                "ModelName": model_name,
                "InitialInstanceCount": 1,
                "InstanceType": instance_type,
                "InitialVariantWeight": 1.0,
            }],
        )

    try:
        sm.describe_endpoint(EndpointName=endpoint_name)
        sm.update_endpoint(EndpointName=endpoint_name, EndpointConfigName=endpoint_config_name)
    except sm.exceptions.ClientError:
        sm.create_endpoint(EndpointName=endpoint_name, EndpointConfigName=endpoint_config_name)


def update_model_secret(region: str, secret_arn: str, endpoint_name: str):
    sm_client = boto3.client("secretsmanager", region_name=region)
    existing = sm_client.get_secret_value(SecretId=secret_arn)
    payload = json.loads(existing["SecretString"])
    payload["sagemakerEndpointName"] = endpoint_name
    sm_client.update_secret(SecretId=secret_arn, SecretString=json.dumps(payload))


def main():
    parser = argparse.ArgumentParser(description="Package and deploy the SageMaker endpoint for finance predictions.")
    parser.add_argument("--region", default="us-west-2")
    parser.add_argument("--artifact-dir", default=str(ROOT / "trained_artifacts"))
    parser.add_argument("--artifact-bucket", required=True)
    parser.add_argument("--artifact-key", default="sagemaker/finance-tracker/model.tar.gz")
    parser.add_argument("--source-key", default="sagemaker/finance-tracker/source.tar.gz")
    parser.add_argument("--model-name", default="finance-tracker-ml-model")
    parser.add_argument("--endpoint-config-name", default="finance-tracker-ml-config")
    parser.add_argument("--endpoint-name", default="finance-tracker-ml-endpoint")
    parser.add_argument("--execution-role-arn", required=True)
    parser.add_argument("--model-config-secret-arn", required=True)
    parser.add_argument("--instance-type", default="ml.m5.large")
    parser.add_argument("--image-uri", default="")
    args = parser.parse_args()

    image_uri = args.image_uri or IMAGE_URI_BY_REGION.get(args.region)
    if not image_uri:
        raise SystemExit("No default SageMaker scikit-learn image URI for this region. Pass --image-uri explicitly.")

    artifact_path = package_model_artifact(Path(args.artifact_dir))
    source_bundle_path = package_source_bundle()
    s3_client = boto3.client("s3", region_name=args.region)
    model_data_url = upload_artifact(s3_client, args.artifact_bucket, args.artifact_key, artifact_path)
    source_bundle_url = upload_artifact(s3_client, args.artifact_bucket, args.source_key, source_bundle_path)

    upsert_endpoint(
        region=args.region,
        model_name=args.model_name,
        endpoint_name=args.endpoint_name,
        endpoint_config_name=args.endpoint_config_name,
        execution_role_arn=args.execution_role_arn,
        model_data_url=model_data_url,
        source_bundle_url=source_bundle_url,
        instance_type=args.instance_type,
        image_uri=image_uri,
    )
    update_model_secret(args.region, args.model_config_secret_arn, args.endpoint_name)

    print(json.dumps({
        "status": "submitted",
        "modelDataUrl": model_data_url,
        "sourceBundleUrl": source_bundle_url,
        "endpointName": args.endpoint_name,
        "modelConfigSecretArn": args.model_config_secret_arn,
    }, indent=2))


if __name__ == "__main__":
    main()
