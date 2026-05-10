import asyncio
from dataclasses import dataclass
import inspect
import json
import logging
import os
import re
import shutil
import zipfile
from pathlib import Path
from typing import Awaitable, Callable, Optional

from apps.worker.core_engine.config import config

logger = logging.getLogger("core_engine.gs_runner")
logger.setLevel(logging.INFO)

ProgressCallback = Callable[[str, int, str], Awaitable[None] | None]
LineCallback = Callable[[str], Awaitable[None] | None]

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".flv"}


@dataclass(frozen=True)
class RunProjectResult:
    archive_path: Path
    requested_mode: str
    effective_mode: str
    mesh_requested: bool
    mesh_succeeded: bool
    mesh_error: str | None = None


class GSRunner:
    """Runs the server-side mp4/images -> Dynamic-2DGS -> mesh pipeline."""

    def __init__(self):
        self.paths = config.get_paths()

    async def _maybe_await(self, result):
        if inspect.isawaitable(result):
            return await result
        return result

    async def _notify(self, callback: ProgressCallback, status: str, progress: int, message: str):
        await self._maybe_await(callback(status, progress, message))

    async def stream_subprocess(
        self,
        cmd: list[str],
        cwd: Path,
        env: Optional[dict[str, str]] = None,
        on_line: Optional[LineCallback] = None,
    ) -> int:
        logger.info("Starting subprocess: %s", " ".join(cmd))

        process_env = os.environ.copy()
        if env:
            process_env.update(env)
        process_env["PYTHONUNBUFFERED"] = "1"

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=cwd,
            env=process_env,
        )

        if process.stdout:
            while True:
                line_bytes = await process.stdout.readline()
                if not line_bytes:
                    break
                line = line_bytes.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                logger.info(line)
                if on_line:
                    await self._maybe_await(on_line(line))

        return await process.wait()

    async def run_project(
        self,
        job_id: int,
        project_dir: Path,
        on_progress: ProgressCallback,
        mode: str = "both",
    ) -> RunProjectResult:
        normalized_mode = mode.strip().lower()
        if normalized_mode not in {"3dgs", "mesh", "both"}:
            raise ValueError(f"Unsupported mode: {mode}")

        project_dir = Path(project_dir)
        assets_dir = project_dir / "assets"
        workspace_dir = project_dir / "d2dgs"
        source_dir = workspace_dir / "source"
        input_dir = source_dir / "input"
        model_base_dir = workspace_dir / "model"
        model_dir = self._actual_model_path(model_base_dir)
        result_dir = project_dir / "results" / f"job_{job_id}"

        await self._notify(on_progress, "running", 5, "Preparing input frames")
        frame_count = await self.prepare_source(assets_dir, source_dir, input_dir)
        logger.info("Prepared %s input frames for %s", frame_count, project_dir)

        await self._notify(on_progress, "running", 15, "Running COLMAP reconstruction")
        await self.run_colmap(source_dir, on_progress)

        await self._notify(on_progress, "running", 30, "Training Dynamic-2DGS model")
        await self.run_train(source_dir, model_base_dir, on_progress)

        if not self._latest_point_cloud(model_dir):
            raise FileNotFoundError(f"No point_cloud.ply was generated under {model_dir}")

        mesh_requested = normalized_mode in {"mesh", "both"} and config.D2DGS_RENDER_MESH
        mesh_succeeded = not mesh_requested
        mesh_error: str | None = None
        effective_mode = normalized_mode

        if mesh_requested:
            await self._notify(on_progress, "running", 82, "Extracting mesh")
            try:
                await self.run_mesh(source_dir, model_base_dir, on_progress)
                mesh_succeeded = True
            except Exception as exc:
                if normalized_mode == "both":
                    mesh_succeeded = False
                    mesh_error = str(exc)
                    effective_mode = "3dgs"
                    logger.exception(
                        "Mesh extraction failed for job %s, fallback to 3DGS-only", job_id
                    )
                    await self._notify(
                        on_progress,
                        "running",
                        90,
                        "Mesh extraction failed, continuing with 3DGS-only artifacts",
                    )
                else:
                    raise

        await self._notify(on_progress, "running", 96, "Packaging artifacts")
        archive_path = self.package_artifacts(
            source_dir=source_dir,
            model_dir=model_dir,
            result_dir=result_dir,
            frame_count=frame_count,
            requested_mode=normalized_mode,
            effective_mode=effective_mode,
            mesh_requested=mesh_requested,
            mesh_succeeded=mesh_succeeded,
            mesh_error=mesh_error,
        )
        return RunProjectResult(
            archive_path=archive_path,
            requested_mode=normalized_mode,
            effective_mode=effective_mode,
            mesh_requested=mesh_requested,
            mesh_succeeded=mesh_succeeded,
            mesh_error=mesh_error,
        )

    async def prepare_source(self, assets_dir: Path, source_dir: Path, input_dir: Path) -> int:
        if not assets_dir.exists():
            raise FileNotFoundError(f"Project assets directory does not exist: {assets_dir}")

        self._reset_dir(source_dir)
        input_dir.mkdir(parents=True, exist_ok=True)

        videos = sorted(p for p in assets_dir.iterdir() if p.suffix.lower() in VIDEO_EXTS)
        images = sorted(p for p in assets_dir.iterdir() if p.suffix.lower() in IMAGE_EXTS)

        if videos:
            await self.extract_video_frames(videos[0], input_dir)
        elif images:
            self.copy_images(images, input_dir)
        else:
            raise ValueError("No supported input found. Upload an mp4/mov video or image sequence.")

        frames = sorted(p for p in input_dir.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
        if len(frames) < 2:
            raise ValueError("At least two extracted frames are required for COLMAP reconstruction.")
        return len(frames)

    async def extract_video_frames(self, video_path: Path, input_dir: Path) -> None:
        filter_expr = (
            f"fps={config.D2DGS_FRAME_FPS},"
            f"scale={config.D2DGS_MAX_WIDTH}:{config.D2DGS_MAX_WIDTH}:force_original_aspect_ratio=decrease"
        )
        cmd = [
            str(self.paths["ffmpeg"]),
            "-hide_banner",
            "-y",
            "-i",
            str(video_path),
            "-vf",
            filter_expr,
            "-q:v",
            "2",
            "-frames:v",
            str(config.D2DGS_MAX_FRAMES),
            "-start_number",
            "0",
            str(input_dir / "%05d.jpg"),
        ]
        exit_code = await self.stream_subprocess(cmd=cmd, cwd=self.paths["repo"])
        if exit_code != 0:
            raise RuntimeError(f"ffmpeg frame extraction failed with exit code {exit_code}")

    def copy_images(self, images: list[Path], input_dir: Path) -> None:
        for index, image_path in enumerate(images[: config.D2DGS_MAX_FRAMES]):
            suffix = ".png" if image_path.suffix.lower() == ".png" else ".jpg"
            target = input_dir / f"{index:05d}{suffix}"
            shutil.copy2(image_path, target)

    async def run_colmap(self, source_dir: Path, on_progress: ProgressCallback) -> None:
        env = self._subprocess_env()
        colmap_dir = str(self.paths["colmap"].parent)
        env["PATH"] = colmap_dir + os.pathsep + env.get("PATH", "")

        cmd = [
            str(self.paths["python"]),
            str(self.paths["repo"] / "convert.py"),
            "-s",
            str(source_dir),
            "--camera",
            config.D2DGS_CAMERA_MODEL,
            "--colmap_executable",
            str(self.paths["colmap"]),
        ]
        if not config.D2DGS_COLMAP_USE_GPU:
            cmd.append("--no_gpu")

        async def on_line(line: str):
            lower = line.lower()
            if "feature_extractor" in lower or "feature extraction" in lower:
                await self._notify(on_progress, "running", 17, "COLMAP feature extraction")
            elif "exhaustive_matcher" in lower or "matching" in lower:
                await self._notify(on_progress, "running", 21, "COLMAP feature matching")
            elif "mapper" in lower or "bundle" in lower:
                await self._notify(on_progress, "running", 25, "COLMAP sparse reconstruction")
            elif "image_undistorter" in lower or "done" in lower:
                await self._notify(on_progress, "running", 28, "COLMAP image undistortion")

        exit_code = await self.stream_subprocess(
            cmd=cmd,
            cwd=self.paths["repo"],
            env=env,
            on_line=on_line,
        )

        if exit_code != 0 and config.D2DGS_COLMAP_USE_GPU:
            await self._notify(on_progress, "running", 19, "COLMAP GPU failed, retrying on CPU")
            logger.warning("COLMAP GPU failed (exit=%s), retrying with --no_gpu", exit_code)

            # Reset potentially partial outputs before CPU retry.
            for retry_path in (source_dir / "distorted", source_dir / "sparse"):
                if retry_path.exists():
                    shutil.rmtree(retry_path, ignore_errors=True)

            retry_cmd = [
                str(self.paths["python"]),
                str(self.paths["repo"] / "convert.py"),
                "-s",
                str(source_dir),
                "--camera",
                config.D2DGS_CAMERA_MODEL,
                "--colmap_executable",
                str(self.paths["colmap"]),
                "--no_gpu",
            ]

            exit_code = await self.stream_subprocess(
                cmd=retry_cmd,
                cwd=self.paths["repo"],
                env=env,
                on_line=on_line,
            )

        if exit_code != 0:
            raise RuntimeError(f"COLMAP conversion failed with exit code {exit_code}")

        if not (source_dir / "sparse" / "0").exists():
            raise FileNotFoundError("COLMAP finished but sparse/0 was not generated.")

    async def run_train(
        self,
        source_dir: Path,
        model_base_dir: Path,
        on_progress: ProgressCallback,
    ) -> None:
        model_base_dir.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            str(self.paths["python"]),
            str(self.paths["repo"] / "train_gui.py"),
            "--source_path",
            str(source_dir),
            "--model_path",
            str(model_base_dir),
            "--deform_type",
            config.D2DGS_DEFORM_TYPE,
            "--resolution",
            str(config.D2DGS_RESOLUTION),
            "--iterations",
            str(config.D2DGS_ITERATIONS),
            "--save_iterations",
            str(config.D2DGS_ITERATIONS),
            "--test_iterations",
            str(config.D2DGS_ITERATIONS),
        ]
        if config.D2DGS_EVAL:
            cmd.append("--eval")
        if config.D2DGS_LOAD2GPU_ON_THE_FLY:
            cmd.append("--load2gpu_on_the_fly")
        if config.D2DGS_LOCAL_FRAME:
            cmd.append("--local_frame")
        if config.D2DGS_GT_ALPHA_MASK_AS_SCENE_MASK:
            cmd.append("--gt_alpha_mask_as_scene_mask")

        percent_pattern = re.compile(r"(\d+)%\|")
        iteration_pattern = re.compile(r"(\d+)/(\d+)")
        last_progress = 29

        async def on_line(line: str):
            nonlocal last_progress
            percent = None

            match = percent_pattern.search(line)
            if match:
                percent = int(match.group(1))
            else:
                match = iteration_pattern.search(line)
                if match:
                    current, total = int(match.group(1)), int(match.group(2))
                    if total:
                        percent = int(current * 100 / total)

            if percent is None:
                return
            mapped = 30 + int(50 * max(0, min(percent, 100)) / 100)
            if mapped >= last_progress + 2 or mapped >= 80:
                last_progress = mapped
                await self._notify(on_progress, "running", mapped, "Training Dynamic-2DGS model")

        exit_code = await self.stream_subprocess(
            cmd=cmd,
            cwd=self.paths["repo"],
            env=self._subprocess_env(),
            on_line=on_line,
        )
        if exit_code != 0:
            raise RuntimeError(f"Dynamic-2DGS training failed with exit code {exit_code}")

    async def run_mesh(
        self,
        source_dir: Path,
        model_base_dir: Path,
        on_progress: ProgressCallback,
    ) -> None:
        cmd = [
            str(self.paths["python"]),
            str(self.paths["repo"] / "render_mesh.py"),
            "--source_path",
            str(source_dir),
            "--model_path",
            str(model_base_dir),
            "--deform_type",
            config.D2DGS_DEFORM_TYPE,
            "--resolution",
            str(config.D2DGS_RESOLUTION),
            "--voxel_size",
            str(config.D2DGS_VOXEL_SIZE),
            "--depth_trunc",
            str(config.D2DGS_DEPTH_TRUNC),
            "--num_cluster",
            str(config.D2DGS_NUM_CLUSTER),
            "--mesh_res",
            str(config.D2DGS_MESH_RES),
        ]
        if config.D2DGS_EVAL:
            cmd.append("--eval")
        if not config.D2DGS_RENDER_IMAGES:
            cmd.extend(["--skip_train", "--skip_test"])
        if config.D2DGS_UNBOUNDED_MESH:
            cmd.append("--unbounded")

        mesh_count = 0

        async def on_line(line: str):
            nonlocal mesh_count
            if "export mesh" in line.lower():
                mesh_count += 1
                progress = min(95, 82 + mesh_count)
                await self._notify(on_progress, "running", progress, "Extracting mesh")

        exit_code = await self.stream_subprocess(
            cmd=cmd,
            cwd=self.paths["repo"],
            env=self._subprocess_env(),
            on_line=on_line,
        )
        if exit_code != 0:
            raise RuntimeError(f"Mesh extraction failed with exit code {exit_code}")

    def package_artifacts(
        self,
        source_dir: Path,
        model_dir: Path,
        result_dir: Path,
        frame_count: int,
        requested_mode: str,
        effective_mode: str,
        mesh_requested: bool,
        mesh_succeeded: bool,
        mesh_error: str | None,
    ) -> Path:
        self._reset_dir(result_dir)
        result_dir.mkdir(parents=True, exist_ok=True)

        point_cloud = self._latest_point_cloud(model_dir)
        meshes = self._mesh_files(model_dir)
        previews = self._preview_files(model_dir)

        manifest = {
            "frame_count": frame_count,
            "requested_mode": requested_mode,
            "effective_mode": effective_mode,
            "deform_type": config.D2DGS_DEFORM_TYPE,
            "iterations": config.D2DGS_ITERATIONS,
            "source_dir": str(source_dir),
            "model_dir": str(model_dir),
            "gaussian_ply": "point_cloud.ply" if point_cloud else None,
            "primary_mesh": "mesh_frame_0.ply" if meshes else None,
            "archive": "result.zip",
            "mesh_count": len(meshes),
            "preview_count": len(previews),
            "mesh_requested": mesh_requested,
            "mesh_succeeded": mesh_succeeded,
            "mesh_error": mesh_error,
        }

        if point_cloud:
            shutil.copy2(point_cloud, result_dir / "point_cloud.ply")
        if meshes:
            shutil.copy2(meshes[0], result_dir / "mesh_frame_0.ply")

        manifest_path = result_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        archive_path = result_dir / "result.zip"
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(manifest_path, "manifest.json")
            if point_cloud:
                archive.write(point_cloud, "gaussian/point_cloud.ply")
            for mesh_path in meshes:
                archive.write(mesh_path, f"mesh/{mesh_path.name}")
            for preview_path in previews:
                archive.write(preview_path, f"preview/{preview_path.parent.name}/{preview_path.name}")

            cfg_args = model_dir / "cfg_args"
            cameras_json = model_dir / "cameras.json"
            if cfg_args.exists():
                archive.write(cfg_args, "model/cfg_args")
            if cameras_json.exists():
                archive.write(cameras_json, "model/cameras.json")

        return archive_path

    def _subprocess_env(self) -> dict[str, str]:
        env = os.environ.copy()
        if config.CUDA_VISIBLE_DEVICES:
            env["CUDA_VISIBLE_DEVICES"] = config.CUDA_VISIBLE_DEVICES
        # Run COLMAP/Qt tools in headless containers without an X server.
        env.setdefault("QT_QPA_PLATFORM", "offscreen")
        return env

    def _actual_model_path(self, model_base_dir: Path) -> Path:
        if model_base_dir.name.endswith(config.D2DGS_DEFORM_TYPE):
            return model_base_dir
        return model_base_dir.with_name(f"{model_base_dir.name}_{config.D2DGS_DEFORM_TYPE}")

    def _latest_point_cloud(self, model_dir: Path) -> Optional[Path]:
        point_cloud_root = model_dir / "point_cloud"
        if not point_cloud_root.exists():
            return None

        def iteration_number(path: Path) -> int:
            try:
                return int(path.name.split("_")[-1])
            except ValueError:
                return -1

        candidates = [
            path / "point_cloud.ply"
            for path in point_cloud_root.glob("iteration_*")
            if (path / "point_cloud.ply").exists()
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda p: iteration_number(p.parent))

    def _mesh_files(self, model_dir: Path) -> list[Path]:
        meshes = sorted(model_dir.glob("train/ours_*/frame_*.ply"))
        if meshes:
            return meshes
        return sorted(model_dir.glob("mesh_export/*.ply"))

    def _preview_files(self, model_dir: Path) -> list[Path]:
        preview_dirs = [model_dir / "mesh_image", model_dir / "mesh_shape"]
        previews: list[Path] = []
        for directory in preview_dirs:
            if directory.exists():
                previews.extend(sorted(directory.glob("*.png")))
        return previews

    def _reset_dir(self, path: Path) -> None:
        if path.exists():
            shutil.rmtree(path)
