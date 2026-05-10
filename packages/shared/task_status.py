TASK_STATUSES = (
    "PENDING",
    "QUEUED",
    "RUNNING",
    "PREPROCESSING",
    "TRAINING_3DGS",
    "TRAINING_MESH",
    "EXPORTING",
    "SUCCESS",
    "FAILED",
    "CANCELED",
)

ACTIVE_STATUSES = (
    "PENDING",
    "QUEUED",
    "RUNNING",
    "PREPROCESSING",
    "TRAINING_3DGS",
    "TRAINING_MESH",
    "EXPORTING",
)

RUNNING_STATUSES = (
    "RUNNING",
    "PREPROCESSING",
    "TRAINING_3DGS",
    "TRAINING_MESH",
    "EXPORTING",
)

FINAL_STATUSES = (
    "SUCCESS",
    "FAILED",
    "CANCELED",
)

MODE_ALIASES = {
    "3dgs": "3dgs",
    "gs": "3dgs",
    "mesh": "mesh",
    "both": "both",
    "all": "both",
}


def normalize_mode(mode: str | None) -> str:
    raw = (mode or "both").strip().lower()
    normalized = MODE_ALIASES.get(raw)
    if normalized is None:
        raise ValueError("mode 仅支持: 3dgs | mesh | both")
    return normalized
