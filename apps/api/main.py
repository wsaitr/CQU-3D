"""API 服务：鉴权/控制面/任务管理。"""

import json
import shutil
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from packages.shared.config import settings
from packages.shared.database import get_session, init_models
from packages.shared.models import Asset, User
from packages.shared.repository import (
    count_user_projects,
    create_assets,
    create_project,
    create_task,
    create_user,
    delete_asset,
    delete_project_with_relations,
    get_asset_by_id,
    get_global_total_asset_size,
    get_latest_task,
    get_project_by_id,
    get_project_total_asset_size,
    get_task_by_id,
    get_task_by_idempotency_key,
    get_user_by_email,
    get_user_by_id,
    get_user_by_username,
    list_assets,
    list_projects,
    list_tasks,
    request_cancel,
    task_to_dict,
    update_task,
    update_task_status,
)
from packages.shared.storage import (
    build_task_input_dir,
    delete_asset_file,
    delete_project_dir,
    ensure_project_assets_dir,
    save_upload_file,
)
from packages.shared.task_queue import TaskQueue
from packages.shared.task_status import ACTIVE_STATUSES, FINAL_STATUSES, TASK_STATUSES, normalize_mode
from packages.shared.utils import ensure_dir, storage_safe_path, storage_url

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tiff", ".tif"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".flv"}

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

app = FastAPI(title="cqu3d-async-api")
settings.ensure_storage_dirs()
app.mount("/storage", StaticFiles(directory=settings.storage_root), name="storage")


class Token(BaseModel):
    access_token: str
    token_type: str


class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class UserRead(BaseModel):
    id: int
    username: str
    email: EmailStr
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=500)


class ProjectRead(BaseModel):
    id: int
    name: str
    description: str | None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class AssetRead(BaseModel):
    id: int
    file_type: str
    filename: str
    file_path: str
    file_size: int
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class TaskCreateJSON(BaseModel):
    source_video_path: str | None = None
    mode: str = Field(default="both")
    user_id: int | None = None
    project_id: int | None = None
    idempotency_key: str | None = None


class TaskCreateResponse(BaseModel):
    task_id: int
    status: str
    progress: int
    deduplicated: bool = False


class InternalTaskUpdate(BaseModel):
    status: str
    progress: int = Field(default=0, ge=0, le=100)
    error_message: str | None = None
    output_path: str | None = None
    preview_path: str | None = None
    log_path: str | None = None
    result_meta_path: str | None = None
    worker_id: str | None = None


def _verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def _get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def _create_access_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


async def _get_current_user_optional(
    session: AsyncSession = Depends(get_session),
    token: str | None = Depends(oauth2_scheme),
) -> User | None:
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        user_id = payload.get("sub")
        if user_id is None:
            return None
    except JWTError:
        return None

    return await get_user_by_id(session, int(user_id))


async def _get_current_user_required(
    current_user: User | None = Depends(_get_current_user_optional),
) -> User:
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请先登录",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return current_user


def _upload_size(upload: UploadFile) -> int:
    try:
        upload.file.seek(0, 2)
        size = upload.file.tell()
        upload.file.seek(0)
        return size
    except Exception:
        return upload.size if upload.size is not None else 0


def _infer_file_type(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix in IMAGE_SUFFIXES:
        return "image"
    if suffix in VIDEO_SUFFIXES:
        return "video"
    return "unknown"


def _build_asset_filename(original_name: str, index: int) -> str:
    suffix = Path(original_name).suffix.lower()
    return f"{index:06d}_{uuid.uuid4().hex}{suffix}"


def _copy_source_to_input(source_path: Path, input_dir: Path) -> Path:
    ensure_dir(input_dir)
    if source_path.is_file():
        target = input_dir / source_path.name
        shutil.copy2(source_path, target)
        return target

    if source_path.is_dir():
        target_dir = input_dir / source_path.name
        if target_dir.exists():
            shutil.rmtree(target_dir)
        shutil.copytree(source_path, target_dir)
        return target_dir

    raise ValueError(f"source_video_path 不存在: {source_path}")


def _resolve_source_path(raw_path: str) -> Path:
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = settings.storage_root_path / candidate
    candidate = candidate.resolve()
    if not candidate.exists():
        raise ValueError(f"source_video_path 不存在: {candidate}")
    return candidate


def _parse_task_meta(task_obj) -> dict[str, Any] | None:
    meta_path = Path(task_obj.result_meta_path) if task_obj.result_meta_path else None
    if not meta_path or not meta_path.exists() or not meta_path.is_file():
        return None
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _add_dir_to_zip(archive: zipfile.ZipFile, source_dir: Path, arc_prefix: str) -> bool:
    if not source_dir.exists() or not source_dir.is_dir():
        return False
    added = False
    for file_path in sorted(source_dir.rglob("*")):
        if not file_path.is_file():
            continue
        arcname = f"{arc_prefix}/{file_path.relative_to(source_dir).as_posix()}"
        archive.write(file_path, arcname)
        added = True
    return added


def _rebuild_archive_from_output(output_dir: Path) -> Path | None:
    archive_path = output_dir / "result.zip"
    manifest_path = output_dir / "manifest.json"
    has_payload = False

    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        if manifest_path.exists() and manifest_path.is_file():
            archive.write(manifest_path, "manifest.json")
            has_payload = True

        has_payload = _add_dir_to_zip(archive, output_dir / "3dgs", "gaussian") or has_payload
        has_payload = _add_dir_to_zip(archive, output_dir / "mesh", "mesh") or has_payload
        has_payload = _add_dir_to_zip(archive, output_dir / "preview", "preview") or has_payload
        has_payload = _add_dir_to_zip(archive, output_dir / "extracted" / "model", "model") or has_payload

        meta_path = output_dir / "meta.json"
        if meta_path.exists() and meta_path.is_file():
            archive.write(meta_path, "meta.json")
            has_payload = True

    if has_payload:
        return archive_path

    archive_path.unlink(missing_ok=True)
    return None


def _build_task_payload(task_obj, with_artifacts: bool = False) -> dict[str, Any]:
    payload = task_to_dict(task_obj)
    payload["status_url"] = f"/api/tasks/{task_obj.id}"
    payload["result_url"] = f"/api/tasks/{task_obj.id}/result"
    payload["download_url"] = f"/api/tasks/{task_obj.id}/download"
    payload["cancel_url"] = f"/api/tasks/{task_obj.id}/cancel"

    payload["storage_urls"] = {
        "source_video": storage_url(task_obj.source_video_path),
        "output": storage_url(task_obj.output_path),
        "preview": storage_url(task_obj.preview_path),
        "log": storage_url(task_obj.log_path),
        "meta": storage_url(task_obj.result_meta_path),
    }

    if not with_artifacts:
        return payload

    parsed_meta = _parse_task_meta(task_obj)
    artifacts: dict[str, Any] = {
        "output_path": task_obj.output_path,
        "preview_path": task_obj.preview_path,
        "log_path": task_obj.log_path,
        "meta_path": task_obj.result_meta_path,
        "download_urls": {
            "output": storage_url(task_obj.output_path),
            "preview": storage_url(task_obj.preview_path),
            "log": storage_url(task_obj.log_path),
            "meta": storage_url(task_obj.result_meta_path),
            "archive": f"/api/tasks/{task_obj.id}/download",
        },
    }

    if isinstance(parsed_meta, dict):
        artifacts["meta"] = parsed_meta
        if parsed_meta.get("warning_message"):
            artifacts["warning_message"] = parsed_meta.get("warning_message")
        if parsed_meta.get("requested_mode"):
            artifacts["requested_mode"] = parsed_meta.get("requested_mode")
        if parsed_meta.get("effective_mode"):
            artifacts["effective_mode"] = parsed_meta.get("effective_mode")
        manifest_path = parsed_meta.get("manifest_path")
        three_dgs_dir = parsed_meta.get("three_dgs_dir")
        mesh_dir = parsed_meta.get("mesh_dir")
        if manifest_path:
            artifacts["download_urls"]["manifest"] = storage_url(manifest_path)
        if three_dgs_dir:
            artifacts["download_urls"]["three_dgs"] = storage_url(three_dgs_dir)
        if mesh_dir:
            artifacts["download_urls"]["mesh"] = storage_url(mesh_dir)
    else:
        artifacts["meta"] = None

    payload["artifacts"] = artifacts
    return payload


def _ensure_task_access(task_obj, current_user: User | None) -> None:
    if task_obj.user_id is None:
        return
    if current_user is None or int(task_obj.user_id) != int(current_user.id):
        raise HTTPException(status_code=403, detail="无权限访问该任务")


async def _resolve_project_input_path(session: AsyncSession, project_id: int, user_id: int) -> str:
    assets = await list_assets(session, project_id=project_id, user_id=user_id)
    videos = [asset for asset in assets if asset.file_type == "video"]
    images = [asset for asset in assets if asset.file_type == "image"]

    if not videos and not images:
        raise HTTPException(status_code=400, detail="请先上传 mp4 视频或图片序列")
    if len(videos) > 1:
        raise HTTPException(status_code=400, detail="一个项目一次只能处理一个视频")
    if videos and images:
        raise HTTPException(status_code=400, detail="请勿同时上传视频和图片序列")
    if images and len(images) < 2:
        raise HTTPException(status_code=400, detail="图片序列至少需要 2 张图片")

    if videos:
        return videos[0].file_path
    return str(Path(images[0].file_path).resolve().parent)


def _resolve_task_download_file(task_obj) -> Path:
    candidates: list[Path] = []
    parsed_meta = _parse_task_meta(task_obj)
    if isinstance(parsed_meta, dict) and parsed_meta.get("archive_path"):
        candidates.append(Path(str(parsed_meta["archive_path"])))

    if task_obj.output_path:
        output_path = Path(task_obj.output_path)
        if output_path.is_file() and output_path.suffix.lower() == ".zip":
            candidates.append(output_path)
        candidates.append(output_path / "result.zip")

    for candidate in candidates:
        resolved = candidate.resolve()
        try:
            safe = storage_safe_path(resolved)
        except ValueError:
            continue
        if safe.exists() and safe.is_file():
            return safe

    if task_obj.output_path:
        output_path = Path(task_obj.output_path)
        if output_path.exists() and output_path.is_dir():
            try:
                safe_output = storage_safe_path(output_path.resolve())
            except ValueError:
                safe_output = None

            if safe_output is not None:
                rebuilt = _rebuild_archive_from_output(safe_output)
                if rebuilt is not None and rebuilt.exists() and rebuilt.is_file():
                    return rebuilt

    raise HTTPException(status_code=404, detail="结果文件不存在")


async def _create_and_enqueue_task(
    session: AsyncSession,
    mode: str,
    user_id: int | None,
    project_id: int | None,
    source_video_path: str | None,
    upload_file: UploadFile | None,
    idempotency_key: str | None,
    enforce_project_single_active: bool = False,
) -> TaskCreateResponse:
    try:
        normalized_mode = normalize_mode(mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if enforce_project_single_active and user_id is not None and project_id is not None:
        running = await get_latest_task(session, user_id, project_id, statuses=ACTIVE_STATUSES)
        if running is not None:
            raise HTTPException(status_code=409, detail="该项目已有任务正在处理中")

    if idempotency_key:
        dedup = await get_task_by_idempotency_key(session, idempotency_key=idempotency_key, user_id=user_id)
        if dedup is not None and (project_id is None or dedup.project_id == project_id):
            return TaskCreateResponse(
                task_id=dedup.id,
                status=dedup.status,
                progress=dedup.progress,
                deduplicated=True,
            )

    task = await create_task(
        session=session,
        source_video_path="",
        mode=normalized_mode,
        user_id=user_id,
        project_id=project_id,
        max_retries=settings.task_max_retries,
        idempotency_key=idempotency_key,
    )

    if upload_file is not None:
        task_input_dir = build_task_input_dir(task.id)
        ensure_dir(task_input_dir)
        target_path = task_input_dir / (upload_file.filename or "upload.mp4")
        await save_upload_file(upload_file, target_path)
        source_path = target_path
    else:
        if not source_video_path:
            await update_task_status(session, task.id, "FAILED", 0, error_message="必须提供输入素材")
            raise HTTPException(status_code=400, detail="必须提供输入素材")
        try:
            resolved = _resolve_source_path(source_video_path)
            if project_id is not None and user_id is not None:
                # 工程模式直接使用“用户/工程资产目录”里的源路径，避免 task 临时路径失配。
                source_path = resolved
            else:
                task_input_dir = build_task_input_dir(task.id)
                ensure_dir(task_input_dir)
                source_path = _copy_source_to_input(resolved, task_input_dir)
        except ValueError as exc:
            await update_task_status(session, task.id, "FAILED", 0, error_message=str(exc))
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    await update_task(
        session,
        task.id,
        source_video_path=str(source_path),
        status="PENDING",
        progress=0,
    )

    queue = TaskQueue()
    try:
        await queue.enqueue_incoming(task.id, attempt=0)
    finally:
        await queue.close()

    updated = await update_task_status(session, task.id, "QUEUED", 1)
    if updated is None:
        raise HTTPException(status_code=500, detail="任务创建后状态更新失败")

    return TaskCreateResponse(task_id=updated.id, status=updated.status, progress=updated.progress)


@app.on_event("startup")
async def on_startup() -> None:
    await init_models()


@app.get("/api/health")
async def health(session: AsyncSession = Depends(get_session)) -> dict:
    db_ok = False
    redis_ok = False

    try:
        await session.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    queue = TaskQueue()
    try:
        redis_ok = bool(await queue.redis.ping())
    except Exception:
        redis_ok = False
    finally:
        await queue.close()

    status_text = "ok" if db_ok and redis_ok else "degraded"
    return {
        "status": status_text,
        "service": "api",
        "db": db_ok,
        "redis": redis_ok,
    }


@app.post("/api/auth/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register_user(payload: UserCreate, session: AsyncSession = Depends(get_session)):
    if await get_user_by_username(session, payload.username):
        raise HTTPException(status_code=400, detail="用户名已存在")
    if await get_user_by_email(session, payload.email):
        raise HTTPException(status_code=400, detail="邮箱已存在")

    user = await create_user(
        session,
        username=payload.username,
        email=payload.email,
        hashed_password=_get_password_hash(payload.password),
    )
    return user


@app.post("/api/auth/login", response_model=Token)
async def login_user(
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(get_session),
):
    user = await get_user_by_username(session, form_data.username)
    if user is None or not _verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号或密码错误")

    access_token = _create_access_token(subject=str(user.id))
    return {"access_token": access_token, "token_type": "bearer"}


@app.post("/api/projects", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project_endpoint(
    payload: ProjectCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(_get_current_user_required),
):
    count = await count_user_projects(session, current_user.id)
    if count >= settings.max_projects_per_user:
        raise HTTPException(
            status_code=400,
            detail=f"工程数量已达上限 ({settings.max_projects_per_user} 个)",
        )

    existing = await list_projects(session, current_user.id)
    if any(item.name == payload.name for item in existing):
        raise HTTPException(status_code=400, detail="工程名称已存在")

    project = await create_project(session, current_user.id, payload.name, payload.description)
    return project


@app.get("/api/projects", response_model=list[ProjectRead])
async def list_projects_endpoint(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(_get_current_user_required),
):
    return await list_projects(session, current_user.id)


@app.get("/api/projects/{project_id}", response_model=ProjectRead)
async def get_project_endpoint(
    project_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(_get_current_user_required),
):
    project = await get_project_by_id(session, project_id, current_user.id)
    if project is None:
        raise HTTPException(status_code=404, detail="工程不存在")
    return project


@app.delete("/api/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project_endpoint(
    project_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(_get_current_user_required),
):
    project = await get_project_by_id(session, project_id, current_user.id)
    if project is None:
        raise HTTPException(status_code=404, detail="工程不存在")

    await delete_project_dir(current_user, project)
    await delete_project_with_relations(session, project)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/api/projects/{project_id}/assets", response_model=list[AssetRead])
async def upload_assets(
    project_id: int,
    files: list[UploadFile] = File(...),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(_get_current_user_required),
):
    project = await get_project_by_id(session, project_id, current_user.id)
    if project is None:
        raise HTTPException(status_code=404, detail="工程不存在")
    if not files:
        raise HTTPException(status_code=400, detail="请选择要上传的文件")

    current_global_usage = await get_global_total_asset_size(session)
    if current_global_usage >= settings.max_global_storage:
        raise HTTPException(status_code=507, detail="系统总存储空间已满")

    current_project_usage = await get_project_total_asset_size(session, project_id)
    new_files_total_size = 0
    detected_types: list[str] = []

    for upload in files:
        file_type = _infer_file_type(upload.filename or "")
        if file_type == "unknown":
            raise HTTPException(status_code=400, detail=f"文件类型不支持: {upload.filename}")

        size_in_bytes = _upload_size(upload)
        if size_in_bytes > settings.max_file_size:
            raise HTTPException(status_code=413, detail=f"文件超过单文件大小限制: {upload.filename}")

        detected_types.append(file_type)
        new_files_total_size += size_in_bytes

    if detected_types.count("video") > 1:
        raise HTTPException(status_code=400, detail="一个项目一次只能上传一个视频")
    if "video" in detected_types and "image" in detected_types:
        raise HTTPException(status_code=400, detail="请勿在同一次请求中混传视频和图片")
    if current_project_usage + new_files_total_size > settings.max_project_size:
        raise HTTPException(status_code=413, detail="项目存储空间不足")
    if current_global_usage + new_files_total_size > settings.max_global_storage:
        raise HTTPException(status_code=507, detail="系统总存储空间不足")

    project_dir = ensure_project_assets_dir(current_user, project)
    assets_to_create: list[Asset] = []
    saved_paths: list[Path] = []

    try:
        for index, (upload, file_type) in enumerate(zip(files, detected_types), start=1):
            saved_name = _build_asset_filename(upload.filename or "upload", index)
            dest_path = project_dir / saved_name
            file_size = await save_upload_file(upload, dest_path)
            saved_paths.append(dest_path)
            assets_to_create.append(
                Asset(
                    user_id=current_user.id,
                    project_id=project_id,
                    file_type=file_type,
                    filename=saved_name,
                    file_path=str(dest_path),
                    file_size=file_size,
                )
            )
        return await create_assets(session, assets_to_create)
    except Exception:
        for path in saved_paths:
            await delete_asset_file(str(path))
        raise


@app.get("/api/projects/{project_id}/assets", response_model=list[AssetRead])
async def list_assets_endpoint(
    project_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(_get_current_user_required),
):
    project = await get_project_by_id(session, project_id, current_user.id)
    if project is None:
        raise HTTPException(status_code=404, detail="工程不存在")
    return await list_assets(session, project_id=project_id, user_id=current_user.id)


@app.delete("/api/projects/{project_id}/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset_endpoint(
    project_id: int,
    asset_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(_get_current_user_required),
):
    project = await get_project_by_id(session, project_id, current_user.id)
    if project is None:
        raise HTTPException(status_code=404, detail="工程不存在")

    asset = await get_asset_by_id(session, asset_id)
    if asset is None or asset.project_id != project_id or asset.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="素材不存在")

    await delete_asset_file(asset.file_path)
    await delete_asset(session, asset)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/task-statuses")
async def task_statuses() -> dict:
    return {"statuses": list(TASK_STATUSES)}


@app.post("/api/tasks", response_model=TaskCreateResponse)
async def create_task_endpoint(
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: User | None = Depends(_get_current_user_optional),
):
    content_type = request.headers.get("content-type", "")
    idempotency_key = request.headers.get("Idempotency-Key")
    mode = "both"
    user_id: int | None = None
    project_id: int | None = None
    source_video_path: str | None = None
    upload_file: UploadFile | None = None

    if "application/json" in content_type:
        payload = TaskCreateJSON.model_validate(await request.json())
        mode = payload.mode
        user_id = payload.user_id
        project_id = payload.project_id
        source_video_path = payload.source_video_path
        idempotency_key = payload.idempotency_key or idempotency_key
    else:
        form = await request.form()
        mode = str(form.get("mode", "both"))
        source_video_path = str(form.get("source_video_path")) if form.get("source_video_path") else None
        if form.get("user_id"):
            user_id = int(form.get("user_id"))
        if form.get("project_id"):
            project_id = int(form.get("project_id"))
        if form.get("idempotency_key"):
            idempotency_key = str(form.get("idempotency_key"))
        raw_upload = form.get("file")
        if raw_upload is not None and hasattr(raw_upload, "filename") and hasattr(raw_upload, "read"):
            upload_file = raw_upload

    effective_user_id = user_id
    if current_user is not None:
        if user_id is not None and user_id != current_user.id:
            raise HTTPException(status_code=403, detail="user_id 与登录用户不一致")
        effective_user_id = current_user.id

    if project_id is not None:
        if current_user is None:
            raise HTTPException(status_code=401, detail="project_id 模式需要登录")
        project = await get_project_by_id(session, project_id, current_user.id)
        if project is None:
            raise HTTPException(status_code=404, detail="工程不存在")
        effective_user_id = current_user.id
        if upload_file is None:
            # 工程模式每次点击“开始加工”都按当前用户+工程重新解析素材，
            # 不信任前端传入的 source_video_path，避免使用陈旧路径。
            source_video_path = await _resolve_project_input_path(session, project.id, current_user.id)

    if upload_file is None and not source_video_path:
        raise HTTPException(status_code=400, detail="必须提供 file 上传或 source_video_path")

    return await _create_and_enqueue_task(
        session=session,
        mode=mode,
        user_id=effective_user_id,
        project_id=project_id,
        source_video_path=source_video_path,
        upload_file=upload_file,
        idempotency_key=idempotency_key,
        enforce_project_single_active=project_id is not None,
    )


@app.get("/api/tasks")
async def list_tasks_endpoint(
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
    user_id: int | None = None,
    project_id: int | None = None,
    session: AsyncSession = Depends(get_session),
    current_user: User | None = Depends(_get_current_user_optional),
):
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="limit 必须在 1-500 之间")
    if status and status not in TASK_STATUSES:
        raise HTTPException(status_code=400, detail=f"非法状态: {status}")

    effective_user_id = user_id
    if current_user is not None:
        effective_user_id = current_user.id
    elif project_id is not None:
        raise HTTPException(status_code=401, detail="project_id 查询需要登录")

    items = await list_tasks(
        session,
        limit=limit,
        offset=max(0, offset),
        status=status,
        user_id=effective_user_id,
        project_id=project_id,
    )
    return [_build_task_payload(task_obj) for task_obj in items]


@app.get("/api/tasks/{task_id}")
async def get_task_detail(
    task_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User | None = Depends(_get_current_user_optional),
):
    task = await get_task_by_id(session, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    _ensure_task_access(task, current_user)
    return _build_task_payload(task)


@app.get("/api/tasks/{task_id}/result")
async def get_task_result(
    task_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User | None = Depends(_get_current_user_optional),
):
    task = await get_task_by_id(session, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    _ensure_task_access(task, current_user)
    return _build_task_payload(task, with_artifacts=True)


@app.get("/api/tasks/{task_id}/download")
async def download_task_result(
    task_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User | None = Depends(_get_current_user_optional),
):
    task = await get_task_by_id(session, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    _ensure_task_access(task, current_user)
    archive_path = _resolve_task_download_file(task)
    return FileResponse(path=archive_path, filename=archive_path.name, media_type="application/zip")


@app.post("/api/tasks/{task_id}/cancel")
async def cancel_task(
    task_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User | None = Depends(_get_current_user_optional),
):
    existing = await get_task_by_id(session, task_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    _ensure_task_access(existing, current_user)

    task = await request_cancel(session, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status in FINAL_STATUSES:
        return {"task_id": task.id, "status": task.status, "message": "任务已处于终态"}

    if task.status not in ("PENDING", "QUEUED"):
        await update_task_status(
            session,
            task.id,
            "CANCELED",
            task.progress,
            error_message="用户请求取消任务",
            worker_id=task.worker_id,
        )
    return {"task_id": task.id, "status": "CANCELED", "message": "已提交取消请求"}


@app.post("/api/projects/{project_id}/process", response_model=TaskCreateResponse)
async def trigger_project_process(
    project_id: int,
    payload: dict[str, Any] | None = None,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(_get_current_user_required),
):
    project = await get_project_by_id(session, project_id, current_user.id)
    if project is None:
        raise HTTPException(status_code=404, detail="工程不存在")

    mode = str((payload or {}).get("mode", "both"))
    source_video_path = (payload or {}).get("source_video_path")
    if not source_video_path:
        source_video_path = await _resolve_project_input_path(session, project_id, current_user.id)

    return await _create_and_enqueue_task(
        session=session,
        mode=mode,
        user_id=current_user.id,
        project_id=project_id,
        source_video_path=source_video_path,
        upload_file=None,
        idempotency_key=None,
        enforce_project_single_active=True,
    )


@app.get("/api/projects/{project_id}/process")
async def get_project_process_status(
    project_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(_get_current_user_required),
):
    project = await get_project_by_id(session, project_id, current_user.id)
    if project is None:
        raise HTTPException(status_code=404, detail="工程不存在")

    task = await get_latest_task(session, current_user.id, project_id)
    if task is None:
        raise HTTPException(status_code=404, detail="未找到处理任务")
    return _build_task_payload(task, with_artifacts=True)


@app.get("/api/projects/{project_id}/result")
async def get_project_result(
    project_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(_get_current_user_required),
):
    project = await get_project_by_id(session, project_id, current_user.id)
    if project is None:
        raise HTTPException(status_code=404, detail="工程不存在")

    task = await get_latest_task(session, current_user.id, project_id, statuses=("SUCCESS",))
    if task is None:
        raise HTTPException(status_code=404, detail="未找到结果")
    return _build_task_payload(task, with_artifacts=True)


@app.get("/api/projects/{project_id}/result/download")
async def download_project_result(
    project_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(_get_current_user_required),
):
    project = await get_project_by_id(session, project_id, current_user.id)
    if project is None:
        raise HTTPException(status_code=404, detail="工程不存在")

    task = await get_latest_task(session, current_user.id, project_id, statuses=("SUCCESS",))
    if task is None:
        raise HTTPException(status_code=404, detail="未找到结果")
    archive_path = _resolve_task_download_file(task)
    return FileResponse(path=archive_path, filename=archive_path.name, media_type="application/zip")


@app.get("/api/projects/{project_id}/result/manifest")
async def get_project_result_manifest(
    project_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(_get_current_user_required),
):
    project = await get_project_by_id(session, project_id, current_user.id)
    if project is None:
        raise HTTPException(status_code=404, detail="工程不存在")

    task = await get_latest_task(session, current_user.id, project_id, statuses=("SUCCESS",))
    if task is None:
        raise HTTPException(status_code=404, detail="未找到结果")

    parsed_meta = _parse_task_meta(task)
    if isinstance(parsed_meta, dict) and parsed_meta.get("manifest_path"):
        manifest_path = Path(str(parsed_meta["manifest_path"]))
    elif task.output_path:
        manifest_path = Path(task.output_path) / "manifest.json"
    else:
        raise HTTPException(status_code=404, detail="结果清单不存在")

    try:
        safe_path = storage_safe_path(manifest_path.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="结果路径非法") from exc
    if not safe_path.exists() or not safe_path.is_file():
        raise HTTPException(status_code=404, detail="结果清单不存在")

    return json.loads(safe_path.read_text(encoding="utf-8"))


@app.post("/api/internal/tasks/{task_id}/status")
async def internal_task_update(
    task_id: int,
    payload: InternalTaskUpdate,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    token = request.headers.get("X-Worker-Token", "")
    if token != settings.internal_api_token:
        raise HTTPException(status_code=403, detail="forbidden")

    if payload.status not in TASK_STATUSES:
        raise HTTPException(status_code=400, detail=f"非法状态: {payload.status}")

    task = await update_task_status(
        session,
        task_id,
        payload.status,
        payload.progress,
        error_message=payload.error_message,
        output_path=payload.output_path,
        preview_path=payload.preview_path,
        log_path=payload.log_path,
        result_meta_path=payload.result_meta_path,
        worker_id=payload.worker_id,
        heartbeat=True,
    )
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"ok": True, "task_id": task.id, "status": task.status, "progress": task.progress}


@app.exception_handler(ValueError)
async def value_error_handler(_: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=settings.api_port)
