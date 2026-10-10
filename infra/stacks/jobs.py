"""EventBridge schedules run the same backend image with handler `packages.api.scheduled.handler`.

Mirrors `register_jobs` locally: FIRMS poll (P-FIRE-POLL), daily heat-dome forecast 01:30 UTC, staleness flip 02:00 UTC.
"""

from __future__ import annotations

from aws_cdk import Duration, Stack
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from constructs import Construct

from stacks.alerts import AlertsStack
from stacks.api import grant_runtime, runtime_env
from stacks.common import backend_function, ctx, fire_poll_minutes
from stacks.data import DataStack


class JobsStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, *, data: DataStack, alerts: AlertsStack,
                 **kwargs: object) -> None:
        super().__init__(scope, construct_id, **kwargs)  # type: ignore[arg-type]
        self.fn = backend_function(self, "Jobs", handler="packages.api.scheduled.handler",
                                   environment=runtime_env(self, data), timeout=Duration.minutes(5))
        grant_runtime(self.fn, data=data, alerts=alerts, speech=False)
        city = ctx(self, "city", "mini_city")
        schedules = {
            "fire": events.Schedule.rate(Duration.minutes(fire_poll_minutes())),
            "heatdome": events.Schedule.cron(minute="30", hour="1"),
            "stale": events.Schedule.cron(minute="0", hour="2"),
        }
        for job, schedule in schedules.items():
            events.Rule(
                self, f"Rule{job}", rule_name=f"coolroof-{job}", schedule=schedule,
                targets=[targets.LambdaFunction(
                    self.fn, event=events.RuleTargetInput.from_object({"job": job, "city": city}),
                    retry_attempts=1)])
