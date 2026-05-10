"""Worker 服务：消费任务并调用 dynamic-2dgs。"""

import asyncio
import logging
import shutil
import zipfile
from pathlib import Path

from apps.worker.core_engine.gs_runner import GSRunner
from packages.shared.config import settings
from packages.shared.database import AsyncSessionLocal, init_models
from packages.shared.repository import get_task_by_id, update_task_status
from packages.shared.storage import (
    build_task_log_dir,
    build_task_output_dir,
    build_task_workspace_dir,
    reset_dir,
)
from packages.shared.task_queue import TaskMessage, TaskQueue
from packages.shared.task_status import FINAL_STATUSES
from packages.shared.utils import dump_json, now_utc_iso

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [worker] %(message)s",
)
logger = logging.getLogger("worker")

WORKER_HEARTBEAT_FILE = Path(settings.log_dir_path) / "workers" / f"{settings.worker_id}.heartbeat.json"

VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".flv"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}


def _stage_from_message(message: str) -> str:
    text = message.lower()
    if "preparing input" in text or "colmap" in text or "ffmpeg" in text:
        return "PREPROCESSING"
    if "training" in text:
        return "TRAINING_3DGS"
    if "mesh" in text:
        return "TRAINING_MESH"
    if "packaging" in text or "export" in text:
        return "EXPORTING"
    return "RUNNING"


def _pick_preview(output_dir: Path) -> str | None:
    pngs = sorted(output_dir.glob("preview/**/*.png"))
    if pngs:
        return str(pngs[0])
    return None


def _extract_and_organize_archive(archive_path: Path, output_dir: Path) -> dict[str, str | None]:
    extract_dir = output_dir / "extracted"
    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    extract_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(archive_path, "r") as archive:
        archive.extractall(extract_dir)

    gs_src = extract_dir / "gaussian"
    mesh_src = extract_dir / "mesh"
    preview_src = extract_dir / "preview"

    gs_dst = output_dir / "3dgs"
    mesh_dst = output_dir / "mesh"
    preview_dst = output_dir / "preview"

    if gs_dst.exists():
        shutil.rmtree(gs_dst)
    if mesh_dst.exists():
        shutil.rmtree(mesh_dst)
    if preview_dst.exists():
        shutil.rmtree(preview_dst)

    if gs_src.exists():
        shutil.copytree(gs_src, gs_dst)
    if mesh_src.exists():
        shutil.copytree(mesh_src, mesh_dst)
    if preview_src.exists():
        shutil.copytree(preview_src, preview_dst)

    return {
        "three_dgs_dir": str(gs_dst) if gs_dst.exists() else None,
        "mesh_dir": str(mesh_dst) if mesh_dst.exists() else None,
        "preview_dir": str(preview_dst) if preview_dst.exists() else None,
    }


def _materialize_input(task_source: Path, assets_dir: Path) -> None:
    assets_dir.mkdir(parents=True, exist_ok=True)

    if task_source.is_file():
        target = assets_dir / task_source.name
        shutil.copy2(task_source, target)
        return

    if task_source.is_dir():
        copied = 0
        for item in sorted(task_source.iterdir()):
            if not item.is_file():
                continue
            suffix = item.suffix.lower()
            if suffix not in IMAGE_EXTS and suffix not in VIDEO_EXTS:
                continue
            copied += 1
            shutil.copy2(item, assets_dir / item.name)
        if copied > 0:
            return

    raise RuntimeError(f"输入素材不可用: {task_source}")


async def _heartbeat_loop(queue: TaskQueue, task_id: int, stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        await queue.touch_heartbeat(task_id, settings.worker_id)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=20)
        except asyncio.TimeoutError:
            continue


async def _worker_service_heartbeat_loop(queue: TaskQueue) -> None:
    WORKER_HEARTBEAT_FILE.parent.mkdir(parents=True, exist_ok=True)
    while True:
        redis_ok = False
        try:
            redis_ok = bool(await queue.redis.ping())
        except Exception:
            logger.exception("worker 服务心跳写入前 Redis 连通性检查失败")

        try:
            dump_json(
                WORKER_HEARTBEAT_FILE,
                {
                    "service": "worker",
                    "worker_id": settings.worker_id,
                    "ts": now_utc_iso(),
                    "redis_ok": redis_ok,
                    "ready_queue": settings.task_ready_queue,
                },
            )
        except Exception:
            logger.exception("写入 worker 服务心跳文件失败")

        await asyncio.sleep(10)


async def _run_task(queue: TaskQueue, message: TaskMessage) -> None:
    lock_key = queue.worker_lock_key(message.task_id)
    locked = await queue.acquire_lock(lock_key, ttl=settings.task_timeout)
    if not locked:
        return

    try:
        async with AsyncSessionLocal() as session:
            task = await get_task_by_id(session, message.task_id)
            if task is None:
                logger.warning("任务不存在: task_id=%s", message.task_id)
                return
            if task.status in FINAL_STATUSES:
                logger.info("任务已终态，跳过执行: task_id=%s status=%s", task.id, task.status)
                return
            if task.cancel_requested:
                await update_task_status(session, task.id, "CANCELED", task.progress, error_message="任务已取消")
                return

            source_path = Path(task.source_video_path)
            if not source_path.exists():
                await update_task_status(
                    session,
                    task.id,
                    "FAILED",
                    task.progress,
                    error_message=f"输入路径不存在: {source_path}",
                )
                return

            workspace_dir = build_task_workspace_dir(task.id)
            output_dir = build_task_output_dir(task.id)
            log_dir = build_task_log_dir(task.id)
            reset_dir(workspace_dir)
            reset_dir(output_dir)
            reset_dir(log_dir)

            assets_dir = workspace_dir / "assets"
            _materialize_input(source_path, assets_dir)

            task_log = log_dir / "worker.log"
            await update_task_status(
                session,
                task.id,
                "RUNNING",
                max(2, task.progress),
                worker_id=settings.worker_id,
                log_path=str(task_log),
            )

            stop_event = asyncio.Event()
            heartbeat_task = asyncio.create_task(_heartbeat_loop(queue, task.id, stop_event))

            file_handler = logging.FileHandler(task_log, encoding="utf-8")
            file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s - %(message)s"))
            core_logger = logging.getLogger("core_engine")
            core_logger.addHandler(file_handler)

            try:
                runner = GSRunner()

                async def on_progress(status: str, progress: int, message_text: str):
                    current = await get_task_by_id(session, task.id)
                    if current and current.cancel_requested:
                        raise RuntimeError("任务已被用户取消")

                    stage = _stage_from_message(message_text)
                    mapped_status = stage if status.lower() == "running" else status.upper()
                    if mapped_status not in FINAL_STATUSES and mapped_status != "CANCELED" and mapped_status != "FAILED":
                        mapped_status = stage

                    await update_task_status(
                        session,
                        task.id,
                        mapped_status,
                        progress,
                        error_message=None,
                        worker_id=settings.worker_id,
                        log_path=str(task_log),
                        heartbeat=True,
                    )
                    await queue.touch_heartbeat(task.id, settings.worker_id)

                run_result = await runner.run_project(
                    job_id=task.id,
                    project_dir=workspace_dir,
                    on_progress=on_progress,
                    mode=task.mode,
                )
                archive_path = run_result.archive_path

                archive_out = output_dir / "result.zip"
                shutil.copy2(archive_path, archive_out)
                organized = _extract_and_organize_archive(archive_out, output_dir)

                manifest_src = archive_path.parent / "manifest.json"
                manifest_out = output_dir / "manifest.json"
                if manifest_src.exists():
                    shutil.copy2(manifest_src, manifest_out)

                preview_path = _pick_preview(output_dir)
                warning_message = None
                if run_result.mesh_requested and not run_result.mesh_succeeded:
                    warning_message = "Mesh 提取失败，已降级为仅导出 3DGS 结果"

                meta_path = output_dir / "meta.json"
                meta_payload = {
                    "task_id": task.id,
                    "mode": task.mode,
                    "requested_mode": run_result.requested_mode,
                    "effective_mode": run_result.effective_mode,
                    "mesh_requested": run_result.mesh_requested,
                    "mesh_succeeded": run_result.mesh_succeeded,
                    "mesh_error": run_result.mesh_error,
                    "warning_message": warning_message,
                    "worker_id": settings.worker_id,
                    "source_video_path": str(source_path),
                    "workspace_dir": str(workspace_dir),
                    "output_dir": str(output_dir),
                    "archive_path": str(archive_out),
                    "manifest_path": str(manifest_out) if manifest_out.exists() else None,
                    "preview_path": preview_path,
                    "log_path": str(task_log),
                    "three_dgs_dir": organized["three_dgs_dir"],
                    "mesh_dir": organized["mesh_dir"],
                }
                dump_json(meta_path, meta_payload)

                await update_task_status(
                    session,
                    task.id,
                    "SUCCESS",
                    100,
                    error_message=warning_message,
                    output_path=str(output_dir),
                    preview_path=preview_path,
                    log_path=str(task_log),
                    result_meta_path=str(meta_path),
                    worker_id=settings.worker_id,
                )
                logger.info("任务执行成功: task_id=%s output=%s", task.id, output_dir)
            except Exception as exc:
                logger.exception("任务执行失败: task_id=%s", task.id)
                current = await get_task_by_id(session, task.id)
                failed_status = "CANCELED" if current and current.cancel_requested else "FAILED"
                await update_task_status(
                    session,
                    task.id,
                    failed_status,
                    min(max(task.progress, 1), 99),
                    error_message=str(exc),
                    log_path=str(task_log),
                    worker_id=settings.worker_id,
                )
            finally:
                stop_event.set()
                heartbeat_task.cancel()
                core_logger.removeHandler(file_handler)
                file_handler.close()
    finally:
        await queue.release_lock(lock_key)


async def worker_loop(name: str, queue: TaskQueue) -> None:
    logger.info("worker 协程启动: %s", name)
    while True:
        try:
            message = await queue.pop_ready(timeout=settings.worker_poll_timeout)
            if message is None:
                continue
            logger.info("收到任务: task_id=%s attempt=%s", message.task_id, message.attempt)
            await _run_task(queue, message)
        except Exception:
            logger.exception("worker 循环异常")
            await asyncio.sleep(1)


async def main() -> None:
    settings.ensure_storage_dirs()

    while True:
        try:
            await init_models()
            break
        except Exception:
            logger.exception("worker 初始化数据库失败，5 秒后重试")
            await asyncio.sleep(5)

    queue = TaskQueue()
    workers = [
        asyncio.create_task(worker_loop(f"worker-{index + 1}", queue))
        for index in range(max(1, settings.worker_concurrency))
    ]

    logger.info("worker 启动成功，并发=%s", len(workers))
    service_heartbeat_task = asyncio.create_task(_worker_service_heartbeat_loop(queue))
    try:
        await asyncio.gather(*workers, service_heartbeat_task)
    finally:
        service_heartbeat_task.cancel()
        for task in workers:
            task.cancel()
        await queue.close()


if __name__ == "__main__":
    asyncio.run(main())
