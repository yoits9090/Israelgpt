"""Redis-backed task queue used by the gateway/worker architecture."""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional

from redis.asyncio import Redis

# Defaults are environment-driven to support container overrides.
DEFAULT_REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
DEFAULT_NAMESPACE = os.getenv("TASK_NAMESPACE", "guildest")
DEFAULT_QUEUE_KEY = f"{DEFAULT_NAMESPACE}:tasks"
DEFAULT_RESULT_PREFIX = f"{DEFAULT_NAMESPACE}:results:"


@dataclass
class QueueTask:
    job_id: str
    job_type: str
    payload: Dict[str, Any]
    requested_by: Optional[int | str] = None
    result_ttl: int = 120


class RedisTaskQueue:
    """Minimal Redis-based task queue with per-job result channels."""

    def __init__(
        self,
        redis_url: str = DEFAULT_REDIS_URL,
        queue_key: str = DEFAULT_QUEUE_KEY,
        result_prefix: str = DEFAULT_RESULT_PREFIX,
    ) -> None:
        self.redis = Redis.from_url(redis_url, decode_responses=True)
        self.queue_key = queue_key
        self.result_prefix = result_prefix

    def _result_key(self, job_id: str) -> str:
        return f"{self.result_prefix}{job_id}"

    async def enqueue(
        self,
        job_type: str,
        payload: Dict[str, Any],
        *,
        requested_by: Optional[int | str] = None,
        result_ttl: int = 120,
    ) -> QueueTask:
        job_id = str(uuid.uuid4())
        task = QueueTask(
            job_id=job_id,
            job_type=job_type,
            payload=payload,
            requested_by=requested_by,
            result_ttl=result_ttl,
        )
        await self.redis.rpush(self.queue_key, json.dumps(task.__dict__))
        return task

    async def pop(self, timeout: int = 5) -> Optional[QueueTask]:
        item = await self.redis.blpop(self.queue_key, timeout=timeout)
        if item is None:
            return None

        _, raw = item
        data = json.loads(raw)
        return QueueTask(
            job_id=data["job_id"],
            job_type=data["job_type"],
            payload=data.get("payload", {}),
            requested_by=data.get("requested_by"),
            result_ttl=int(data.get("result_ttl", 120)),
        )

    async def publish_result(self, job_id: str, result: Dict[str, Any], *, ttl: int = 300) -> None:
        key = self._result_key(job_id)
        await self.redis.rpush(key, json.dumps(result))
        await self.redis.expire(key, ttl)

    async def wait_for_result(self, job_id: str, *, timeout: int = 60) -> Dict[str, Any]:
        key = self._result_key(job_id)
        result = await self.redis.blpop(key, timeout=timeout)
        if result is None:
            raise asyncio.TimeoutError(f"Timed out waiting for result for job {job_id}")
        _, raw = result
        return json.loads(raw)


_queue: Optional[RedisTaskQueue] = None


def get_task_queue() -> RedisTaskQueue:
    """Return a singleton RedisTaskQueue instance."""
    global _queue
    if _queue is None:
        _queue = RedisTaskQueue()
    return _queue
