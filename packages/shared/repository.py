"""任务仓储操作。"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.shared.models import Asset, Project, Task, User
from packages.shared.task_status import FINAL_STATUSES, RUNNING_STATUSES
from packages.shared.utils import now_utc


async def create_task(
    session: AsyncSession,
    source_video_path: str,
    mode: str,
    user_id: int | None,
    project_id: int | None,
    max_retries: int,
    idempotency_key: str | None = None,
) -> Task:
    task = Task(
        user_id=user_id,
        project_id=project_id,
        source_video_path=source_video_path,
        status="PENDING",
        progress=0,
        mode=mode,
        max_retries=max_retries,
        idempotency_key=idempotency_key,
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


async def get_task_by_id(session: AsyncSession, task_id: int) -> Task | None:
    return await session.get(Task, task_id)


async def get_task_by_idempotency_key(
    session: AsyncSession,
    idempotency_key: str,
    user_id: int | None,
) -> Task | None:
    query = select(Task).where(Task.idempotency_key == idempotency_key)
    if user_id is not None:
        query = query.where(Task.user_id == user_id)
    result = await session.execute(query.order_by(desc(Task.created_at)).limit(1))
    return result.scalar_one_or_none()


async def list_tasks(
    session: AsyncSession,
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
    user_id: int | None = None,
    project_id: int | None = None,
) -> list[Task]:
    query = select(Task)
    if status:
        query = query.where(Task.status == status)
    if user_id is not None:
        query = query.where(Task.user_id == user_id)
    if project_id is not None:
        query = query.where(Task.project_id == project_id)
    query = query.order_by(desc(Task.created_at)).offset(offset).limit(limit)
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_latest_task(
    session: AsyncSession,
    user_id: int,
    project_id: int,
    statuses: tuple[str, ...] | None = None,
) -> Task | None:
    query = select(Task).where(Task.user_id == user_id, Task.project_id == project_id)
    if statuses:
        query = query.where(Task.status.in_(statuses))
    result = await session.execute(query.order_by(desc(Task.created_at)).limit(1))
    return result.scalar_one_or_none()


async def update_task(
    session: AsyncSession,
    task_id: int,
    **changes,
) -> Task | None:
    task = await session.get(Task, task_id)
    if task is None:
        return None

    for key, value in changes.items():
        setattr(task, key, value)

    await session.commit()
    await session.refresh(task)
    return task


async def update_task_status(
    session: AsyncSession,
    task_id: int,
    status: str,
    progress: int,
    error_message: str | None = None,
    output_path: str | None = None,
    preview_path: str | None = None,
    log_path: str | None = None,
    result_meta_path: str | None = None,
    worker_id: str | None = None,
    heartbeat: bool = False,
) -> Task | None:
    task = await session.get(Task, task_id)
    if task is None:
        return None

    task.status = status
    task.progress = max(0, min(int(progress), 100))
    task.error_message = error_message

    if output_path is not None:
        task.output_path = output_path
    if preview_path is not None:
        task.preview_path = preview_path
    if log_path is not None:
        task.log_path = log_path
    if result_meta_path is not None:
        task.result_meta_path = result_meta_path
    if worker_id is not None:
        task.worker_id = worker_id

    now = now_utc()
    if status in RUNNING_STATUSES and task.started_at is None:
        task.started_at = now
    if heartbeat or status in RUNNING_STATUSES:
        task.heartbeat_at = now
    if status in FINAL_STATUSES:
        task.finished_at = now

    await session.commit()
    await session.refresh(task)
    return task


async def request_cancel(session: AsyncSession, task_id: int) -> Task | None:
    task = await session.get(Task, task_id)
    if task is None:
        return None

    task.cancel_requested = True
    if task.status in FINAL_STATUSES:
        await session.commit()
        await session.refresh(task)
        return task

    if task.status in ("PENDING", "QUEUED"):
        task.status = "CANCELED"
        task.error_message = "用户取消任务"
        task.finished_at = now_utc()
    await session.commit()
    await session.refresh(task)
    return task


async def count_running_tasks(session: AsyncSession) -> int:
    result = await session.execute(select(func.count(Task.id)).where(Task.status.in_(RUNNING_STATUSES)))
    return int(result.scalar() or 0)


async def list_running_tasks(session: AsyncSession) -> list[Task]:
    result = await session.execute(select(Task).where(Task.status.in_(RUNNING_STATUSES)).order_by(desc(Task.updated_at)))
    return list(result.scalars().all())


async def list_dispatchable_tasks(session: AsyncSession, limit: int = 500) -> list[Task]:
    """返回需要进入调度队列的任务（PENDING/QUEUED）。"""
    result = await session.execute(
        select(Task)
        .where(Task.status.in_(("PENDING", "QUEUED")), Task.cancel_requested.is_(False))
        .order_by(Task.created_at)
        .limit(limit)
    )
    return list(result.scalars().all())


async def list_retryable_failed_tasks(session: AsyncSession, limit: int = 100) -> list[Task]:
    result = await session.execute(
        select(Task)
        .where(Task.status == "FAILED", Task.retry_count < Task.max_retries)
        .order_by(desc(Task.updated_at))
        .limit(limit)
    )
    return list(result.scalars().all())


async def bump_retry_count(session: AsyncSession, task_id: int) -> Task | None:
    task = await session.get(Task, task_id)
    if task is None:
        return None
    task.retry_count += 1
    await session.commit()
    await session.refresh(task)
    return task


def is_timed_out(task: Task, timeout_seconds: int) -> bool:
    reference = task.heartbeat_at or task.started_at
    if reference is None:
        return False

    # MySQL DATETIME 通常是无时区；运行时 now_utc() 为带时区。
    # 统一转成 UTC naive，避免 aware/naive 比较报错。
    def _normalize_utc_naive(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    now = _normalize_utc_naive(now_utc())
    reference = _normalize_utc_naive(reference)
    timeout = timedelta(seconds=max(1, timeout_seconds))
    return reference + timeout < now


def task_to_dict(task: Task) -> dict:
    return {
        "id": task.id,
        "user_id": task.user_id,
        "project_id": task.project_id,
        "source_video_path": task.source_video_path,
        "status": task.status,
        "progress": task.progress,
        "mode": task.mode,
        "error_message": task.error_message,
        "output_path": task.output_path,
        "preview_path": task.preview_path,
        "log_path": task.log_path,
        "result_meta_path": task.result_meta_path,
        "retry_count": task.retry_count,
        "max_retries": task.max_retries,
        "worker_id": task.worker_id,
        "cancel_requested": bool(task.cancel_requested),
        "idempotency_key": task.idempotency_key,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "started_at": task.started_at,
        "heartbeat_at": task.heartbeat_at,
        "finished_at": task.finished_at,
    }


async def get_user_by_id(session: AsyncSession, user_id: int) -> User | None:
    return await session.get(User, user_id)


async def get_user_by_username(session: AsyncSession, username: str) -> User | None:
    result = await session.execute(select(User).where(User.username == username).limit(1))
    return result.scalar_one_or_none()


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email).limit(1))
    return result.scalar_one_or_none()


async def create_user(
    session: AsyncSession,
    username: str,
    email: str,
    hashed_password: str,
) -> User:
    user = User(username=username, email=email, hashed_password=hashed_password)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def count_user_projects(session: AsyncSession, user_id: int) -> int:
    result = await session.execute(select(func.count(Project.id)).where(Project.user_id == user_id))
    return int(result.scalar() or 0)


async def create_project(
    session: AsyncSession,
    user_id: int,
    name: str,
    description: str | None,
) -> Project:
    project = Project(user_id=user_id, name=name, description=description)
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


async def list_projects(session: AsyncSession, user_id: int) -> list[Project]:
    result = await session.execute(select(Project).where(Project.user_id == user_id).order_by(desc(Project.created_at)))
    return list(result.scalars().all())


async def get_project_by_id(
    session: AsyncSession,
    project_id: int,
    user_id: int,
) -> Project | None:
    result = await session.execute(
        select(Project).where(Project.id == project_id, Project.user_id == user_id).limit(1)
    )
    return result.scalar_one_or_none()


async def delete_project_with_relations(session: AsyncSession, project: Project) -> None:
    await session.execute(delete(Asset).where(Asset.project_id == project.id))
    await session.execute(delete(Task).where(Task.project_id == project.id))
    await session.execute(delete(Project).where(Project.id == project.id))
    await session.commit()


async def get_global_total_asset_size(session: AsyncSession) -> int:
    result = await session.execute(select(func.sum(Asset.file_size)))
    return int(result.scalar() or 0)


async def get_project_total_asset_size(session: AsyncSession, project_id: int) -> int:
    result = await session.execute(select(func.sum(Asset.file_size)).where(Asset.project_id == project_id))
    return int(result.scalar() or 0)


async def create_assets(session: AsyncSession, assets: list[Asset]) -> list[Asset]:
    session.add_all(assets)
    await session.commit()
    for asset in assets:
        await session.refresh(asset)
    return assets


async def list_assets(session: AsyncSession, project_id: int, user_id: int) -> list[Asset]:
    result = await session.execute(
        select(Asset)
        .where(Asset.project_id == project_id, Asset.user_id == user_id)
        .order_by(Asset.created_at)
    )
    return list(result.scalars().all())


async def get_asset_by_id(session: AsyncSession, asset_id: int) -> Asset | None:
    return await session.get(Asset, asset_id)


async def delete_asset(session: AsyncSession, asset: Asset) -> None:
    await session.delete(asset)
    await session.commit()
