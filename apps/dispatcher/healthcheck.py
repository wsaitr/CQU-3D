"""Dispatcher 容器健康检查。"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from packages.shared.config import settings

HEARTBEAT_FILE = Path(settings.log_dir_path) / "dispatcher" / "heartbeat.json"
MAX_AGE = timedelta(seconds=max(40, settings.dispatcher_monitor_interval * 3))


def _fail(message: str) -> int:
    print(f"dispatcher unhealthy: {message}")
    return 1


def main() -> int:
    if not HEARTBEAT_FILE.exists() or not HEARTBEAT_FILE.is_file():
        return _fail(f"heartbeat file not found: {HEARTBEAT_FILE}")

    try:
        payload = json.loads(HEARTBEAT_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        return _fail(f"invalid heartbeat json: {exc}")

    ts_text = str(payload.get("ts", "")).strip()
    if not ts_text:
        return _fail("missing ts in heartbeat")

    try:
        ts = datetime.fromisoformat(ts_text.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
    except Exception as exc:
        return _fail(f"invalid ts format: {exc}")

    now = datetime.now(timezone.utc)
    if now - ts.astimezone(timezone.utc) > MAX_AGE:
        return _fail(f"stale heartbeat: {ts_text}")

    print("dispatcher healthy")
    return 0


if __name__ == "__main__":
    sys.exit(main())
