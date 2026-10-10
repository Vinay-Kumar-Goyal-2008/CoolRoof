"""S3 bucket and DynamoDB tables (spec §M40). One table per logical table, plus gsi1."""

from aws_cdk import Duration, RemovalPolicy, Stack
from aws_cdk import aws_dynamodb as ddb
from aws_cdk import aws_s3 as s3
from constructs import Construct

PREFIX = "coolroof"
TABLES = ("ward_context", "roof_context", "policy", "config", "session", "cache", "alerts",
          "advisories", "subscriptions", "forecasts", "environment", "runs")
PITR_TABLES = {"ward_context", "roof_context", "policy", "config"}


class DataStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs: object) -> None:
        super().__init__(scope, construct_id, **kwargs)  # type: ignore[arg-type]
        self.bucket = s3.Bucket(
            self, "Data", encryption=s3.BucketEncryption.S3_MANAGED, enforce_ssl=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL, versioned=True,
            removal_policy=RemovalPolicy.RETAIN,
            lifecycle_rules=[s3.LifecycleRule(  # PDFs expire after 7 days (privacy)
                prefix="exports/pdf/", expiration=Duration.days(7))],
        )
        self.tables: dict[str, ddb.Table] = {}
        for name in TABLES:
            table = ddb.Table(
                self, f"T{name}", table_name=f"{PREFIX}-{name}",
                partition_key=ddb.Attribute(name="pk", type=ddb.AttributeType.STRING),
                sort_key=ddb.Attribute(name="sk", type=ddb.AttributeType.STRING),
                billing_mode=ddb.BillingMode.PAY_PER_REQUEST, time_to_live_attribute="expires_at",
                point_in_time_recovery=name in PITR_TABLES,
                removal_policy=RemovalPolicy.RETAIN if name in PITR_TABLES else RemovalPolicy.DESTROY,
            )
            table.add_global_secondary_index(
                index_name="gsi1",
                partition_key=ddb.Attribute(name="gsi1pk", type=ddb.AttributeType.STRING),
                sort_key=ddb.Attribute(name="gsi1sk", type=ddb.AttributeType.STRING))
            self.tables[name] = table

