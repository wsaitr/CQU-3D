document.addEventListener("DOMContentLoaded", async () => {
    if (!API.token) {
        window.location.href = "index.html";
        return;
    }

    const urlParams = new URLSearchParams(window.location.search);
    const projectId = urlParams.get("id");

    if (!projectId) {
        window.location.href = "dashboard.html";
        return;
    }

    const projectName = document.getElementById("project-name");
    const projectDesc = document.getElementById("project-desc");
    const assetList = document.getElementById("asset-list");
    const uploadForm = document.getElementById("upload-form");
    const processBtn = document.getElementById("process-btn");
    const processProgressContainer = document.getElementById("process-progress-container");
    const processProgressBar = document.getElementById("process-progress-bar");
    const processStatus = document.getElementById("process-status");
    const resultContainer = document.getElementById("result-container");
    const modeSelector = document.getElementById("task-mode");

    const POLL_INTERVAL_MS = 2000;
    const POLL_RETRY_INTERVAL_MS = 4000;

    let currentTaskId = null;
    let resultLoadedTaskId = null;
    let isCheckingStatus = false;
    let statusPollTimer = null;

    function clearStatusPollTimer() {
        if (statusPollTimer) {
            clearTimeout(statusPollTimer);
            statusPollTimer = null;
        }
    }

    function scheduleStatusPoll(delayMs = POLL_INTERVAL_MS) {
        clearStatusPollTimer();
        statusPollTimer = setTimeout(() => {
            checkStatus();
        }, delayMs);
    }

    function normalizeStatus(status) {
        return (status || "").toUpperCase();
    }

    function statusText(status) {
        const mapping = {
            PENDING: "待处理",
            QUEUED: "排队中",
            RUNNING: "运行中",
            PREPROCESSING: "预处理中",
            TRAINING_3DGS: "训练 3DGS",
            TRAINING_MESH: "训练 Mesh",
            EXPORTING: "导出结果",
            SUCCESS: "处理完成",
            FAILED: "处理失败",
            CANCELED: "已取消",
            COMPLETED: "处理完成",
        };
        return mapping[normalizeStatus(status)] || status;
    }

    function isActiveStatus(status) {
        const active = [
            "PENDING",
            "QUEUED",
            "RUNNING",
            "PREPROCESSING",
            "TRAINING_3DGS",
            "TRAINING_MESH",
            "EXPORTING",
        ];
        return active.includes(normalizeStatus(status));
    }

    async function loadProject() {
        try {
            const project = await API.getProject(projectId);
            projectName.textContent = project.name;
            projectDesc.textContent = project.description;
        } catch (error) {
            alert("加载工程失败");
            window.location.href = "dashboard.html";
        }
    }

    async function loadAssets() {
        try {
            const assets = await API.getAssets(projectId);
            assetList.innerHTML = assets.map(asset => `
                <li class="list-group-item d-flex justify-content-between align-items-center">
                    <div>
                        ${asset.filename}
                        <span class="badge bg-secondary ms-2">${asset.file_type}</span>
                    </div>
                    <button class="btn btn-sm btn-danger delete-asset-btn" data-id="${asset.id}">删除</button>
                </li>
            `).join("");

            document.querySelectorAll(".delete-asset-btn").forEach(button => {
                button.addEventListener("click", async (event) => {
                    const assetId = event.target.getAttribute("data-id");
                    if (confirm("确定要删除这个素材吗？")) {
                        try {
                            await API.deleteAsset(projectId, assetId);
                            loadAssets();
                        } catch (error) {
                            alert("删除失败: " + error.message);
                        }
                    }
                });
            });
        } catch (error) {
            assetList.innerHTML = '<li class="list-group-item text-danger">素材加载失败</li>';
        }
    }

    async function checkStatus() {
        if (isCheckingStatus) {
            return;
        }
        isCheckingStatus = true;

        try {
            let job = null;
            if (currentTaskId) {
                job = await API.getTask(currentTaskId);
            } else {
                const tasks = await API.listTasks(projectId);
                if (tasks.length > 0) {
                    job = tasks[0];
                }
            }

            if (!job) {
                processProgressContainer.classList.add("hidden");
                processBtn.disabled = false;
                clearStatusPollTimer();
                return;
            }

            currentTaskId = job.id;
            const normalized = normalizeStatus(job.status);

            if (isActiveStatus(normalized)) {
                processBtn.disabled = true;
                processProgressContainer.classList.remove("hidden");
                processProgressBar.classList.remove("bg-danger", "bg-warning");
                processProgressBar.classList.add("progress-bar-animated");
                processProgressBar.style.width = `${job.progress}%`;
                processProgressBar.textContent = `${job.progress}%`;
                processStatus.textContent = `状态: ${statusText(normalized)}`;

                scheduleStatusPoll(POLL_INTERVAL_MS);
            } else if (normalized === "SUCCESS" || normalized === "COMPLETED") {
                processBtn.disabled = false;
                clearStatusPollTimer();
                processProgressContainer.classList.remove("hidden");
                processProgressBar.classList.remove("bg-danger", "bg-warning");
                processProgressBar.style.width = "100%";
                processProgressBar.textContent = "100%";
                processProgressBar.classList.remove("progress-bar-animated");
                processStatus.textContent = "处理完成";
                await loadTaskResult(job.id);
            } else if (normalized === "FAILED") {
                processBtn.disabled = false;
                clearStatusPollTimer();
                processProgressContainer.classList.remove("hidden");
                processProgressBar.style.width = "100%";
                processProgressBar.classList.remove("progress-bar-animated", "bg-warning");
                processProgressBar.classList.add("bg-danger");
                processStatus.innerHTML = `处理失败 <br><small class="text-danger">${job.error_message || "未知错误"}</small>`;
            } else if (normalized === "CANCELED") {
                processBtn.disabled = false;
                clearStatusPollTimer();
                processProgressContainer.classList.remove("hidden");
                processProgressBar.style.width = "100%";
                processProgressBar.classList.remove("progress-bar-animated", "bg-danger");
                processProgressBar.classList.add("bg-warning");
                processStatus.textContent = "任务已取消";
            } else {
                processProgressContainer.classList.add("hidden");
            }
        } catch (error) {
            processBtn.disabled = false;
            processProgressContainer.classList.remove("hidden");
            processProgressBar.classList.remove("progress-bar-animated");
            processStatus.textContent = `状态获取失败：${error.message || "网络异常"}，正在重试...`;
            scheduleStatusPoll(POLL_RETRY_INTERVAL_MS);
        } finally {
            isCheckingStatus = false;
        }
    }

    async function loadTaskResult(taskId) {
        if (resultLoadedTaskId === taskId) {
            return;
        }

        try {
            const result = await API.getTaskResult(taskId);
            const warningMessage =
                (result.artifacts && result.artifacts.warning_message) ||
                (normalizeStatus(result.status) === "SUCCESS" ? result.error_message : null);
            const warningHtml = warningMessage
                ? `<p class="mb-2 text-warning">告警: <small>${warningMessage}</small></p>`
                : "";

            resultContainer.innerHTML = `
                <div class="alert alert-success">
                    <h5>加工完成</h5>
                    <p class="mb-2">状态: <strong>${statusText(result.status)}</strong></p>
                    ${warningHtml}
                    <p class="mb-2">输出目录: <small class="text-muted">${result.output_path || "-"}</small></p>
                    <p class="mb-2">日志目录: <small class="text-muted">${result.log_path || "-"}</small></p>
                    <button id="download-result-btn" class="btn btn-primary btn-sm" type="button">下载结果</button>
                </div>
            `;

            const downloadBtn = document.getElementById("download-result-btn");
            if (downloadBtn) {
                downloadBtn.addEventListener("click", async () => {
                    const originalText = downloadBtn.textContent;
                    downloadBtn.disabled = true;
                    downloadBtn.textContent = "下载中...";
                    try {
                        await API.downloadTask(taskId);
                    } catch (error) {
                        alert("下载失败: " + (error.message || "未知错误"));
                    } finally {
                        downloadBtn.disabled = false;
                        downloadBtn.textContent = originalText;
                    }
                });
            }

            resultLoadedTaskId = taskId;
        } catch (error) {
            resultLoadedTaskId = null;
            resultContainer.innerHTML = `
                <div class="alert alert-warning">
                    <h5>结果加载中断</h5>
                    <p class="mb-2">${error.message || "暂时无法获取结果"}</p>
                    <button id="retry-load-result" class="btn btn-outline-secondary btn-sm">重试加载结果</button>
                </div>
            `;
            const retryBtn = document.getElementById("retry-load-result");
            if (retryBtn) {
                retryBtn.addEventListener("click", () => {
                    loadTaskResult(taskId);
                });
            }
        }
    }

    uploadForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        const files = document.getElementById("file-input").files;
        if (files.length === 0) {
            return;
        }

        const uploadBtn = document.getElementById("upload-btn");
        const progressContainer = document.getElementById("upload-progress-container");
        const progressBar = document.getElementById("upload-progress-bar");
        const uploadStatusText = document.getElementById("upload-status-text");

        uploadBtn.disabled = true;
        progressContainer.classList.remove("hidden");
        progressBar.style.width = "0%";
        progressBar.textContent = "0%";
        uploadStatusText.textContent = `准备上传 ${files.length} 个文件...`;

        try {
            await API.uploadAssets(projectId, files, (loaded, total) => {
                const percent = Math.round((loaded / total) * 100);
                progressBar.style.width = `${percent}%`;
                progressBar.textContent = `${percent}%`;

                const loadedSize = (loaded / 1024 / 1024).toFixed(2);
                const totalSize = (total / 1024 / 1024).toFixed(2);
                uploadStatusText.textContent = `已上传 ${loadedSize}MB / ${totalSize}MB`;
            });

            alert("上传成功");
            uploadForm.reset();
            loadAssets();
            setTimeout(() => {
                progressContainer.classList.add("hidden");
                progressBar.style.width = "0%";
            }, 2000);
        } catch (error) {
            alert("上传失败: " + error.message);
            uploadStatusText.textContent = "上传出错";
        } finally {
            uploadBtn.disabled = false;
        }
    });

    processBtn.addEventListener("click", async () => {
        processBtn.disabled = true;
        try {
            const mode = modeSelector ? modeSelector.value : "both";
            const created = await API.createTask(projectId, mode);
            currentTaskId = created.task_id;
            resultLoadedTaskId = null;
            resultContainer.innerHTML = "";
            processProgressContainer.classList.remove("hidden");
            processProgressBar.classList.remove("bg-danger", "bg-warning");
            processProgressBar.classList.add("progress-bar-animated");
            processProgressBar.style.width = "1%";
            processProgressBar.textContent = "1%";
            processStatus.textContent = "任务已创建，等待调度...";
            clearStatusPollTimer();
            await checkStatus();
        } catch (error) {
            processBtn.disabled = false;
            alert("启动加工失败: " + error.message);
        }
    });

    loadProject();
    loadAssets();
    await checkStatus();
    if (currentTaskId) {
        await loadTaskResult(currentTaskId);
    }

    window.addEventListener("beforeunload", () => {
        clearStatusPollTimer();
    });
});
