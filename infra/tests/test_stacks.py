"""Synthesises every stack (no AWS account or Docker build needed) and checks the wiring the backend depends on."""

from __future__ import annotations

import sys
from pathlib import Path

import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Match, Template

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stacks.alerts import AlertsStack  # noqa: E402
from stacks.api import ApiStack  # noqa: E402
from stacks.auth import AuthStack  # noqa: E402
from stacks.data import DataStack  # noqa: E402
from stacks.jobs import JobsStack  # noqa: E402
from stacks.monitoring import MonitoringStack  # noqa: E402

ENV = cdk.Environment(account="123456789012", region="ap-south-1")


@pytest.fixture(scope="module")
def stacks() -> dict[str, Template]:
    app = cdk.App(context={"ops_email": "ops@example.com", "bedrock_model_id": "test-model",
                           "frontend_origin": "https://app.example.com"})
    data = DataStack(app, "D", env=ENV)
    alerts = AlertsStack(app, "A", env=ENV)
    auth = AuthStack(app, "U", env=ENV)
    api = ApiStack(app, "P", env=ENV, data=data, alerts=alerts, auth=auth)
    jobs = JobsStack(app, "J", env=ENV, data=data, alerts=alerts)
    mon = MonitoringStack(app, "M", env=ENV, api=api, jobs=jobs)
    return {k: Template.from_stack(s) for k, s in
            {"alerts": alerts, "auth": auth, "api": api, "jobs": jobs, "mon": mon}.items()}


def test_secret_is_named_for_the_backend_and_holds_the_sns_prefix(stacks: dict[str, Template]) -> None:
    stacks["alerts"].has_resource_properties("AWS::SecretsManager::Secret", {
        "Name": "coolroof/app",
        "GenerateSecretString": Match.object_like({"GenerateStringKey": "PLANNER_API_KEY"})})


def test_topics_follow_the_notifier_naming(stacks: dict[str, Template]) -> None:
    names = {r["Properties"]["TopicName"] for r in stacks["alerts"].find_resources("AWS::SNS::Topic").values()}
    assert names == {"coolroof-mini_city-staff", "coolroof-mini_city-public"}


def test_api_lambda_has_runtime_env_and_cognito(stacks: dict[str, Template]) -> None:
    env = next(iter(stacks["api"].find_resources("AWS::Lambda::Function").values()))["Properties"]["Environment"]["Variables"]
    for key in ("RUNTIME", "S3_BUCKET", "DYNAMODB_TABLE_PREFIX", "SNS_TOPIC_PREFIX", "COGNITO_ISSUER",
                "COGNITO_CLIENT_ID", "BEDROCK_MODEL_ID", "FRONTEND_ORIGIN"):
        assert key in env, key
    assert env["RUNTIME"] == "aws" and env["BEDROCK_MODEL_ID"] == "test-model"


def test_api_can_read_the_secret_speak_and_call_bedrock(stacks: dict[str, Template]) -> None:
    # CDK moves overflow statements of a large role policy into an AWS::IAM::ManagedPolicy.
    policies = {**stacks["api"].find_resources("AWS::IAM::Policy"),
                **stacks["api"].find_resources("AWS::IAM::ManagedPolicy")}
    actions = {a for p in policies.values()
               for s in p["Properties"]["PolicyDocument"]["Statement"]
               for a in ([s["Action"]] if isinstance(s["Action"], str) else s["Action"])}
    assert {"secretsmanager:GetSecretValue", "sns:Publish", "polly:SynthesizeSpeech",
            "bedrock:InvokeModel"} <= actions


def test_jobs_use_the_scheduled_handler_and_three_rules(stacks: dict[str, Template]) -> None:
    stacks["jobs"].has_resource_properties(
        "AWS::Lambda::Function", {"ImageConfig": {"Command": ["packages.api.scheduled.handler"]}})
    rules = stacks["jobs"].find_resources("AWS::Events::Rule")
    assert {r["Properties"]["Name"] for r in rules.values()} == {
        "coolroof-fire", "coolroof-heatdome", "coolroof-stale"}


def test_cognito_has_the_two_groups_the_backend_maps(stacks: dict[str, Template]) -> None:
    groups = {r["Properties"]["GroupName"] for r in stacks["auth"].find_resources("AWS::Cognito::UserPoolGroup").values()}
    assert groups == {"planner", "admin"}


def test_monitoring_has_alarms_and_budget(stacks: dict[str, Template]) -> None:
    stacks["mon"].resource_count_is("AWS::CloudWatch::Alarm", 3)
    stacks["mon"].resource_count_is("AWS::Budgets::Budget", 1)
