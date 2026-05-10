# CQU3D 分离部署版（repo3_split）

本版本将服务拆分为两类：

- CPU 服务器：web + api + dispatcher + mysql + redis
- GPU 服务器：worker（可单台或多台）

目标：

- GPU 可随时上下线，任务不丢失、不假死
- CPU 可频繁重启，服务自动恢复
- 首次一键部署完成后即可运行任务，不在首次任务时编译 CUDA 扩展

## 1. 目录说明

- deploy/cpu/docker-compose.cpu.yml：CPU 侧编排
- deploy/gpu/docker-compose.gpu.yml：GPU 侧编排
- deploy/cpu/deploy_cpu.sh：CPU 一键部署
- deploy/gpu/deploy_gpu.sh：GPU 一键部署
- deploy/cpu/ops_cpu.sh：CPU 运维快捷脚本
- deploy/gpu/ops_gpu.sh：GPU 运维快捷脚本

## 2. 阿里云 VPC 组网要求

要求 CPU 与 GPU 主机在同一 VPC 内，推荐不同交换机同网段互通。

### 2.1 安全组策略（最小开放）

在 CPU 服务器安全组上只允许来自 GPU 安全组的入站：

- TCP 3306（MySQL）
- TCP 6379（Redis）
- 可选：TCP 8000（API 调试）

如果外网访问 Web/API，还需对公网入口按需开放：

- TCP 8080（Web）
- TCP 8000（API）

### 2.2 网络连通验证

GPU 一键脚本 deploy/gpu/deploy_gpu.sh 会自动检查：

- MYSQL_HOST:MYSQL_PORT 是否可达
- REDIS_URL 对应主机端口是否可达

不通时会直接失败，避免“部署成功但不可用”。

## 3. 共享存储要求

CPU 与所有 GPU 服务器必须挂载同一份共享存储（推荐 NAS/NFS）。

- CPU 侧 .env.cpu 的 HOST_STORAGE_ROOT
- GPU 侧 .env.gpu 的 HOST_STORAGE_ROOT

两边必须指向同一份数据。

建议目录结构（脚本会自动创建）：

- input
- workspace
- output
- logs

## 4. 一键部署

### 4.1 CPU 服务器

1. 复制配置：

- cp deploy/cpu/.env.cpu.example deploy/cpu/.env.cpu

2. 修改关键项：

- JWT_SECRET_KEY
- INTERNAL_API_TOKEN
- MYSQL_ROOT_PASSWORD / MYSQL_PASSWORD
- HOST_STORAGE_ROOT

3. 执行一键部署：

- bash deploy/cpu/deploy_cpu.sh

脚本会自动：

- 构建 api/dispatcher/web 镜像
- 拉起 mysql/redis/api/dispatcher/web/autoheal
- 等待健康检查通过

### 4.2 GPU 服务器（可多台）

每台 GPU 机器都执行：

1. 复制配置：

- cp deploy/gpu/.env.gpu.example deploy/gpu/.env.gpu

2. 修改关键项：

- MYSQL_HOST（CPU 服务器 VPC 私网 IP）
- REDIS_URL（CPU 服务器 VPC 私网 IP）
- MYSQL_PASSWORD
- HOST_STORAGE_ROOT（共享存储挂载点）
- WORKER_ID（每台 GPU 必须唯一）

3. 执行一键部署：

- bash deploy/gpu/deploy_gpu.sh

脚本会自动：

- 校验 nvidia-smi
- 校验 VPC 连通性
- 构建 worker 镜像（构建阶段预编译 CUDA 扩展）
- 启动 worker + autoheal
- 等待 worker 健康

## 5. 首次部署即完全可用的保证

worker 镜像在 build 阶段执行 infra/docker/install-d2dgs-deps.sh，包含：

- 本地 torch/torchvision/torchaudio wheel 安装
- diff-surfel-rasterization 编译安装
- simple-knn 编译安装
- nvdiffrast 编译安装
- 依赖 import 校验

因此不会在第一次任务时再编译。

## 6. 自恢复与异常检测设计

### 6.1 容器级自恢复

- 所有关键服务 restart: unless-stopped
- 引入 autoheal，对 healthcheck fail 的容器自动重启

### 6.2 应用级自恢复

- dispatcher 启动时会做任务队列对账，将 DB 中 PENDING/QUEUED 任务补回 incoming 队列
- dispatcher 周期性对账，防止重启或网络抖动后出现任务假死
- worker/dispatcher 均增加数据库初始化重试逻辑，避免依赖暂不可用时崩溃退出

### 6.3 GPU 节点上下线适配

- worker 心跳断开后，dispatcher 监控会判定超时并自动重试或失败收敛
- 支持多 worker 同时消费，GPU 节点增减无需改 CPU 服务

## 7. 日志与排障

### 7.1 容器日志

使用 json-file rotation：

- max-size=50m
- max-file=10

### 7.2 业务日志

写入共享存储 logs 目录：

- worker 任务日志
- dispatcher 服务心跳日志
- worker 服务心跳日志

### 7.3 常用运维命令

CPU 侧：

- bash deploy/cpu/ops_cpu.sh status
- bash deploy/cpu/ops_cpu.sh logs api
- bash deploy/cpu/ops_cpu.sh logs dispatcher

GPU 侧：

- bash deploy/gpu/ops_gpu.sh status
- bash deploy/gpu/ops_gpu.sh logs

## 8. 验收清单

部署完成后，按顺序验证：

1. CPU 侧服务健康

- web/api/dispatcher/mysql/redis 均 healthy

2. GPU 侧服务健康

- worker healthy，且日志无缺依赖报错

3. 任务链路验证

- 上传素材
- 创建任务
- 状态正常流转至 SUCCESS
- 下载结果成功

4. 故障演练

- 停掉 worker 容器后恢复，任务可继续被重试处理
- 重启 CPU 主机后，dispatcher 启动对账可恢复待调度任务

## 9. 版本边界

本版本保持业务代码路径与 repo2 一致，主要新增部署编排与自愈能力；如需跨机 TLS、数据库主从、Redis 哨兵，可在此版本上继续扩展。

## 10. 弱网与 Docker Hub 受限场景

为避免 Docker Hub 抖动导致部署失败，本版本的一键脚本默认启用离线优先：

- OFFLINE_FIRST=1（默认）：不主动拉取镜像
- IMAGE_ARCHIVE_DIR：离线镜像包目录，默认分别为：
- CPU：deploy/cpu/images
- GPU：deploy/gpu/images

### 10.1 脚本行为

- deploy/cpu/deploy_cpu.sh 在离线优先模式下：
- 自动加载 deploy/cpu/images 下的 .tar/.tar.gz/.tgz 镜像包
- 检查 mysql/redis/autoheal/python/nginx 基础镜像是否存在
- build 不加 --pull，up 使用 --pull never

- deploy/gpu/deploy_gpu.sh 在离线优先模式下：
- 自动加载 deploy/gpu/images 下的 .tar/.tar.gz/.tgz 镜像包
- 检查 nvidia/cuda 与 autoheal 基础镜像是否存在
- build 不加 --pull，up 使用 --pull never

### 10.2 需要预制的离线镜像

CPU 侧至少准备：

- mysql:8.0
- redis:7.2-alpine
- willfarrell/autoheal:1.2.0
- python:3.11-slim
- nginx:1.27-alpine

GPU 侧至少准备：

- nvidia/cuda:12.1.1-cudnn8-devel-ubuntu22.04
- willfarrell/autoheal:1.2.0

### 10.3 在有网络机器导出镜像

示例（CPU）：

- docker pull mysql:8.0
- docker pull redis:7.2-alpine
- docker pull willfarrell/autoheal:1.2.0
- docker pull python:3.11-slim
- docker pull nginx:1.27-alpine
- docker save -o cpu-base-images.tar mysql:8.0 redis:7.2-alpine willfarrell/autoheal:1.2.0 python:3.11-slim nginx:1.27-alpine

示例（GPU）：

- docker pull nvidia/cuda:12.1.1-cudnn8-devel-ubuntu22.04
- docker pull willfarrell/autoheal:1.2.0
- docker save -o gpu-base-images.tar nvidia/cuda:12.1.1-cudnn8-devel-ubuntu22.04 willfarrell/autoheal:1.2.0

把导出的 tar 包放到目标机器目录：

- CPU：repo3_split/deploy/cpu/images/
- GPU：repo3_split/deploy/gpu/images/

然后直接执行一键脚本即可。

### 10.4 如需恢复在线拉取

可临时关闭离线优先：

- OFFLINE_FIRST=0 bash deploy/cpu/deploy_cpu.sh
- OFFLINE_FIRST=0 bash deploy/gpu/deploy_gpu.sh
