"""存储目录与任务工作目录工具。"""

import os
import shutil
from pathlib import Path

import aiofiles
from fastapi import UploadFile

from packages.shared.config import settings
from packages.shared.models import Project, User
from packages.shared.utils import ensure_dir


def build_task_input_dir(task_id: int) -> Path:
    return settings.input_dir_path / "tasks" / f"task_{task_id}"


def build_task_workspace_dir(task_id: int) -> Path:
    return settings.workspace_dir_path / "tasks" / f"task_{task_id}"


def build_task_output_dir(task_id: int) -> Path:
    return settings.output_dir_path / "tasks" / f"task_{task_id}"


def build_task_log_dir(task_id: int) -> Path:
    return settings.log_dir_path / "tasks" / f"task_{task_id}"


def build_project_assets_dir(user: User, project: Project) -> Path:
    return settings.input_dir_path / "users" / str(user.uuid) / "projects" / str(project.uuid) / "assets"


def build_project_root(user: User, project: Project) -> Path:
    return build_project_assets_dir(user, project).parent


def reset_dir(path: Path) -> Path:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_task_dirs(task_id: int) -> dict[str, Path]:
    input_dir = ensure_dir(build_task_input_dir(task_id))
    workspace_dir = ensure_dir(build_task_workspace_dir(task_id))
    output_dir = ensure_dir(build_task_output_dir(task_id))
    log_dir = ensure_dir(build_task_log_dir(task_id))
    return {
        "input_dir": input_dir,
        "workspace_dir": workspace_dir,
        "output_dir": output_dir,
        "log_dir": log_dir,
    }


def ensure_project_assets_dir(user: User, project: Project) -> Path:
    path = build_project_assets_dir(user, project)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _resolve_under_storage(path_text: str | Path) -> Path:
    resolved = Path(path_text).resolve()
    root = settings.storage_root_path
    if resolved != root and root not in resolved.parents:
        raise ValueError(f"路径不在 STORAGE_ROOT 下: {resolved}")
    return resolved


async def delete_project_dir(user: User, project: Project) -> None:
    project_root = _resolve_under_storage(build_project_root(user, project))
    if project_root.exists():
        shutil.rmtree(project_root)

    root = settings.storage_root_path
    for parent in [project_root.parent, project_root.parent.parent, project_root.parent.parent.parent]:
        if parent == root or root not in parent.parents:
            break
        try:
            parent.rmdir()
        except OSError:
            break


async def delete_asset_file(file_path: str) -> None:
    path = _resolve_under_storage(file_path)
    if path.exists():
        os.remove(path)


async def save_upload_file(upload_file: UploadFile, dest_path: Path) -> int:
    total_size = 0
    async with aiofiles.open(dest_path, "wb") as output:
        while True:
            chunk = await upload_file.read(1024 * 1024)
            if not chunk:
                break
            total_size += len(chunk)
            await output.write(chunk)
    await upload_file.close()
    return total_size
