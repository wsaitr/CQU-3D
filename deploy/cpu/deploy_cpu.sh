#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/docker-compose.cpu.yml"
ENV_FILE="${SCRIPT_DIR}/.env.cpu"
ENV_EXAMPLE="${SCRIPT_DIR}/.env.cpu.example"
PROJECT_NAME="${COMPOSE_PROJECT_NAME:-cqu3d-cpu}"
IMAGE_ARCHIVE_DIR="${IMAGE_ARCHIVE_DIR:-${SCRIPT_DIR}/images}"
OFFLINE_FIRST="${OFFLINE_FIRST:-1}"

REQUIRED_IMAGES=(
  "mysql:8.0"
  "redis:7.2-alpine"
  "willfarrell/autoheal:1.2.0"
  "python:3.11-slim"
  "nginx:1.27-alpine"
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

if [ ! -f "${ENV_FILE}" ]; then
  cp "${ENV_EXAMPLE}" "${ENV_FILE}"
  echo "[提示] 已创建 ${ENV_FILE}，请按需修改后重新执行。"
fi

set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

if [ -z "${HOST_STORAGE_ROOT:-}" ]; then
  echo "[错误] .env.cpu 中未设置 HOST_STORAGE_ROOT。" >&2
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

wait_healthy() {
  local service="$1"
  local timeout="${2:-360}"
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
      docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" --project-name "${PROJECT_NAME}" logs --tail 100 "${service}" || true
      return 1
    fi
    sleep 3
  done
}

echo "[步骤] 开始构建 CPU 侧镜像..."
if [ "${OFFLINE_FIRST}" = "1" ]; then
  docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" --project-name "${PROJECT_NAME}" build api dispatcher web
else
  docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" --project-name "${PROJECT_NAME}" build --pull api dispatcher web
fi

echo "[步骤] 启动 CPU 侧服务..."
if [ "${OFFLINE_FIRST}" = "1" ]; then
  docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" --project-name "${PROJECT_NAME}" up -d --pull never
else
  docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" --project-name "${PROJECT_NAME}" up -d
fi

wait_healthy mysql 240
wait_healthy redis 180
wait_healthy api 300
wait_healthy dispatcher 300
wait_healthy web 240

echo "[完成] CPU 侧部署成功。"
echo "[访问] Web: http://localhost:${WEB_PUBLIC_PORT:-8080}"
echo "[访问] API 健康检查: http://localhost:${API_PUBLIC_PORT:-8000}/api/health"
echo "[下一步] 请在 GPU 服务器执行 deploy/gpu/deploy_gpu.sh。"
