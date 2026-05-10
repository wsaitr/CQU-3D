"""Dispatcher 服务：任务派发、并发控制、重试与心跳监控。"""

import asyncio
import logging
from pathlib import Path

from packages.shared.config import settings
from packages.shared.database import AsyncSessionLocal, init_models
from packages.shared.repository import (
    bump_retry_count,
    count_running_tasks,
    get_task_by_id,
    is_timed_out,
    list_dispatchable_tasks,
    list_retryable_failed_tasks,
    list_running_tasks,
    update_task_status,
)
from packages.shared.task_queue import TaskQueue
from packages.shared.task_status import FINAL_STATUSES
from packages.shared.utils import dump_json, now_utc_iso

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [dispatcher] %(message)s",
)
logger = logging.getLogger("dispatcher")

DISPATCHER_HEARTBEAT_FILE = Path(settings.log_dir_path) / "dispatcher" / "heartbeat.json"


def _touch_dispatcher_heartbeat() -> None:
    DISPATCHER_HEARTBEAT_FILE.parent.mkdir(parents=True, exist_ok=True)
    dump_json(
        DISPATCHER_HEARTBEAT_FILE,
        {
            "service": "dispatcher",
            "status": "running",
            "ts": now_utc_iso(),
            "incoming_queue": settings.task_incoming_queue,
            "ready_queue": settings.task_ready_queue,
        },
    )


async def _reconcile_dispatchable_tasks(queue: TaskQueue, reason: str, limit: int = 500) -> int:
    """将 DB 中 PENDING/QUEUED 任务补入 incoming 队列，防止重启后假死。"""
    async with AsyncSessionLocal() as session:
        tasks = await list_dispatchable_tasks(session, limit=limit)

    enqueued = 0
    dedupe_ttl = max(30, settings.dispatcher_monitor_interval * 3)
    for task in tasks:
        dedupe_key = f"{settings.task_dispatch_lock_prefix}:reconcile:{task.id}"
        # 使用短 TTL 去重，避免每轮都重复压入同一任务导致队列膨胀。
        if not await queue.acquire_lock(dedupe_key, ttl=dedupe_ttl):
            continue
        await queue.enqueue_incoming(task.id, attempt=task.retry_count)
        enqueued += 1

    if enqueued > 0:
        logger.warning("%s：补入 incoming 队列 %s 个任务", reason, enqueued)
    else:
        logger.info("%s：无需补队列", reason)
    return enqueued


async def dispatch_once(queue: TaskQueue) -> None:
    message = await queue.pop_incoming(timeout=settings.dispatcher_poll_timeout)
    if message is None:
        return

    lock_key = queue.dispatch_lock_key(message.task_id)
    locked = await queue.acquire_lock(lock_key, ttl=max(30, settings.dispatcher_poll_timeout * 2))
    if not locked:
        return

    try:
        async with AsyncSessionLocal() as session:
            task = await get_task_by_id(session, message.task_id)
            if task is None:
                logger.warning("任务不存在，跳过派发: task_id=%s", message.task_id)
                return

            if task.status in FINAL_STATUSES:
                logger.info("任务已终态，跳过派发: task_id=%s status=%s", task.id, task.status)
                return

            if task.cancel_requested:
                await update_task_status(session, task.id, "CANCELED", task.progress, error_message="任务已取消")
                logger.info("任务已取消，跳过派发: task_id=%s", task.id)
                return

            running_count = await count_running_tasks(session)
            if running_count >= settings.dispatcher_max_inflight:
                await queue.enqueue_incoming(task.id, attempt=task.retry_count)
                logger.info("并发已满，任务重新入队: task_id=%s running=%s", task.id, running_count)
                return

            await update_task_status(session, task.id, "QUEUED", max(task.progress, 1))
            await queue.enqueue_ready(task.id, attempt=task.retry_count)
            logger.info("任务派发到 ready 队列: task_id=%s attempt=%s", task.id, task.retry_count)
    finally:
        await queue.release_lock(lock_key)


async def monitor_loop(queue: TaskQueue) -> None:
    while True:
        await asyncio.sleep(max(3, settings.dispatcher_monitor_interval))
        try:
            async with AsyncSessionLocal() as session:
                running_tasks = await list_running_tasks(session)
                for task in running_tasks:
                    if task.cancel_requested:
                        await update_task_status(
                            session,
                            task.id,
                            "CANCELED",
                            task.progress,
                            error_message="用户请求取消任务",
                            worker_id=task.worker_id,
                        )
                        logger.info("运行中任务已标记取消: task_id=%s", task.id)
                        continue

                    heartbeat = await queue.get_heartbeat(task.id)
                    if heartbeat is not None:
                        await update_task_status(
                            session,
                            task.id,
                            task.status,
                            task.progress,
                            error_message=task.error_message,
                            output_path=task.output_path,
                            preview_path=task.preview_path,
                            log_path=task.log_path,
                            result_meta_path=task.result_meta_path,
                            worker_id=task.worker_id,
                            heartbeat=True,
                        )
                        continue

                    if not is_timed_out(task, settings.task_heartbeat_timeout):
                        continue

                    reason = "任务心跳超时，dispatcher 判定失活"
                    # 任务被判定超时后，先清理心跳和 worker 锁，避免重试消息被旧锁拦截。
                    await queue.release_lock(queue.worker_lock_key(task.id))
                    if task.retry_count < task.max_retries:
                        updated = await bump_retry_count(session, task.id)
                        retry_no = updated.retry_count if updated else task.retry_count + 1
                        await update_task_status(
                            session,
                            task.id,
                            "QUEUED",
                            min(task.progress, 95),
                            error_message=f"{reason}，准备第 {retry_no} 次重试",
                        )
                        await queue.enqueue_incoming(task.id, attempt=retry_no)
                        logger.warning("任务超时后重试入队: task_id=%s retry=%s", task.id, retry_no)
                    else:
                        await update_task_status(
                            session,
                            task.id,
                            "FAILED",
                            min(task.progress, 99),
                            error_message=f"{reason}，超过最大重试次数",
                        )
                        logger.error("任务超时且重试耗尽: task_id=%s", task.id)

                failed = await list_retryable_failed_tasks(session)
                for task in failed:
                    if task.error_message and "[RETRY_QUEUED]" in task.error_message:
                        continue

                    updated = await bump_retry_count(session, task.id)
                    retry_no = updated.retry_count if updated else task.retry_count + 1
                    message = f"任务失败后自动重试 [RETRY_QUEUED] 第 {retry_no} 次"
                    await update_task_status(
                        session,
                        task.id,
                        "QUEUED",
                        min(task.progress, 95),
                        error_message=message,
                    )
                    await queue.enqueue_incoming(task.id, attempt=retry_no)
                    logger.warning("失败任务重试入队: task_id=%s retry=%s", task.id, retry_no)
        except Exception:
            logger.exception("监控循环异常")
            await asyncio.sleep(1)


async def dispatch_loop(queue: TaskQueue) -> None:
    while True:
        try:
            await dispatch_once(queue)
        except Exception:
            logger.exception("派发循环异常")
            await asyncio.sleep(1)


async def reconcile_loop(queue: TaskQueue) -> None:
    interval = max(20, settings.dispatcher_monitor_interval * 2)
    while True:
        await asyncio.sleep(interval)
        try:
            await _reconcile_dispatchable_tasks(queue, reason="周期对账")
        except Exception:
            logger.exception("周期对账异常")
            await asyncio.sleep(1)


async def dispatcher_heartbeat_loop() -> None:
    while True:
        try:
            _touch_dispatcher_heartbeat()
        except Exception:
            logger.exception("写入 dispatcher 心跳失败")
        await asyncio.sleep(10)


async def main() -> None:
    settings.ensure_storage_dirs()

    while True:
        try:
            await init_models()
            break
        except Exception:
            logger.exception("dispatcher 初始化数据库失败，5 秒后重试")
            await asyncio.sleep(5)

    queue = TaskQueue()
    logger.info("dispatcher 启动: incoming=%s ready=%s", settings.task_incoming_queue, settings.task_ready_queue)
    try:
        await _reconcile_dispatchable_tasks(queue, reason="dispatcher 启动对账")
        await asyncio.gather(
            dispatch_loop(queue),
            monitor_loop(queue),
            reconcile_loop(queue),
            dispatcher_heartbeat_loop(),
        )
    finally:
        await queue.close()


if __name__ == "__main__":
    asyncio.run(main())
