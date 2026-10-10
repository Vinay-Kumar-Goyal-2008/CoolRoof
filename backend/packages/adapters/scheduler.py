"""Scheduler: local = APScheduler inside the API process; AWS = EventBridge.

On AWS the schedules themselves are declared in the CDK alerts stack and invoke
Lambda handlers directly, so ``EventBridgeScheduler`` only records registrations
(it lets the same wiring code run on both runtimes).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass

__all__ = ["APSchedulerLocal", "EventBridgeScheduler", "JobSpec", "Scheduler"]

Job = Callable[[], object]


@dataclass(frozen=True)
class JobSpec:
    name: str
    interval_minutes: int | None = None
    cron: str | None = None  # "min hour day month day_of_week"


class Scheduler(ABC):
    @abstractmethod
    def add(self, spec: JobSpec, job: Job) -> None: ...

    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def shutdown(self) -> None: ...

    @abstractmethod
    def jobs(self) -> list[JobSpec]: ...


class APSchedulerLocal(Scheduler):
    def __init__(self) -> None:
        from apscheduler.schedulers.background import BackgroundScheduler

        self._sched = BackgroundScheduler(timezone="UTC")
        self._specs: list[JobSpec] = []

    def add(self, spec: JobSpec, job: Job) -> None:
        from apscheduler.triggers.cron import CronTrigger

        if spec.interval_minutes:
            self._sched.add_job(
                job,
                "interval",
                minutes=spec.interval_minutes,
                id=spec.name,
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
        elif spec.cron:
            self._sched.add_job(
                job,
                CronTrigger.from_crontab(spec.cron),
                id=spec.name,
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
        else:
            raise ValueError(f"job {spec.name} needs interval_minutes or cron")
        self._specs.append(spec)

    def start(self) -> None:
        if not self._sched.running:
            self._sched.start()

    def shutdown(self) -> None:
        if self._sched.running:
            self._sched.shutdown(wait=False)

    def jobs(self) -> list[JobSpec]:
        return list(self._specs)


class EventBridgeScheduler(Scheduler):
    """Records job registrations; the CDK stack owns the real schedules."""

    def __init__(self) -> None:
        self._specs: list[JobSpec] = []

    def add(self, spec: JobSpec, job: Job) -> None:
        self._specs.append(spec)

    def start(self) -> None:
        return None

    def shutdown(self) -> None:
        return None

    def jobs(self) -> list[JobSpec]:
        return list(self._specs)
