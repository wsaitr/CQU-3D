const API_BASE = "/api";

const healthBadge = document.getElementById("healthBadge");
const taskCount = document.getElementById("taskCount");
const taskForm = document.getElementById("taskForm");
const submitHint = document.getElementById("submitHint");
const submitBtn = document.getElementById("submitBtn");
const taskRows = document.getElementById("taskRows");

const detailEmpty = document.getElementById("detailEmpty");
const detailPanel = document.getElementById("detailPanel");
const dTaskId = document.getElementById("dTaskId");
const dStatus = document.getElementById("dStatus");
const dProgress = document.getElementById("dProgress");
const dMode = document.getElementById("dMode");
const dError = document.getElementById("dError");
const dOutput = document.getElementById("dOutput");
const dLog = document.getElementById("dLog");
const cancelBtn = document.getElementById("cancelBtn");
const refreshDetailBtn = document.getElementById("refreshDetailBtn");
const resultLinks = document.getElementById("resultLinks");

let selectedTaskId = null;
let latestTasks = [];

function statusText(status) {
  const mapping = {
    PENDING: "待处理",
    QUEUED: "排队中",
    RUNNING: "运行中",
    PREPROCESSING: "预处理中",
    TRAINING_3DGS: "训练 3DGS",
    TRAINING_MESH: "训练 Mesh",
    EXPORTING: "导出中",
    SUCCESS: "成功",
    FAILED: "失败",
    CANCELED: "已取消",
  };
  return mapping[(status || "").toUpperCase()] || status;
}

function formatTime(value) {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, options);
  if (!response.ok) {
    let detail = "请求失败";
    try {
      const payload = await response.json();
      detail = payload.detail || detail;
    } catch (_) {
      // ignore
    }
    throw new Error(detail);
  }
  return response.json();
}

async function refreshHealth() {
  try {
    const data = await request("/health");
    if (data.status === "ok") {
      healthBadge.textContent = "API/DB/Redis 正常";
      healthBadge.style.background = "#d8f1e8";
      healthBadge.style.color = "#0f6f58";
    } else {
      healthBadge.textContent = "服务降级";
      healthBadge.style.background = "#f6e6cc";
      healthBadge.style.color = "#8a5a14";
    }
  } catch (error) {
    healthBadge.textContent = "无法连接 API";
    healthBadge.style.background = "#f8dbd7";
    healthBadge.style.color = "#98251a";
  }
}

function renderTaskRows() {
  if (!latestTasks.length) {
    taskRows.innerHTML = '<tr><td colspan="5">暂无任务</td></tr>';
    taskCount.textContent = "任务数 0";
    return;
  }

  taskCount.textContent = `任务数 ${latestTasks.length}`;
  taskRows.innerHTML = latestTasks
    .map(
      (task) => `
        <tr data-clickable="1" data-task-id="${task.id}">
          <td>${task.id}</td>
          <td>${statusText(task.status)}</td>
          <td>${task.progress}%</td>
          <td>${escapeHtml(task.mode)}</td>
          <td>${formatTime(task.created_at)}</td>
        </tr>
      `
    )
    .join("");

  document.querySelectorAll("tr[data-task-id]").forEach((row) => {
    row.addEventListener("click", () => {
      selectedTaskId = Number(row.dataset.taskId);
      loadTaskDetail();
    });
  });
}

async function refreshTaskList() {
  try {
    latestTasks = await request("/tasks?limit=200");
    renderTaskRows();
    if (selectedTaskId && latestTasks.some((item) => item.id === selectedTaskId)) {
      await loadTaskDetail();
    }
  } catch (error) {
    taskRows.innerHTML = `<tr><td colspan="5">任务列表加载失败: ${escapeHtml(error.message)}</td></tr>`;
  }
}

function renderResultLinks(result) {
  const links = [];
  const urls = result?.artifacts?.download_urls || {};
  const labels = {
    archive: "下载结果压缩包",
    three_dgs: "打开 3DGS 目录",
    mesh: "打开 Mesh 目录",
    output: "打开输出目录",
    preview: "打开预览图",
    log: "查看日志",
    meta: "下载元数据",
  };

  Object.keys(urls)
    .sort()
    .forEach((key) => {
      const url = urls[key];
      if (!url) {
        return;
      }
      const label = labels[key] || `下载 ${key}`;
      links.push(`<a href="${url}" target="_blank">${label}</a>`);
    });

  resultLinks.innerHTML = links.length ? links.join("") : "暂无可下载产物";
}

async function loadTaskDetail() {
  if (!selectedTaskId) {
    return;
  }

  try {
    const task = await request(`/tasks/${selectedTaskId}`);
    const result = await request(`/tasks/${selectedTaskId}/result`);

    detailEmpty.classList.add("hidden");
    detailPanel.classList.remove("hidden");

    dTaskId.textContent = String(task.id);
    dStatus.textContent = statusText(task.status);
    dProgress.textContent = `${task.progress}%`;
    dMode.textContent = task.mode;
    dError.textContent = task.error_message || "-";
    dOutput.textContent = task.output_path || "-";
    dLog.textContent = task.log_path || "-";

    renderResultLinks(result);
  } catch (error) {
    detailEmpty.classList.remove("hidden");
    detailPanel.classList.add("hidden");
    detailEmpty.textContent = `加载任务详情失败: ${error.message}`;
  }
}

taskForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  submitHint.textContent = "";
  submitBtn.disabled = true;

  const mode = document.getElementById("mode").value;
  const file = document.getElementById("file").files[0];
  const sourceVideoPath = document.getElementById("sourceVideoPath").value.trim();
  const userId = document.getElementById("userId").value.trim();
  const idempotencyKey = document.getElementById("idempotencyKey").value.trim();

  try {
    let response;

    if (file || sourceVideoPath || userId || idempotencyKey) {
      const form = new FormData();
      form.append("mode", mode);
      if (file) {
        form.append("file", file);
      }
      if (sourceVideoPath) {
        form.append("source_video_path", sourceVideoPath);
      }
      if (userId) {
        form.append("user_id", userId);
      }
      if (idempotencyKey) {
        form.append("idempotency_key", idempotencyKey);
      }
      response = await request("/tasks", { method: "POST", body: form });
    } else {
      const body = {
        mode,
      };
      response = await request("/tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
    }

    submitHint.textContent = `创建成功: task_id=${response.task_id}，状态=${statusText(response.status)}${
      response.deduplicated ? "（幂等返回）" : ""
    }`;
    selectedTaskId = Number(response.task_id);
    await refreshTaskList();
    await loadTaskDetail();
  } catch (error) {
    submitHint.textContent = `创建失败: ${error.message}`;
  } finally {
    submitBtn.disabled = false;
  }
});

cancelBtn.addEventListener("click", async () => {
  if (!selectedTaskId) {
    return;
  }
  try {
    const result = await request(`/tasks/${selectedTaskId}/cancel`, { method: "POST" });
    submitHint.textContent = `取消结果: ${result.message}`;
    await refreshTaskList();
    await loadTaskDetail();
  } catch (error) {
    submitHint.textContent = `取消失败: ${error.message}`;
  }
});

refreshDetailBtn.addEventListener("click", async () => {
  await loadTaskDetail();
});

async function boot() {
  await refreshHealth();
  await refreshTaskList();
  setInterval(refreshHealth, 15000);
  setInterval(refreshTaskList, 5000);
}

boot();
