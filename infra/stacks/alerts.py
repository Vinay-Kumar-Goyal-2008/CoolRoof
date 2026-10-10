"""SNS topics for alert delivery and the one Secrets Manager secret the backend reads (`coolroof/app`)."""

from __future__ import annotations

import json

from aws_cdk import CfnOutput, Stack
from aws_cdk import aws_secretsmanager as sm
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sns_subscriptions as subs
from constructs import Construct

from stacks.common import ctx
from stacks.data import PREFIX

AUDIENCES = ("staff", "public")


class AlertsStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs: object) -> None:
        super().__init__(scope, construct_id, **kwargs)  # type: ignore[arg-type]
        city = ctx(self, "city", "mini_city")
        # Topic name = `<prefix>-<city>-<audience>`; SNSNotifier builds the same ARN from SNS_ARN_PREFIX.
        self.topics = {a: sns.Topic(self, f"Topic{a}", topic_name=f"{PREFIX}-{city}-{a}") for a in AUDIENCES}
        ops_email = ctx(self, "ops_email")
        if ops_email:  # the owner confirms the subscription from their inbox
            self.topics["staff"].add_subscription(subs.EmailSubscription(ops_email))

        # PLANNER_API_KEY is generated. ADMIN_API_KEY, DEEPGRAM_API_KEY and FIRMS_MAP_KEY start empty
        # (admin routes stay disabled until you set one): fill them in the Secrets Manager console.
        self.secret = sm.Secret(
            self, "AppSecret", secret_name=f"{PREFIX}/app",
            description="CoolRoof runtime secrets (JSON): API keys and the SNS ARN prefix",
            generate_secret_string=sm.SecretStringGenerator(
                secret_string_template=json.dumps({
                    "SNS_ARN_PREFIX": f"arn:aws:sns:{self.region}:{self.account}",
                    "ADMIN_API_KEY": "", "DEEPGRAM_API_KEY": "", "FIRMS_MAP_KEY": ""}),
                generate_string_key="PLANNER_API_KEY", exclude_punctuation=True, password_length=40),
        )
        CfnOutput(self, "SecretName", value=self.secret.secret_name)
        for audience, topic in self.topics.items():
            CfnOutput(self, f"Topic{audience.title()}Arn", value=topic.topic_arn)
