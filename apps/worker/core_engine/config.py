import os
import shutil
import sys
from pathlib import Path

from packages.shared.config import settings


class CoreEngineConfig:
    """Dynamic-2DGS 执行配置。"""

    def __init__(self):
        repo_root = Path(__file__).resolve().parents[3]
        default_candidates = [
            Path(settings.dynamic_2dgs_root),
            repo_root / "services" / "dynamic-2dgs",
            repo_root.parent / "dynamic-2dgs",
        ]
        default_gs_repo = next((path for path in default_candidates if path.exists()), default_candidates[0])

        self.GS_PYTHON = os.getenv("GS_PYTHON", settings.gs_python or sys.executable)
        self.GS_REPO_DIR = os.getenv("DYNAMIC_2DGS_ROOT", os.getenv("GS_REPO_DIR", str(default_gs_repo)))
        self.COLMAP_BIN = os.getenv("COLMAP_BIN", settings.colmap_bin or shutil.which("colmap") or "colmap")
        self.FFMPEG_BIN = os.getenv("FFMPEG_BIN", settings.ffmpeg_bin or shutil.which("ffmpeg") or "ffmpeg")

        self.CUDA_VISIBLE_DEVICES = os.getenv("CUDA_VISIBLE_DEVICES", settings.cuda_visible_devices)
        self.DISABLE_GPU = str(os.getenv("DISABLE_GPU", str(settings.disable_gpu))).lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

        self.D2DGS_FRAME_FPS = float(os.getenv("D2DGS_FRAME_FPS", str(settings.d2dgs_frame_fps)))
        self.D2DGS_MAX_FRAMES = int(os.getenv("D2DGS_MAX_FRAMES", str(settings.d2dgs_max_frames)))
        self.D2DGS_MAX_WIDTH = int(os.getenv("D2DGS_MAX_WIDTH", str(settings.d2dgs_max_width)))
        self.D2DGS_CAMERA_MODEL = os.getenv("D2DGS_CAMERA_MODEL", settings.d2dgs_camera_model)
        self.D2DGS_COLMAP_USE_GPU = str(
            os.getenv("D2DGS_COLMAP_USE_GPU", str(settings.d2dgs_colmap_use_gpu))
        ).lower() in {"1", "true", "yes", "on"}

        self.D2DGS_DEFORM_TYPE = os.getenv("D2DGS_DEFORM_TYPE", settings.d2dgs_deform_type)
        self.D2DGS_ITERATIONS = int(os.getenv("D2DGS_ITERATIONS", str(settings.d2dgs_iterations)))
        self.D2DGS_RESOLUTION = os.getenv("D2DGS_RESOLUTION", settings.d2dgs_resolution)
        self.D2DGS_EVAL = str(os.getenv("D2DGS_EVAL", str(settings.d2dgs_eval))).lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.D2DGS_LOAD2GPU_ON_THE_FLY = str(
            os.getenv("D2DGS_LOAD2GPU_ON_THE_FLY", str(settings.d2dgs_load2gpu_on_the_fly))
        ).lower() in {"1", "true", "yes", "on"}
        self.D2DGS_LOCAL_FRAME = str(os.getenv("D2DGS_LOCAL_FRAME", str(settings.d2dgs_local_frame))).lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.D2DGS_GT_ALPHA_MASK_AS_SCENE_MASK = str(
            os.getenv(
                "D2DGS_GT_ALPHA_MASK_AS_SCENE_MASK",
                str(settings.d2dgs_gt_alpha_mask_as_scene_mask),
            )
        ).lower() in {"1", "true", "yes", "on"}

        self.D2DGS_RENDER_MESH = str(os.getenv("D2DGS_RENDER_MESH", str(settings.d2dgs_render_mesh))).lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.D2DGS_RENDER_IMAGES = str(
            os.getenv("D2DGS_RENDER_IMAGES", str(settings.d2dgs_render_images))
        ).lower() in {"1", "true", "yes", "on"}
        self.D2DGS_VOXEL_SIZE = float(os.getenv("D2DGS_VOXEL_SIZE", str(settings.d2dgs_voxel_size)))
        self.D2DGS_DEPTH_TRUNC = float(os.getenv("D2DGS_DEPTH_TRUNC", str(settings.d2dgs_depth_trunc)))
        self.D2DGS_NUM_CLUSTER = int(os.getenv("D2DGS_NUM_CLUSTER", str(settings.d2dgs_num_cluster)))
        self.D2DGS_UNBOUNDED_MESH = str(
            os.getenv("D2DGS_UNBOUNDED_MESH", str(settings.d2dgs_unbounded_mesh))
        ).lower() in {"1", "true", "yes", "on"}
        self.D2DGS_MESH_RES = int(os.getenv("D2DGS_MESH_RES", str(settings.d2dgs_mesh_res)))

    def get_paths(self) -> dict[str, Path]:
        paths: dict[str, Path] = {}

        python_path = Path(self.GS_PYTHON)
        if not python_path.exists() or not python_path.is_file():
            # Keep compatibility across base images where python may be in /usr/bin instead of /usr/local/bin.
            resolved = shutil.which(self.GS_PYTHON) or shutil.which("python") or shutil.which("python3")
            if not resolved:
                raise ValueError(f"GS_PYTHON 不可执行: {python_path}")
            python_path = Path(resolved)
        paths["python"] = python_path

        repo_path = Path(self.GS_REPO_DIR)
        if not repo_path.exists() or not repo_path.is_dir():
            raise ValueError(f"DYNAMIC_2DGS_ROOT 不存在: {repo_path}")

        required_scripts = ["convert.py", "train_gui.py", "render_mesh.py"]
        missing = [name for name in required_scripts if not (repo_path / name).exists()]
        if missing:
            raise ValueError(f"dynamic-2dgs 缺少脚本: {', '.join(missing)}")
        paths["repo"] = repo_path

        colmap_path = Path(self.COLMAP_BIN)
        if not colmap_path.exists():
            resolved = shutil.which(self.COLMAP_BIN)
            if not resolved:
                raise ValueError(f"COLMAP 不存在: {self.COLMAP_BIN}")
            colmap_path = Path(resolved)
        paths["colmap"] = colmap_path

        ffmpeg_path = Path(self.FFMPEG_BIN)
        if not ffmpeg_path.exists():
            resolved = shutil.which(self.FFMPEG_BIN)
            if not resolved:
                raise ValueError(f"FFMPEG 不存在: {self.FFMPEG_BIN}")
            ffmpeg_path = Path(resolved)
        paths["ffmpeg"] = ffmpeg_path

        return paths


config = CoreEngineConfig()
