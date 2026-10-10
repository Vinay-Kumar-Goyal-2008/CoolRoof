"""API Gateway (REST) → Lambda container (FastAPI via Mangum) with the grants the backend needs."""

from __future__ import annotations

from aws_cdk import CfnOutput, Duration, Stack
from aws_cdk import aws_apigateway as apigw
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as _lambda
from constructs import Construct

from stacks.alerts import AlertsStack
from stacks.auth import AuthStack
from stacks.common import backend_function, bedrock_policy, ctx, data_source_env
from stacks.data import PREFIX, DataStack


def grant_runtime(fn: _lambda.IFunction, *, data: DataStack, alerts: AlertsStack, speech: bool) -> None:
    """Everything the backend touches at runtime: S3, DynamoDB, the secret, SNS and (API only) Polly/Bedrock."""
    data.bucket.grant_read_write(fn)
    for table in data.tables.values():
        table.grant_read_write_data(fn)
    alerts.secret.grant_read(fn)
    for topic in alerts.topics.values():
        topic.grant_publish(fn)
    if speech:
        fn.add_to_role_policy(iam.PolicyStatement(actions=["polly:SynthesizeSpeech"], resources=["*"]))
        fn.add_to_role_policy(bedrock_policy())


def runtime_env(stack: Stack, data: DataStack) -> dict[str, str]:
    # Lambda sets AWS_REGION itself, which is what settings.aws_region (and boto3) read.
    return {
        "RUNTIME": "aws", "S3_BUCKET": data.bucket.bucket_name, "DYNAMODB_TABLE_PREFIX": PREFIX,
        "SNS_TOPIC_PREFIX": PREFIX, "CITY": ctx(stack, "city", "mini_city"),
        **data_source_env(ctx(stack, "data_sources", "fixture")),
    }


class ApiStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, *, data: DataStack, alerts: AlertsStack,
                 auth: AuthStack | None = None, **kwargs: object) -> None:
        super().__init__(scope, construct_id, **kwargs)  # type: ignore[arg-type]
        env = {
            **runtime_env(self, data),
            "BEDROCK_MODEL_ID": ctx(self, "bedrock_model_id"),
            "FRONTEND_ORIGIN": ctx(self, "frontend_origin", "*"),
        }
        if auth is not None:
            env["COGNITO_ISSUER"] = auth.issuer
            env["COGNITO_CLIENT_ID"] = auth.client.user_pool_client_id
        # 29 s is API Gateway's integration limit.
        self.fn = backend_function(self, "Api", handler="packages.api.app.handler", environment=env,
                                   timeout=Duration.seconds(29))
        grant_runtime(self.fn, data=data, alerts=alerts, speech=True)
        self.api = apigw.LambdaRestApi(
            self, "Gateway", handler=self.fn, proxy=True,
            deploy_options=apigw.StageOptions(throttling_rate_limit=20, throttling_burst_limit=40))
        CfnOutput(self, "ApiUrl", value=self.api.url)
