# CQU3D 用户化异步视频转 3DGS/Mesh 平台（repo2）

repo2 基于原 repo 扩展为可服务真实用户的版本，核心包含：

- 用户认证（注册/登录/JWT）
- 工程管理（创建/列表/详情/删除）
- 素材管理（上传/列表/删除，含容量限制）
- 项目任务（按 `project_id` 发起异步任务并查询结果）

## 架构

平台采用 6 服务架构：`web / api / mysql / redis / dispatcher / worker`

- `web`: 登录注册、工程页、素材上传、任务状态与结果下载
- `api`: 认证、工程/素材管理、任务控制面、结果接口
- `mysql`: 持久化（users/projects/assets/tasks）
- `redis`: 队列、锁、心跳、临时状态
- `dispatcher`: 调度 incoming 队列到 ready 队列
- `worker`: 执行 dynamic-2dgs 流程并回写任务状态

## 快速启动

1. 复制环境变量

```bash
cp .env.example .env
```

2. 启动服务

```bash
docker compose up --build -d
```

3. 默认访问

- Web: `http://localhost:8080`
- API 健康检查: `http://localhost:8000/api/health`

## 关键环境变量

见 `.env.example`，重点关注：

- 数据库: `MYSQL_URL` 或 `MYSQL_HOST/MYSQL_PORT/MYSQL_DATABASE/MYSQL_USER/MYSQL_PASSWORD`
- Redis: `REDIS_URL`
- 鉴权: `JWT_SECRET_KEY/JWT_ALGORITHM/ACCESS_TOKEN_EXPIRE_MINUTES`
- 存储: `STORAGE_ROOT/INPUT_DIR/WORKSPACE_DIR/OUTPUT_DIR/LOG_DIR`
- 限额: `MAX_FILE_SIZE/MAX_PROJECT_SIZE/MAX_PROJECTS_PER_USER/MAX_GLOBAL_STORAGE`
- 任务调度: `WORKER_CONCURRENCY/DISPATCHER_MAX_INFLIGHT/TASK_TIMEOUT/TASK_HEARTBEAT_TIMEOUT/TASK_MAX_RETRIES`

## 用户与工程流程

1. `POST /api/auth/register` 注册
2. `POST /api/auth/login` 获取 Bearer Token
3. `POST /api/projects` 创建工程
4. `POST /api/projects/{project_id}/assets` 上传视频或图片序列
5. `POST /api/tasks`（携带 `project_id`）创建异步任务
6. `GET /api/tasks?project_id=...` 轮询状态
7. `GET /api/tasks/{task_id}/result` 查看产物信息
8. `GET /api/tasks/{task_id}/download` 下载结果压缩包

## 任务状态流转

`PENDING -> QUEUED -> RUNNING -> PREPROCESSING -> TRAINING_3DGS -> TRAINING_MESH -> EXPORTING -> SUCCESS/FAILED/CANCELED`

## 最低接口清单

- `GET /api/health`
- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/projects`
- `POST /api/projects`
- `GET /api/projects/{project_id}`
- `DELETE /api/projects/{project_id}`
- `POST /api/projects/{project_id}/assets`
- `GET /api/projects/{project_id}/assets`
- `DELETE /api/projects/{project_id}/assets/{asset_id}`
- `POST /api/tasks`
- `GET /api/tasks`
- `GET /api/tasks/{task_id}`
- `GET /api/tasks/{task_id}/result`
- `GET /api/tasks/{task_id}/download`
- `POST /api/tasks/{task_id}/cancel`

## 说明

- 项目任务默认按登录用户进行数据隔离，防止跨用户访问。
- 当前取消任务为软取消，worker 会在下一次进度回调时感知并中断。
- 生产部署建议替换 `JWT_SECRET_KEY`、数据库密码和内部 token。

## 分离部署（CPU/GPU）

本仓库已提供 CPU 与 GPU 分离部署版本，请直接参考：

- [README_SPLIT_DEPLOY.md](README_SPLIT_DEPLOY.md)

包含：

- 阿里云 VPC 通讯约束
- CPU/GPU 双端一键部署脚本
- 健康检查、自恢复与日志策略
