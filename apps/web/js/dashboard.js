document.addEventListener("DOMContentLoaded", async () => {
    if (!API.token) {
        window.location.href = "index.html";
        return;
    }

    const projectList = document.getElementById("project-list");
    const taskList = document.getElementById("task-list");
    const createProjectForm = document.getElementById("create-project-form");
    const logoutBtn = document.getElementById("logout-btn");

    function statusText(status) {
        const mapping = {
            PENDING: "待处理",
            QUEUED: "排队中",
            RUNNING: "运行中",
            PREPROCESSING: "预处理中",
            TRAINING_3DGS: "训练 3DGS",
            TRAINING_MESH: "训练 Mesh",
            EXPORTING: "导出结果",
            SUCCESS: "完成",
            FAILED: "失败",
            CANCELED: "已取消",
            COMPLETED: "完成",
        };
        return mapping[(status || "").toUpperCase()] || status;
    }

    function formatDate(value) {
        if (!value) {
            return "-";
        }
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) {
            return value;
        }
        return date.toLocaleString();
    }

    logoutBtn.addEventListener("click", () => {
        localStorage.removeItem("access_token");
        window.location.href = "index.html";
    });

    async function loadProjects() {
        try {
            const projects = await API.getProjects();
            projectList.innerHTML = projects.map(project => `
                <div class="col-md-4 mb-3">
                    <div class="card">
                        <div class="card-body">
                            <h5 class="card-title text-truncate" title="${project.name}">${project.name}</h5>
                            <p class="card-text text-truncate" title="${project.description || ""}">${project.description || "无描述"}</p>
                            <div class="d-flex justify-content-between gap-2">
                                <a href="project.html?id=${project.id}" class="btn btn-primary btn-sm flex-grow-1">查看详情</a>
                                <button class="btn btn-danger btn-sm delete-project-btn" data-id="${project.id}">删除</button>
                            </div>
                        </div>
                    </div>
                </div>
            `).join("");

            document.querySelectorAll(".delete-project-btn").forEach(button => {
                button.addEventListener("click", async (event) => {
                    const projectId = event.target.getAttribute("data-id");
                    if (confirm("确定要删除整个工程吗？所有相关文件和数据将被永久删除！")) {
                        try {
                            await API.deleteProject(projectId);
                            loadProjects();
                            loadTasks();
                        } catch (error) {
                            alert("删除工程失败: " + error.message);
                        }
                    }
                });
            });
        } catch (error) {
            projectList.innerHTML = '<div class="text-danger">工程加载失败</div>';
        }
    }

    async function loadTasks() {
        try {
            const tasks = await API.listTasks();
            if (!tasks.length) {
                taskList.innerHTML = '<tr><td colspan="6" class="text-muted">暂无任务</td></tr>';
                return;
            }

            taskList.innerHTML = tasks.map(task => `
                <tr>
                    <td>${task.id}</td>
                    <td>${task.project_id || "-"}</td>
                    <td>${statusText(task.status)}</td>
                    <td>${task.progress}%</td>
                    <td>${formatDate(task.created_at)}</td>
                    <td>${task.project_id ? `<a class="btn btn-sm btn-outline-primary" href="project.html?id=${task.project_id}">查看</a>` : "-"}</td>
                </tr>
            `).join("");
        } catch (error) {
            taskList.innerHTML = '<tr><td colspan="6" class="text-danger">任务加载失败</td></tr>';
        }
    }

    createProjectForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        const name = createProjectForm.name.value;
        const description = createProjectForm.description.value;
        try {
            await API.createProject(name, description);
            createProjectForm.reset();
            const modal = bootstrap.Modal.getInstance(document.getElementById("createProjectModal"));
            modal.hide();
            loadProjects();
            loadTasks();
        } catch (error) {
            alert("创建工程失败: " + error.message);
        }
    });

    loadProjects();
    loadTasks();
    setInterval(loadTasks, 5000);
});
