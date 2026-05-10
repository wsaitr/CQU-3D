import json
from datetime import datetime, timezone
from pathlib import Path

from packages.shared.config import settings


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def ensure_dir(path: str | Path) -> Path:
    resolved = Path(path)
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def storage_safe_path(path_text: str | Path) -> Path:
    """确保路径位于 STORAGE_ROOT 下。"""
    resolved = Path(path_text).resolve()
    root = settings.storage_root_path
    if resolved != root and root not in resolved.parents:
        raise ValueError(f"路径不在 STORAGE_ROOT 下: {resolved}")
    return resolved


def storage_url(path_text: str | Path | None) -> str | None:
    if not path_text:
        return None
    resolved = Path(path_text).resolve()
    root = settings.storage_root_path
    if resolved != root and root not in resolved.parents:
        return None
    rel = resolved.relative_to(root).as_posix()
    return f"/storage/{rel}"


def dump_json(path: str | Path, payload: dict) -> None:
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
