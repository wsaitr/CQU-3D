"""共享配置定义。"""

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

KB = 1024
MB = KB * 1024
GB = MB * 1024
TB = GB * 1024


def parse_size(value: int | str) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)

    raw = str(value).strip().upper()
    units = {
        "TB": TB,
        "T": TB,
        "GB": GB,
        "G": GB,
        "MB": MB,
        "M": MB,
        "KB": KB,
        "K": KB,
        "B": 1,
    }
    for unit, multiplier in units.items():
        if raw.endswith(unit):
            number = float(raw[: -len(unit)])
            return int(number * multiplier)
    raise ValueError(f"无法解析的容量格式: {value}")


class AppSettings(BaseSettings):
    app_name: str = "cqu3d-async-platform"
    app_version: str = "1.0.0"

    jwt_secret_key: str = "change_me_jwt_secret"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    api_port: int = 8000
    web_port: int = 8080

    mysql_url: str = ""
    mysql_host: str = "mysql"
    mysql_port: int = 3306
    mysql_database: str = "repo_db"
    mysql_user: str = "repo_user"
    mysql_password: str = "change_me_app"

    redis_url: str = "redis://redis:6379/0"

    storage_root: str = "/workspace/repo/storage"
    input_dir: str = "/workspace/repo/storage/input"
    workspace_dir: str = "/workspace/repo/storage/workspace"
    output_dir: str = "/workspace/repo/storage/output"
    log_dir: str = "/workspace/repo/storage/logs"

    task_incoming_queue: str = "cqu3d:tasks:incoming"
    task_ready_queue: str = "cqu3d:tasks:ready"
    task_heartbeat_prefix: str = "cqu3d:tasks:heartbeat"
    task_dispatch_lock_prefix: str = "cqu3d:tasks:dispatch-lock"
    task_worker_lock_prefix: str = "cqu3d:tasks:worker-lock"

    task_timeout: int = 21600
    task_heartbeat_timeout: int = 300
    task_max_retries: int = 1

    dispatcher_poll_timeout: int = 5
    dispatcher_monitor_interval: int = 15
    dispatcher_max_inflight: int = 1

    worker_poll_timeout: int = 5
    worker_concurrency: int = 1
    worker_id: str = "worker-1"

    max_file_size: int | str = 4 * GB
    max_project_size: int | str = 10 * GB
    max_projects_per_user: int = 5
    max_global_storage: int | str = 200 * GB

    dynamic_2dgs_root: str = "/workspace/repo/services/dynamic-2dgs"
    gs_python: str = "/usr/local/bin/python"
    colmap_bin: str = "colmap"
    ffmpeg_bin: str = "ffmpeg"

    disable_gpu: bool = False
    cuda_visible_devices: str = "0"

    d2dgs_frame_fps: float = 3.0
    d2dgs_max_frames: int = 120
    d2dgs_max_width: int = 1280
    d2dgs_camera_model: str = "OPENCV"
    d2dgs_colmap_use_gpu: bool = True
    d2dgs_deform_type: str = "static"
    d2dgs_iterations: int = 2000
    d2dgs_resolution: str = "1"
    d2dgs_eval: bool = True
    d2dgs_load2gpu_on_the_fly: bool = True
    d2dgs_local_frame: bool = False
    d2dgs_gt_alpha_mask_as_scene_mask: bool = False
    d2dgs_render_mesh: bool = True
    d2dgs_render_images: bool = False
    d2dgs_voxel_size: float = 0.004
    d2dgs_depth_trunc: float = 6.0
    d2dgs_num_cluster: int = 1000
    d2dgs_unbounded_mesh: bool = False
    d2dgs_mesh_res: int = 1024

    internal_api_token: str = "change_me_internal_token"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False)

    @field_validator("max_file_size", "max_project_size", "max_global_storage", mode="before")
    @classmethod
    def validate_size(cls, value: int | str) -> int:
        return parse_size(value)

    @field_validator("jwt_secret_key")
    @classmethod
    def validate_jwt_secret(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 16:
            raise ValueError("jwt_secret_key 长度至少为 16")
        return normalized

    @property
    def database_url(self) -> str:
        if self.mysql_url:
            value = self.mysql_url.strip()
            if value.startswith("mysql://"):
                return value.replace("mysql://", "mysql+aiomysql://", 1)
            return value
        return (
            f"mysql+aiomysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
        )

    @property
    def storage_root_path(self) -> Path:
        return Path(self.storage_root).resolve()

    @property
    def input_dir_path(self) -> Path:
        return Path(self.input_dir).resolve()

    @property
    def workspace_dir_path(self) -> Path:
        return Path(self.workspace_dir).resolve()

    @property
    def output_dir_path(self) -> Path:
        return Path(self.output_dir).resolve()

    @property
    def log_dir_path(self) -> Path:
        return Path(self.log_dir).resolve()

    def ensure_storage_dirs(self) -> None:
        self.storage_root_path.mkdir(parents=True, exist_ok=True)
        self.input_dir_path.mkdir(parents=True, exist_ok=True)
        self.workspace_dir_path.mkdir(parents=True, exist_ok=True)
        self.output_dir_path.mkdir(parents=True, exist_ok=True)
        self.log_dir_path.mkdir(parents=True, exist_ok=True)


settings = AppSettings()
