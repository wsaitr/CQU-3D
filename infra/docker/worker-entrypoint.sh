#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python}"
if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  else
    echo "[entrypoint] python executable not found" >&2
    exit 1
  fi
fi

export FORCE_CUDA="${FORCE_CUDA:-1}"
export MAX_JOBS="${MAX_JOBS:-$(nproc)}"
export CUDA_HOME="${CUDA_HOME:-/usr/local/cuda}"

detect_and_export_torch_lib_path() {
  local torch_lib_dir
  if torch_lib_dir="$(${PYTHON_BIN} - <<'PY'
import os

try:
    import torch
except Exception:
    raise SystemExit(1)

print(os.path.join(os.path.dirname(torch.__file__), "lib"))
PY
)"; then
    export LD_LIBRARY_PATH="${torch_lib_dir}:${LD_LIBRARY_PATH:-}"
  fi
}

require_python_module() {
  local import_name="$1"
  local hint_message="$2"
  if ${PYTHON_BIN} -c "import ${import_name}" >/dev/null 2>&1; then
    return
  fi
  echo "[entrypoint] missing python module '${import_name}'. ${hint_message}" >&2
  exit 1
}

detect_and_export_torch_lib_path
require_python_module "torch" "请先执行镜像构建阶段依赖安装。"
require_python_module "diff_surfel_rasterization" "请确认 build 时已安装 diff_surfel_rasterization。"
require_python_module "simple_knn" "请确认 build 时已安装 simple_knn。"
require_python_module "nvdiffrast.torch" "请确认 build 时已安装 nvdiffrast。"
require_python_module "pytorch3d" "请确认本地 wheel 已放入 wheelhouse 并完成构建。"
require_python_module "dearpygui.dearpygui" "请确认构建阶段已安装 dearpygui。"
require_python_module "imageio" "请确认构建阶段已安装 imageio。"
require_python_module "scipy" "请确认构建阶段已安装 scipy。"
require_python_module "plyfile" "请确认构建阶段已安装 plyfile。"
require_python_module "cv2" "请确认构建阶段已安装 opencv-python-headless。"
require_python_module "lpips" "请确认构建阶段已安装 lpips。"
require_python_module "matplotlib" "请确认构建阶段已安装 matplotlib。"
require_python_module "open3d" "请确认构建阶段已安装 open3d。"

detect_and_export_torch_lib_path

exec ${PYTHON_BIN} /workspace/repo/apps/worker/main.py
