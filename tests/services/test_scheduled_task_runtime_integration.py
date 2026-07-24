"""Runtime scheduler ownership tests for persisted scheduled tasks."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from src.services.runtime_scheduler import RuntimeSchedulerService


class NoopThread:
    def __init__(self, target=None, **_kwargs):
        self.target = target

    def start(self):
        return None


class FakeScheduleModule:
    @staticmethod
    def get_jobs():
        return []


class FakeScheduler:
    instances = []

    def __init__(self, **_kwargs):
        self.daily_tasks = []
        self.background_tasks = []
        self.schedule = FakeScheduleModule()
        self.stopped = False
        self.__class__.instances.append(self)

    def set_daily_task(self, task, run_immediately):
        self.daily_tasks.append((task, run_immediately))

    def add_background_task(self, task, interval_seconds, run_immediately, name):
        self.background_tasks.append(
            {
                "task": task,
                "interval_seconds": interval_seconds,
                "run_immediately": run_immediately,
                "name": name,
            }
        )

    def run(self):
        return None

    def stop(self):
        self.stopped = True


class FakeScheduledTaskService:
    def __init__(self):
        self.enabled = True
        self.ticks = 0

    def has_enabled_tasks(self):
        return self.enabled

    def tick(self):
        self.ticks += 1


def test_personalized_tasks_use_existing_runtime_loop_without_legacy_daily_job() -> None:
    FakeScheduler.instances = []
    config = SimpleNamespace(
        schedule_enabled=False,
        schedule_time="18:00",
        schedule_times=["18:00"],
    )
    scheduled_tasks = FakeScheduledTaskService()
    service = RuntimeSchedulerService(
        config_provider=lambda: config,
        scheduled_task_service=scheduled_tasks,
    )

    with patch(
        "src.services.runtime_scheduler.Scheduler",
        FakeScheduler,
    ), patch(
        "src.services.runtime_scheduler.threading.Thread",
        NoopThread,
    ):
        service.reconcile_scheduled_tasks()
        scheduler = FakeScheduler.instances[-1]
        assert scheduler.daily_tasks == []
        assert [item["name"] for item in scheduler.background_tasks] == [
            "scheduled_tasks"
        ]
        assert service.status()["enabled"] is False

        scheduled_tasks.enabled = False
        service.reconcile_scheduled_tasks()

    assert scheduler.stopped is True
