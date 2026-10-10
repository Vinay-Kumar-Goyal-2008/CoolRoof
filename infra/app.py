#!/usr/bin/env python3
"""CDK entry point: `cdk deploy --all` deploys data, alerts, auth, API, jobs and monitoring.

Optional context (`-c key=value`): city, bedrock_model_id, frontend_origin, ops_email,
monthly_budget_usd, data_sources=fixture|live. See infra/README.md.
"""

import os

import aws_cdk as cdk

from stacks.alerts import AlertsStack
from stacks.api import ApiStack
from stacks.auth import AuthStack
from stacks.data import DataStack
from stacks.jobs import JobsStack
from stacks.monitoring import MonitoringStack

app = cdk.App()
env = cdk.Environment(account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
                      region=os.environ.get("CDK_DEFAULT_REGION", "ap-south-1"))
data = DataStack(app, "CoolRoofDataStack", env=env)
alerts = AlertsStack(app, "CoolRoofAlertsStack", env=env)
auth = AuthStack(app, "CoolRoofAuthStack", env=env)
api = ApiStack(app, "CoolRoofApiStack", env=env, data=data, alerts=alerts, auth=auth)
jobs = JobsStack(app, "CoolRoofJobsStack", env=env, data=data, alerts=alerts)
MonitoringStack(app, "CoolRoofMonitoringStack", env=env, api=api, jobs=jobs)
app.synth()
