"""Dynamic-2DGS 统一 CLI 封装入口。"""

import argparse
import asyncio
import json
from pathlib import Path

from apps.worker.core_engine.gs_runner import GSRunner


async def run(args) -> None:
    runner = GSRunner()

    async def on_progress(status: str, progress: int, message: str):
        print(
            json.dumps(
                {
                    "status": status,
                    "progress": progress,
                    "message": message,
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

    run_result = await runner.run_project(
        job_id=args.task_id,
        project_dir=Path(args.workspace_dir),
        on_progress=on_progress,
        mode=args.mode,
    )
    print(
        json.dumps(
            {
                "result_zip": str(run_result.archive_path),
                "requested_mode": run_result.requested_mode,
                "effective_mode": run_result.effective_mode,
                "mesh_requested": run_result.mesh_requested,
                "mesh_succeeded": run_result.mesh_succeeded,
                "mesh_error": run_result.mesh_error,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="运行 dynamic-2dgs 任务")
    parser.add_argument("--task-id", type=int, required=True, help="任务ID")
    parser.add_argument("--workspace-dir", required=True, help="任务工作目录（需包含 assets/）")
    parser.add_argument("--mode", default="both", choices=["3dgs", "mesh", "both"], help="导出模式")
    parser.add_argument("--config-path", default="", help="预留配置参数")
    parser.add_argument("--input-video", default="", help="预留输入视频参数")
    parser.add_argument("--output-dir", default="", help="预留输出目录参数")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
