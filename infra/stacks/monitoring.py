"""CloudWatch alarms (API and job errors, API 5XX) and an AWS Budget.

Pass `-c ops_email=you@example.com` so someone is notified; without it the alarms still exist and the budget is skipped.
"""

from __future__ import annotations

from aws_cdk import Duration, Stack
from aws_cdk import aws_budgets as budgets
from aws_cdk import aws_cloudwatch as cw
from aws_cdk import aws_cloudwatch_actions as cw_actions
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sns_subscriptions as subs
from constructs import Construct

from stacks.api import ApiStack
from stacks.common import ctx
from stacks.jobs import JobsStack


class MonitoringStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, *, api: ApiStack, jobs: JobsStack,
                 **kwargs: object) -> None:
        super().__init__(scope, construct_id, **kwargs)  # type: ignore[arg-type]
        ops_email = ctx(self, "ops_email")
        topic = sns.Topic(self, "OpsTopic", topic_name="coolroof-ops")
        if ops_email:
            topic.add_subscription(subs.EmailSubscription(ops_email))
        action = cw_actions.SnsAction(topic)

        alarms = {
            "ApiErrors": api.fn.metric_errors(period=Duration.minutes(5), statistic="Sum"),
            "JobErrors": jobs.fn.metric_errors(period=Duration.minutes(15), statistic="Sum"),
            "Api5xx": api.api.metric_server_error(period=Duration.minutes(5), statistic="Sum"),
        }
        for name, metric in alarms.items():
            cw.Alarm(self, name, metric=metric, threshold=1, evaluation_periods=1,
                     comparison_operator=cw.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
                     treat_missing_data=cw.TreatMissingData.NOT_BREACHING).add_alarm_action(action)

        if ops_email:  # a budget needs at least one subscriber
            limit = float(ctx(self, "monthly_budget_usd", "50"))
            budgets.CfnBudget(
                self, "Budget",
                budget=budgets.CfnBudget.BudgetDataProperty(
                    budget_name="coolroof-monthly", budget_type="COST", time_unit="MONTHLY",
                    budget_limit=budgets.CfnBudget.SpendProperty(amount=limit, unit="USD")),
                notifications_with_subscribers=[
                    budgets.CfnBudget.NotificationWithSubscribersProperty(
                        notification=budgets.CfnBudget.NotificationProperty(
                            notification_type="ACTUAL", comparison_operator="GREATER_THAN",
                            threshold=pct, threshold_type="PERCENTAGE"),
                        subscribers=[budgets.CfnBudget.SubscriberProperty(
                            subscription_type="EMAIL", address=ops_email)])
                    for pct in (50, 80, 100)])
