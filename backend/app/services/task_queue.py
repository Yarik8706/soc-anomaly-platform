from __future__ import annotations

from redis import Redis
from rq import Queue

from app.core.config import settings


class TaskQueueError(RuntimeError):
    pass


def enqueue_run(run_id: str) -> str:
    from app.tasks import process_analysis_run

    try:
        connection = Redis.from_url(settings.redis_url)
        job = Queue(settings.analysis_queue, connection=connection).enqueue(
            process_analysis_run,
            run_id,
            job_timeout="2h",
            result_ttl=86_400,
            failure_ttl=604_800,
        )
    except Exception as exc:
        raise TaskQueueError("Analysis queue is unavailable") from exc
    return job.id
