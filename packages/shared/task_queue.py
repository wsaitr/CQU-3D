"""Redis 队列与分布式锁封装。"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from redis.asyncio import Redis

from packages.shared.config import settings

logger = logging.getLogger("task_queue")


@dataclass
class TaskMessage:
    task_id: int
    attempt: int = 0

    def dumps(self) -> str:
        return json.dumps({"task_id": self.task_id, "attempt": self.attempt}, ensure_ascii=False)

    @classmethod
    def loads(cls, raw: str) -> "TaskMessage":
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            # 兼容误写入的转义 JSON，例如 {\"task_id\":3,\"attempt\":1}
            payload = json.loads(raw.replace('\\"', '"'))
        return cls(task_id=int(payload["task_id"]), attempt=int(payload.get("attempt", 0)))


class TaskQueue:
    def __init__(self, redis_url: str | None = None):
        self.redis = Redis.from_url(redis_url or settings.redis_url, decode_responses=True)

    async def close(self) -> None:
        await self.redis.aclose()

    async def enqueue_incoming(self, task_id: int, attempt: int = 0) -> None:
        message = TaskMessage(task_id=task_id, attempt=attempt)
        await self.redis.lpush(settings.task_incoming_queue, message.dumps())

    async def enqueue_ready(self, task_id: int, attempt: int = 0) -> None:
        message = TaskMessage(task_id=task_id, attempt=attempt)
        await self.redis.lpush(settings.task_ready_queue, message.dumps())

    async def pop_incoming(self, timeout: int | None = None) -> TaskMessage | None:
        result = await self.redis.brpop(settings.task_incoming_queue, timeout=timeout or settings.dispatcher_poll_timeout)
        if not result:
            return None
        _, raw = result
        try:
            return TaskMessage.loads(raw)
        except Exception:
            logger.warning("忽略非法 incoming 队列消息: %r", raw, exc_info=True)
            return None

    async def pop_ready(self, timeout: int | None = None) -> TaskMessage | None:
        result = await self.redis.brpop(settings.task_ready_queue, timeout=timeout or settings.worker_poll_timeout)
        if not result:
            return None
        _, raw = result
        try:
            return TaskMessage.loads(raw)
        except Exception:
            logger.warning("忽略非法 ready 队列消息: %r", raw, exc_info=True)
            return None

    def heartbeat_key(self, task_id: int) -> str:
        return f"{settings.task_heartbeat_prefix}:{task_id}"

    def dispatch_lock_key(self, task_id: int) -> str:
        return f"{settings.task_dispatch_lock_prefix}:{task_id}"

    def worker_lock_key(self, task_id: int) -> str:
        return f"{settings.task_worker_lock_prefix}:{task_id}"

    async def touch_heartbeat(self, task_id: int, worker_id: str, ttl: int | None = None) -> None:
        payload = {
            "worker_id": worker_id,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        await self.redis.set(
            self.heartbeat_key(task_id),
            json.dumps(payload, ensure_ascii=False),
            ex=ttl or settings.task_heartbeat_timeout,
        )

    async def get_heartbeat(self, task_id: int) -> dict | None:
        raw = await self.redis.get(self.heartbeat_key(task_id))
        if not raw:
            return None
        return json.loads(raw)

    async def acquire_lock(self, lock_key: str, ttl: int) -> bool:
        return bool(await self.redis.set(lock_key, "1", nx=True, ex=max(1, ttl)))

    async def release_lock(self, lock_key: str) -> None:
        await self.redis.delete(lock_key)
