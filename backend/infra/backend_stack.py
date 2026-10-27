import json
from pathlib import Path

from aws_cdk import (
    BundlingOptions,
    CfnOutput,
    Duration,
    RemovalPolicy,
    SecretValue,
    Stack,
    aws_apigateway as apigw,
    aws_cloudwatch as cloudwatch,
    aws_dynamodb as dynamodb,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_lambda as _lambda,
    aws_rds as rds,
    aws_s3 as s3,
    aws_secretsmanager as secretsmanager,
)
from constructs import Construct


class FinanceBackendStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        project_root = Path(__file__).resolve().parents[1]
        lambdas_root = project_root / "lambdas"

        users_table = dynamodb.Table(
            self,
            "UsersTable",
            partition_key=dynamodb.Attribute(name="userId", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
        )

        transactions_table = dynamodb.Table(
            self,
            "TransactionsTable",
            partition_key=dynamodb.Attribute(name="userId", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="transactionDate", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
        )
        transactions_table.add_global_secondary_index(
            index_name="TransactionIdIndex",
            partition_key=dynamodb.Attribute(name="transactionId", type=dynamodb.AttributeType.STRING),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        uploads_table = dynamodb.Table(
            self,
            "UploadsTable",
            partition_key=dynamodb.Attribute(name="uploadId", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
        )
        uploads_table.add_global_secondary_index(
            index_name="UserUploadsIndex",
            partition_key=dynamodb.Attribute(name="userId", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="uploadedAt", type=dynamodb.AttributeType.STRING),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        statements_bucket = s3.Bucket(
            self,
            "StatementsBucket",
            auto_delete_objects=True,
            removal_policy=RemovalPolicy.DESTROY,
            cors=[
                s3.CorsRule(
                    allowed_headers=["*"],
                    allowed_methods=[s3.HttpMethods.GET, s3.HttpMethods.PUT, s3.HttpMethods.POST],
                    allowed_origins=["*"],
                )
            ],
        )

        analytics_vpc = ec2.Vpc(
            self,
            "AnalyticsVpc",
            nat_gateways=1,
            max_azs=2,
        )

        analytics_lambda_sg = ec2.SecurityGroup(
            self,
            "AnalyticsLambdaSecurityGroup",
            vpc=analytics_vpc,
            allow_all_outbound=True,
            description="Security group for analytics and ML Lambdas",
        )

        reporting_db_sg = ec2.SecurityGroup(
            self,
            "ReportingDatabaseSecurityGroup",
            vpc=analytics_vpc,
            allow_all_outbound=False,
            description="Restricts RDS access to analytics Lambdas",
        )
        reporting_db_sg.add_ingress_rule(
            analytics_lambda_sg,
            ec2.Port.tcp(3306),
            "Allow analytics Lambdas to connect to the reporting database",
        )

        reporting_db = rds.DatabaseInstance(
            self,
            "ReportingDatabase",
            engine=rds.DatabaseInstanceEngine.mysql(version=rds.MysqlEngineVersion.VER_8_0_40),
            vpc=analytics_vpc,
            credentials=rds.Credentials.from_generated_secret("finance_admin"),
            database_name="finance_reporting",
            instance_type=ec2.InstanceType.of(ec2.InstanceClass.BURSTABLE3, ec2.InstanceSize.MICRO),
            security_groups=[reporting_db_sg],
            allocated_storage=20,
            max_allocated_storage=100,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            publicly_accessible=False,
            deletion_protection=False,
            removal_policy=RemovalPolicy.DESTROY,
            backup_retention=Duration.days(1),
            multi_az=False,
        )

        analytics_model_config_secret = secretsmanager.Secret(
            self,
            "AnalyticsModelConfigSecret",
            secret_string_value=SecretValue.unsafe_plain_text(json.dumps({
                "sagemakerEndpointName": "",
                "forecastHorizonMonths": 1,
                "defaultSpendingIncreaseThresholdPct": 20,
            })),
        )

        sagemaker_execution_role = iam.Role(
            self,
            "SageMakerExecutionRole",
            assumed_by=iam.ServicePrincipal("sagemaker.amazonaws.com"),
            inline_policies={
                "SageMakerProjectAccess": iam.PolicyDocument(statements=[
                    iam.PolicyStatement(
                        actions=[
                            "s3:GetObject",
                            "s3:PutObject",
                            "s3:ListBucket",
                        ],
                        resources=[
                            statements_bucket.bucket_arn,
                            f"{statements_bucket.bucket_arn}/*",
                        ],
                    ),
                    iam.PolicyStatement(
                        actions=[
                            "cloudwatch:PutMetricData",
                            "logs:CreateLogGroup",
                            "logs:CreateLogStream",
                            "logs:PutLogEvents",
                        ],
                        resources=["*"],
                    ),
                    iam.PolicyStatement(
                        actions=[
                            "ecr:GetDownloadUrlForLayer",
                            "ecr:BatchGetImage",
                            "ecr:BatchCheckLayerAvailability",
                            "ecr:GetAuthorizationToken",
                        ],
                        resources=["*"],
                    ),
                ])
            },
        )

        common_env = {
            "USERS_TABLE": users_table.table_name,
            "TRANSACTIONS_TABLE": transactions_table.table_name,
            "UPLOADS_TABLE": uploads_table.table_name,
            "STATEMENTS_BUCKET": statements_bucket.bucket_name,
        }

        def make_lambda(
            name: str,
            *,
            timeout_seconds: int = 30,
            memory_size: int = 256,
            environment: dict | None = None,
            vpc: ec2.IVpc | None = None,
            security_groups: list[ec2.ISecurityGroup] | None = None,
        ) -> _lambda.Function:
            lambda_path = lambdas_root / name
            requirements_file = lambda_path / "requirements.txt"
            bundling = None
            if requirements_file.exists():
                bundling = BundlingOptions(
                    image=_lambda.Runtime.PYTHON_3_12.bundling_image,
                    command=[
                        "bash",
                        "-lc",
                        "pip install -r requirements.txt -t /asset-output && cp -au . /asset-output",
                    ],
                )

            fn = _lambda.Function(
                self,
                f"{name.title().replace('_', '')}Lambda",
                runtime=_lambda.Runtime.PYTHON_3_12,
                handler="lambda_function.lambda_handler",
                code=_lambda.Code.from_asset(str(lambda_path), bundling=bundling),
                timeout=Duration.seconds(timeout_seconds),
                memory_size=memory_size,
                environment={**common_env, **(environment or {})},
                vpc=vpc,
                security_groups=security_groups,
            )
            users_table.grant_read_write_data(fn)
            transactions_table.grant_read_write_data(fn)
            uploads_table.grant_read_write_data(fn)
            statements_bucket.grant_read_write(fn)
            return fn

        create_user_fn = make_lambda("create_user")
        create_user_fn.add_to_role_policy(iam.PolicyStatement(
            actions=[
                "sns:CreateTopic",
                "sns:Subscribe",
            ],
            resources=["*"],
        ))
        get_user_profile_fn = make_lambda("get_user_profile")
        generate_upload_url_fn = make_lambda("generate_upload_url")
        save_transactions_fn = make_lambda("save_transactions")
        get_transactions_fn = make_lambda("get_transactions")
        update_spending_threshold_fn = make_lambda("update_spending_threshold")
        monthly_summary_fn = make_lambda("monthly_summary")
        category_spending_fn = make_lambda("category_spending")
        analytics_overview_fn = make_lambda(
            "analytics_overview",
            timeout_seconds=60,
            memory_size=512,
            environment={
                "REPORTING_DB_SECRET_ARN": reporting_db.secret.secret_arn if reporting_db.secret else "",
                "REPORTING_DB_HOST": reporting_db.instance_endpoint.hostname,
                "REPORTING_DB_NAME": "finance_reporting",
            },
            vpc=analytics_vpc,
            security_groups=[analytics_lambda_sg],
        )
        ml_predictions_fn = make_lambda(
            "ml_predictions",
            timeout_seconds=60,
            memory_size=512,
            environment={
                "REPORTING_DB_SECRET_ARN": reporting_db.secret.secret_arn if reporting_db.secret else "",
                "REPORTING_DB_HOST": reporting_db.instance_endpoint.hostname,
                "REPORTING_DB_NAME": "finance_reporting",
                "ML_CONFIG_SECRET_ARN": analytics_model_config_secret.secret_arn,
            },
            vpc=analytics_vpc,
            security_groups=[analytics_lambda_sg],
        )

        if reporting_db.secret:
            reporting_db.secret.grant_read(analytics_overview_fn)
            reporting_db.secret.grant_read(ml_predictions_fn)
        analytics_model_config_secret.grant_read(ml_predictions_fn)

        ml_predictions_fn.add_to_role_policy(iam.PolicyStatement(
            actions=["sagemaker:InvokeEndpoint"],
            resources=["*"],
        ))

        api = apigw.RestApi(
            self,
            "FinanceApi",
            rest_api_name="Smart Personal Finance Backend API",
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS,
                allow_methods=apigw.Cors.ALL_METHODS,
                allow_headers=["*"],
            ),
        )

        user_resource = api.root.add_resource("user")
        user_resource.add_method("POST", apigw.LambdaIntegration(create_user_fn))
        user_profile = user_resource.add_resource("{userId}")
        user_profile.add_method("GET", apigw.LambdaIntegration(get_user_profile_fn))
        user_profile.add_method("PUT", apigw.LambdaIntegration(update_spending_threshold_fn))

        statement_upload = api.root.add_resource("statement").add_resource("upload")
        statement_upload.add_method("POST", apigw.LambdaIntegration(generate_upload_url_fn))

        transactions = api.root.add_resource("transactions")
        transactions.add_method("POST", apigw.LambdaIntegration(save_transactions_fn))
        transactions_user = transactions.add_resource("{userId}")
        transactions_user.add_method("GET", apigw.LambdaIntegration(get_transactions_fn))

        summary_user = api.root.add_resource("summary").add_resource("monthly").add_resource("{userId}")
        summary_user.add_method("GET", apigw.LambdaIntegration(monthly_summary_fn))

        analytics_resource = api.root.add_resource("analytics")

        analytics_category_user = analytics_resource.add_resource("category").add_resource("{userId}")
        analytics_category_user.add_method("GET", apigw.LambdaIntegration(category_spending_fn))

        analytics_overview_user = analytics_resource.add_resource("overview").add_resource("{userId}")
        analytics_overview_user.add_method("GET", apigw.LambdaIntegration(analytics_overview_fn))

        ml_predictions_user = api.root.add_resource("ml").add_resource("predictions").add_resource("{userId}")
        ml_predictions_user.add_method("GET", apigw.LambdaIntegration(ml_predictions_fn))

        ops_dashboard = cloudwatch.Dashboard(
            self,
            "AnalyticsOperationsDashboard",
            dashboard_name="finance-tracker-analytics-ops",
        )
        ops_dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="Analytics and ML Lambda Invocations",
                left=[
                    analytics_overview_fn.metric_invocations(),
                    ml_predictions_fn.metric_invocations(),
                ],
            ),
            cloudwatch.GraphWidget(
                title="Analytics and ML Lambda Errors",
                left=[
                    analytics_overview_fn.metric_errors(),
                    ml_predictions_fn.metric_errors(),
                ],
            ),
            cloudwatch.GraphWidget(
                title="Reporting Database Health",
                left=[
                    reporting_db.metric_cpu_utilization(),
                    reporting_db.metric_database_connections(),
                ],
            ),
        )

        cloudwatch.Alarm(
            self,
            "AnalyticsOverviewErrorsAlarm",
            metric=analytics_overview_fn.metric_errors(period=Duration.minutes(5)),
            threshold=1,
            evaluation_periods=1,
            alarm_description="Triggers when the analytics overview Lambda reports an error.",
        )

        cloudwatch.Alarm(
            self,
            "MlPredictionsErrorsAlarm",
            metric=ml_predictions_fn.metric_errors(period=Duration.minutes(5)),
            threshold=1,
            evaluation_periods=1,
            alarm_description="Triggers when the ML predictions Lambda reports an error.",
        )

        cloudwatch.Alarm(
            self,
            "ReportingDbCpuAlarm",
            metric=reporting_db.metric_cpu_utilization(period=Duration.minutes(5)),
            threshold=80,
            evaluation_periods=2,
            alarm_description="Triggers when the reporting RDS instance sustains high CPU usage.",
        )

        CfnOutput(self, "FinanceApiEndpoint", value=api.url)
        CfnOutput(self, "StatementsBucketName", value=statements_bucket.bucket_name)
        CfnOutput(self, "ReportingDbEndpoint", value=reporting_db.instance_endpoint.hostname)
        if reporting_db.secret:
            CfnOutput(self, "ReportingDbSecretArn", value=reporting_db.secret.secret_arn)
        CfnOutput(self, "ModelConfigSecretArn", value=analytics_model_config_secret.secret_arn)
        CfnOutput(self, "SageMakerExecutionRoleArn", value=sagemaker_execution_role.role_arn)
        CfnOutput(self, "CloudWatchDashboardName", value="finance-tracker-analytics-ops")
