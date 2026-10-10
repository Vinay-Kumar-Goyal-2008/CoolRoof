"""API Gateway (REST) → Lambda container (FastAPI via Mangum) with Bedrock access for the agent."""

from pathlib import Path

from aws_cdk import CfnOutput, Duration, Stack
from aws_cdk import aws_apigateway as apigw
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as _lambda
from constructs import Construct

from stacks.data import PREFIX, DataStack

BACKEND = Path(__file__).resolve().parents[2] / "backend"


class ApiStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, *, data: DataStack, **kwargs: object):
        super().__init__(scope, construct_id, **kwargs)  # type: ignore[arg-type]
        fn = _lambda.DockerImageFunction(
            self, "Api",
            code=_lambda.DockerImageCode.from_image_asset(
                str(BACKEND),
                file="Dockerfile.lambda",
                exclude=[".venv", "data", "__pycache__", "**/__pycache__", ".*_cache",
                         ".hypothesis", "tests/unit", "tests/e2e", "tests/property",
                         "tests/golden", "assets/fonts/*.ttc"],
            ),
            memory_size=2048, timeout=Duration.seconds(29),  # API Gateway's limit
            environment={
                "RUNTIME": "aws", "S3_BUCKET": data.bucket.bucket_name,
                "DYNAMODB_TABLE_PREFIX": PREFIX, "CITY": "mini_city",
                "BEDROCK_MODEL_ID": self.node.try_get_context("bedrock_model_id") or "",
                "FRONTEND_ORIGIN": self.node.try_get_context("frontend_origin") or "*",
            },
        )
        data.bucket.grant_read_write(fn)
        for table in data.tables.values():
            table.grant_read_write_data(fn)
        fn.add_to_role_policy(iam.PolicyStatement(
            actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
            resources=["*"]))
        api = apigw.LambdaRestApi(
            self, "Gateway", handler=fn, proxy=True,
            deploy_options=apigw.StageOptions(throttling_rate_limit=20, throttling_burst_limit=40))
        CfnOutput(self, "ApiUrl", value=api.url)
