from dataclasses import dataclass
from typing import Optional


@dataclass
class TaskRecord:
    task_id: int
    status: str
    progress: int = 0
    error_message: Optional[str] = None
