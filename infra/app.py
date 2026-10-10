#!/usr/bin/env python3
"""CDK entry point: `cdk deploy --all` deploys the data and API stacks."""

import os

import aws_cdk as cdk

from stacks.api import ApiStack
from stacks.data import DataStack

app = cdk.App()
env = cdk.Environment(account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
                      region=os.environ.get("CDK_DEFAULT_REGION", "ap-south-1"))
data = DataStack(app, "CoolRoofDataStack", env=env)
ApiStack(app, "CoolRoofApiStack", env=env, data=data)
app.synth()
