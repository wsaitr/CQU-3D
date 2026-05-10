#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/docker-compose.cpu.yml"
ENV_FILE="${SCRIPT_DIR}/.env.cpu"
PROJECT_NAME="${COMPOSE_PROJECT_NAME:-cqu3d-cpu}"
ACTION="${1:-status}"

run_compose() {
  docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" --project-name "${PROJECT_NAME}" "$@"
}

case "${ACTION}" in
  status)
    run_compose ps
    ;;
  logs)
    SERVICE="${2:-api}"
    run_compose logs -f --tail 200 "${SERVICE}"
    ;;
  restart)
    SERVICE="${2:-api}"
    run_compose restart "${SERVICE}"
    ;;
  stop)
    run_compose down
    ;;
  start)
    run_compose up -d
    ;;
  *)
    echo "用法: $0 {status|logs [service]|restart [service]|start|stop}" >&2
    exit 1
    ;;
esac
