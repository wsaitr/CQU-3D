#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/docker-compose.gpu.yml"
ENV_FILE="${SCRIPT_DIR}/.env.gpu"
ENV_EXAMPLE="${SCRIPT_DIR}/.env.gpu.example"
PROJECT_NAME="${COMPOSE_PROJECT_NAME:-cqu3d-gpu}"
IMAGE_ARCHIVE_DIR="${IMAGE_ARCHIVE_DIR:-${SCRIPT_DIR}/images}"
OFFLINE_FIRST="${OFFLINE_FIRST:-1}"

REQUIRED_IMAGES=(
  "nvidia/cuda:12.1.1-cudnn8-devel-ubuntu22.04"
  "willfarrell/autoheal:1.2.0"
)

load_offline_images() {
  if [ ! -d "${IMAGE_ARCHIVE_DIR}" ]; then
    return 0
  fi

  shopt -s nullglob
  local archives=("${IMAGE_ARCHIVE_DIR}"/*.tar "${IMAGE_ARCHIVE_DIR}"/*.tar.gz "${IMAGE_ARCHIVE_DIR}"/*.tgz)
  shopt -u nullglob

  if [ "${#archives[@]}" -eq 0 ]; then
    return 0
  fi

  for archive in "${archives[@]}"; do
    echo "[步骤] 加载离线镜像包: ${archive}"
    docker load -i "${archive}"
  done
}

ensure_required_images() {
  local missing=()
  local image
  for image in "${REQUIRED_IMAGES[@]}"; do
    if ! docker image inspect "${image}" >/dev/null 2>&1; then
      missing+=("${image}")
    fi
  done

  if [ "${#missing[@]}" -gt 0 ]; then
    echo "[错误] 缺少基础镜像，离线优先模式下不会自动拉取：" >&2
    for image in "${missing[@]}"; do
      echo "  - ${image}" >&2
    done
    echo "[提示] 请先在有网络机器执行 docker pull/docker save，并把镜像包放到 ${IMAGE_ARCHIVE_DIR}。" >&2
    exit 1
  fi
}

if ! command -v docker >/dev/null 2>&1; then
  echo "[错误] 未检测到 docker 命令，请先安装 Docker。" >&2
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "[错误] Docker daemon 不可用，请先启动 Docker 服务。" >&2
  exit 1
fi

if ! command -v nvidia-smi >/dev/null 2>&1; then
  echo "[错误] 未检测到 nvidia-smi，请先安装 NVIDIA 驱动。" >&2
  exit 1
fi

if [ ! -f "${ENV_FILE}" ]; then
  cp "${ENV_EXAMPLE}" "${ENV_FILE}"
  echo "[提示] 已创建 ${ENV_FILE}，请按实际 VPC 地址修改后重新执行。"
fi

set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

if [ -z "${HOST_STORAGE_ROOT:-}" ]; then
  echo "[错误] .env.gpu 中未设置 HOST_STORAGE_ROOT。" >&2
  exit 1
fi

if [ -z "${MYSQL_HOST:-}" ] || [ -z "${REDIS_URL:-}" ]; then
  echo "[错误] .env.gpu 中 MYSQL_HOST/REDIS_URL 未配置。" >&2
  exit 1
fi

mkdir -p "${HOST_STORAGE_ROOT}/input" \
         "${HOST_STORAGE_ROOT}/workspace" \
         "${HOST_STORAGE_ROOT}/output" \
         "${HOST_STORAGE_ROOT}/logs"

if [ "${OFFLINE_FIRST}" = "1" ]; then
  load_offline_images
  ensure_required_images
fi

python3 - <<'PY'
import os
import socket
import sys
from urllib.parse import urlparse

mysql_host = os.environ.get("MYSQL_HOST", "")
mysql_port = int(os.environ.get("MYSQL_PORT", "3306"))
redis_url = os.environ.get("REDIS_URL", "")

if not mysql_host or not redis_url:
    print("[错误] MYSQL_HOST 或 REDIS_URL 缺失")
    sys.exit(1)

parsed = urlparse(redis_url)
redis_host = parsed.hostname
redis_port = parsed.port or 6379
if not redis_host:
    print("[错误] REDIS_URL 解析失败")
    sys.exit(1)

for name, host, port in (
    ("MySQL", mysql_host, mysql_port),
    ("Redis", redis_host, redis_port),
):
    try:
        with socket.create_connection((host, port), timeout=5):
            print(f"[OK] {name} VPC 连通成功: {host}:{port}")
    except OSError as exc:
        print(f"[错误] {name} VPC 连通失败: {host}:{port} -> {exc}")
        sys.exit(1)
PY

wait_healthy() {
  local service="$1"
  local timeout="${2:-600}"
  local start_ts
  start_ts="$(date +%s)"

  while true; do
    local cid status now_ts
    cid="$(docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" --project-name "${PROJECT_NAME}" ps -q "${service}" || true)"
    if [ -n "${cid}" ]; then
      status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "${cid}" 2>/dev/null || true)"
      if [ "${status}" = "healthy" ] || [ "${status}" = "running" ]; then
        echo "[OK] ${service} 状态: ${status}"
        return 0
      fi
    fi

    now_ts="$(date +%s)"
    if [ $((now_ts - start_ts)) -ge "${timeout}" ]; then
      echo "[错误] 等待 ${service} 健康超时。" >&2
      docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" --project-name "${PROJECT_NAME}" logs --tail 120 "${service}" || true
      return 1
    fi
    sleep 5
  done
}

echo "[步骤] 构建 worker 镜像（会在 build 阶段预编译 CUDA 扩展）..."
if [ "${OFFLINE_FIRST}" = "1" ]; then
  docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" --project-name "${PROJECT_NAME}" build worker
else
  docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" --project-name "${PROJECT_NAME}" build --pull worker
fi

echo "[步骤] 启动 worker 服务..."
if [ "${OFFLINE_FIRST}" = "1" ]; then
  docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" --project-name "${PROJECT_NAME}" up -d --pull never
else
  docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" --project-name "${PROJECT_NAME}" up -d
fi

wait_healthy worker 900

echo "[完成] GPU 侧部署成功。"
echo "[提示] 当前 WORKER_ID=${WORKER_ID:-gpu-worker-01}，如多机部署请确保每台机器唯一。"
