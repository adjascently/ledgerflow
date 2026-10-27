from pathlib import Path

from aws_cdk import (
    Aws,
    BundlingOptions,
    CfnOutput,
    CfnParameter,
    Duration,
    Stack,
    aws_dynamodb as dynamodb,
    aws_events as events,
    aws_events_targets as events_targets,
    aws_iam as iam,
    aws_lambda as _lambda,
    aws_logs as logs,
    aws_s3 as s3,
    aws_sns as sns,
    aws_sns_subscriptions as sns_subscriptions,
    aws_sqs as sqs,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as sfn_tasks,
    custom_resources as cr,
)
from constructs import Construct


class WorkflowEventsStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        project_root = Path(__file__).resolve().parents[1]
        lambda_root = project_root / "lambda" / "processor"

        statements_bucket_name = CfnParameter(
            self,
            "StatementsBucketName",
            type="String",
            description="Name of the S3 bucket created by the backend stack for uploaded statements.",
        )
        alert_email = CfnParameter(
            self,
            "AlertEmail",
            type="String",
            description="Email address to subscribe to workflow SNS alerts.",
        )
        default_threshold = CfnParameter(
            self,
            "DefaultThreshold",
            type="Number",
            default=1000,
            description="Default monthly spending threshold used by the processor Lambda.",
        )
        transactions_table_name = CfnParameter(
            self,
            "TransactionsTableName",
            type="String",
            description="Name of the DynamoDB transactions table created by the backend stack.",
        )
        uploads_table_name = CfnParameter(
            self,
            "UploadsTableName",
            type="String",
            description="Name of the DynamoDB uploads table created by the backend stack.",
        )
        users_table_name = CfnParameter(
            self,
            "UsersTableName",
            type="String",
            description="Name of the DynamoDB users table created by the backend stack.",
        )

        statements_bucket = s3.Bucket.from_bucket_name(
            self,
            "ImportedStatementsBucket",
            statements_bucket_name.value_as_string,
        )
        transactions_table = dynamodb.Table.from_table_name(
            self,
            "ImportedTransactionsTable",
            transactions_table_name.value_as_string,
        )
        uploads_table = dynamodb.Table.from_table_name(
            self,
            "ImportedUploadsTable",
            uploads_table_name.value_as_string,
        )
        users_table = dynamodb.Table.from_table_name(
            self,
            "ImportedUsersTable",
            users_table_name.value_as_string,
        )

        alert_topic = sns.Topic(
            self,
            "FinanceTrackerAlertTopic",
            display_name="Finance Tracker Alerts",
            topic_name="finance-tracker-alert-topic",
        )
        alert_topic.add_subscription(
            sns_subscriptions.EmailSubscription(alert_email.value_as_string)
        )

        statement_queue = sqs.Queue(
            self,
            "FinanceTrackerStatementQueue",
            queue_name="finance-tracker-statement-queue",
            visibility_timeout=Duration.seconds(90),
        )

        bundling = BundlingOptions(
            image=_lambda.Runtime.PYTHON_3_12.bundling_image,
            command=[
                "bash",
                "-lc",
                "pip install -r requirements.txt -t /asset-output && cp -au . /asset-output",
            ],
        )

        processor_fn = _lambda.Function(
            self,
            "FinanceTrackerProcessorLambda",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="lambda_function.lambda_handler",
            code=_lambda.Code.from_asset(str(lambda_root), bundling=bundling),
            timeout=Duration.seconds(30),
            memory_size=256,
            environment={
                "SNS_TOPIC_ARN": alert_topic.topic_arn,
                "DEFAULT_THRESHOLD": default_threshold.value_as_string,
                "TRANSACTIONS_TABLE": transactions_table_name.value_as_string,
                "UPLOADS_TABLE": uploads_table_name.value_as_string,
                "USERS_TABLE": users_table_name.value_as_string,
            },
            function_name="finance-tracker-processor-lambda",
        )
        alert_topic.grant_publish(processor_fn)
        statements_bucket.grant_read(processor_fn)
        transactions_table.grant_read_write_data(processor_fn)
        uploads_table.grant_read_write_data(processor_fn)
        users_table.grant_read_write_data(processor_fn)

        send_message = sfn_tasks.SqsSendMessage(
            self,
            "SendMessageToQueue",
            queue=statement_queue,
            message_body=sfn.TaskInput.from_json_path_at("$"),
            result_path=sfn.JsonPath.DISCARD,
        )

        process_statement = sfn_tasks.LambdaInvoke(
            self,
            "ProcessStatement",
            lambda_function=processor_fn,
            payload=sfn.TaskInput.from_object(
                {
                    "eventType": sfn.JsonPath.string_at("$.eventType"),
                    "userId": sfn.JsonPath.string_at("$.userId"),
                    "uploadId": sfn.JsonPath.string_at("$.uploadId"),
                    "fileKey": sfn.JsonPath.string_at("$.fileKey"),
                    "bucketName": sfn.JsonPath.string_at("$.bucketName"),
                }
            ),
            payload_response_only=True,
            result_path="$.lambdaResult",
            retry_on_service_exceptions=True,
        )

        success_state = sfn.Succeed(self, "WorkflowSuccess")
        queue_failed_state = sfn.Fail(
            self,
            "QueueWorkflowFailed",
            cause="Workflow failed while enqueueing the statement event",
        )
        processing_failed_state = sfn.Fail(
            self,
            "ProcessingWorkflowFailed",
            cause="Workflow failed during statement processing",
        )

        send_message.add_catch(
            queue_failed_state,
            result_path="$.error",
        )
        process_statement.add_catch(
            processing_failed_state,
            result_path="$.error",
        )

        definition = send_message.next(process_statement).next(success_state)

        state_machine = sfn.StateMachine(
            self,
            "FinanceTrackerWorkflow",
            state_machine_name="finance-tracker-workflow",
            definition_body=sfn.DefinitionBody.from_chainable(definition),
            timeout=Duration.minutes(5),
            logs=sfn.LogOptions(
                destination=logs.LogGroup(
                    self,
                    "WorkflowLogGroup",
                    retention=logs.RetentionDays.ONE_WEEK,
                ),
                level=sfn.LogLevel.ALL,
            ),
            tracing_enabled=True,
        )

        workflow_trigger_rule = events.Rule(
            self,
            "FinanceTrackerS3TriggerRule",
            rule_name="finance-tracker-s3-trigger",
            description="Starts the finance tracker statement workflow when a new object is uploaded.",
            event_pattern=events.EventPattern(
                source=["aws.s3"],
                detail_type=["Object Created"],
                detail={
                    "bucket": {
                        "name": [statements_bucket_name.value_as_string],
                    }
                },
            ),
        )
        workflow_trigger_rule.add_target(
            events_targets.SfnStateMachine(
                state_machine,
                input=events.RuleTargetInput.from_object(
                    {
                        "eventType": "statement.uploaded",
                        "userId": "unknown",
                        "uploadId": "auto",
                        "fileKey": events.EventField.from_path("$.detail.object.key"),
                        "bucketName": events.EventField.from_path("$.detail.bucket.name"),
                    }
                ),
            )
        )

        enable_eventbridge_notifications = cr.AwsCustomResource(
            self,
            "EnableEventBridgeOnStatementsBucket",
            on_create=cr.AwsSdkCall(
                service="S3",
                action="putBucketNotificationConfiguration",
                parameters={
                    "Bucket": statements_bucket_name.value_as_string,
                    "NotificationConfiguration": {
                        "EventBridgeConfiguration": {},
                    },
                },
                physical_resource_id=cr.PhysicalResourceId.of(
                    f"eventbridge-enabled-{statements_bucket_name.value_as_string}"
                ),
            ),
            on_update=cr.AwsSdkCall(
                service="S3",
                action="putBucketNotificationConfiguration",
                parameters={
                    "Bucket": statements_bucket_name.value_as_string,
                    "NotificationConfiguration": {
                        "EventBridgeConfiguration": {},
                    },
                },
                physical_resource_id=cr.PhysicalResourceId.of(
                    f"eventbridge-enabled-{statements_bucket_name.value_as_string}"
                ),
            ),
            policy=cr.AwsCustomResourcePolicy.from_statements(
                [
                    iam.PolicyStatement(
                        actions=[
                            "s3:PutBucketNotification",
                            "s3:GetBucketNotification",
                        ],
                        resources=[
                            f"arn:{Aws.PARTITION}:s3:::{statements_bucket_name.value_as_string}",
                        ],
                    )
                ]
            ),
        )
        enable_eventbridge_notifications.node.add_dependency(workflow_trigger_rule)
        enable_eventbridge_notifications.node.add_dependency(state_machine)

        CfnOutput(self, "WorkflowStatementsBucketName", value=statements_bucket_name.value_as_string)
        CfnOutput(self, "WorkflowSnsTopicArn", value=alert_topic.topic_arn)
        CfnOutput(self, "WorkflowSqsQueueUrl", value=statement_queue.queue_url)
        CfnOutput(self, "WorkflowProcessorLambdaArn", value=processor_fn.function_arn)
        CfnOutput(self, "WorkflowStateMachineArn", value=state_machine.state_machine_arn)
        CfnOutput(self, "WorkflowEventRuleName", value=workflow_trigger_rule.rule_name)
