"""Cognito user pool for planner/admin sign-in (spec: Phase 2; API keys remain the demo fallback).

The backend maps the `planner` and `admin` groups to roles (`packages/api/auth.py`).
"""

from __future__ import annotations

from aws_cdk import CfnOutput, RemovalPolicy, Stack
from aws_cdk import aws_cognito as cognito
from constructs import Construct


class AuthStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs: object) -> None:
        super().__init__(scope, construct_id, **kwargs)  # type: ignore[arg-type]
        self.pool = cognito.UserPool(
            self, "Pool", user_pool_name="coolroof-staff", self_sign_up_enabled=False,
            sign_in_aliases=cognito.SignInAliases(email=True),
            password_policy=cognito.PasswordPolicy(min_length=12, require_symbols=True),
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,
            removal_policy=RemovalPolicy.RETAIN,
        )
        for group in ("planner", "admin"):
            cognito.CfnUserPoolGroup(self, f"Group{group}", user_pool_id=self.pool.user_pool_id, group_name=group)
        self.client = self.pool.add_client(
            "WebClient", generate_secret=False,
            auth_flows=cognito.AuthFlow(user_srp=True, user_password=True))
        self.issuer = f"https://cognito-idp.{self.region}.amazonaws.com/{self.pool.user_pool_id}"
        CfnOutput(self, "Issuer", value=self.issuer)
        CfnOutput(self, "ClientId", value=self.client.user_pool_client_id)
