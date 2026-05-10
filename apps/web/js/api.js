function resolveApiBaseUrl() {
    if (typeof window === "undefined") {
        return "/api";
    }

    if (window.__API_BASE_URL__) {
        return String(window.__API_BASE_URL__);
    }

    if (window.location.port === "3000") {
        const configuredPort = localStorage.getItem("api_port") || "28000";
        return `${window.location.protocol}//${window.location.hostname}:${configuredPort}/api`;
    }

    return "/api";
}

const API_BASE_URL = resolveApiBaseUrl();
const DEFAULT_REQUEST_TIMEOUT_MS = 15000;

class API {
    static get token() {
        return localStorage.getItem("access_token");
    }

    static async request(endpoint, method = "GET", body = null, isFile = false, timeoutMs = DEFAULT_REQUEST_TIMEOUT_MS) {
        const headers = {};
        if (this.token) {
            headers["Authorization"] = `Bearer ${this.token}`;
        }

        const options = { method, headers };
        const controller = new AbortController();
        const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
        options.signal = controller.signal;

        if (body) {
            if (isFile) {
                options.body = body;
            } else if (method === "POST" && endpoint.includes("auth/login")) {
                options.body = body;
            } else {
                headers["Content-Type"] = "application/json";
                options.body = JSON.stringify(body);
            }
        }

        try {
            const response = await fetch(`${API_BASE_URL}${endpoint}`, options);
            if (response.status === 401) {
                if (endpoint.includes("auth/login")) {
                    const error = await this.parseErrorResponse(response);
                    throw new Error(error.detail || "登录失败");
                }
                localStorage.removeItem("access_token");
                window.location.href = "index.html";
                return null;
            }
            if (response.status === 204) {
                return null;
            }
            if (!response.ok) {
                const error = await this.parseErrorResponse(response);
                let errorMessage = error.detail || "请求失败";
                if (Array.isArray(errorMessage)) {
                    errorMessage = errorMessage.join("\n");
                }
                throw new Error(errorMessage);
            }
            return await response.json();
        } catch (error) {
            if (error.name === "AbortError") {
                throw new Error("请求超时，请稍后重试");
            }
            if (error instanceof TypeError && /failed to fetch|networkerror/i.test(error.message || "")) {
                throw new Error("无法连接到服务器，请确保后端服务已启动");
            }
            throw error;
        } finally {
            window.clearTimeout(timeoutId);
        }
    }

    static async parseErrorResponse(response) {
        try {
            return await response.json();
        } catch (error) {
            const text = await response.text();
            return { detail: text || `请求失败 (${response.status})` };
        }
    }

    static async login(username, password) {
        const formData = new FormData();
        formData.append("username", username);
        formData.append("password", password);
        const data = await this.request("/auth/login", "POST", formData);
        localStorage.setItem("access_token", data.access_token);
        return data;
    }

    static async register(username, email, password) {
        return await this.request("/auth/register", "POST", { username, email, password });
    }

    static async getProjects() {
        return await this.request("/projects");
    }

    static async createProject(name, description) {
        return await this.request("/projects", "POST", { name, description });
    }

    static async getProject(id) {
        return await this.request(`/projects/${id}`);
    }

    static async deleteProject(projectId) {
        return await this.request(`/projects/${projectId}`, "DELETE");
    }

    static async uploadAssets(projectId, files, onProgress) {
        return new Promise((resolve, reject) => {
            const formData = new FormData();
            for (let i = 0; i < files.length; i++) {
                formData.append("files", files[i]);
            }

            const xhr = new XMLHttpRequest();
            xhr.open("POST", `${API_BASE_URL}/projects/${projectId}/assets`);
            xhr.timeout = 300000;
            if (this.token) {
                xhr.setRequestHeader("Authorization", `Bearer ${this.token}`);
            }

            if (onProgress) {
                xhr.upload.onprogress = (event) => {
                    if (event.lengthComputable) {
                        onProgress(event.loaded, event.total);
                    }
                };
            }

            xhr.onload = () => {
                if (xhr.status >= 200 && xhr.status < 300) {
                    try {
                        resolve(JSON.parse(xhr.response));
                    } catch (error) {
                        resolve(xhr.response);
                    }
                } else {
                    try {
                        const error = JSON.parse(xhr.response);
                        let errorMessage = error.detail || "上传失败";
                        if (Array.isArray(errorMessage)) {
                            errorMessage = errorMessage.join("\n");
                        }
                        reject(new Error(errorMessage));
                    } catch (error) {
                        reject(new Error(xhr.statusText || "上传失败"));
                    }
                }
            };

            xhr.onerror = () => reject(new Error("网络错误，请检查服务器连接"));
            xhr.ontimeout = () => reject(new Error("上传超时，请稍后重试"));
            xhr.send(formData);
        });
    }

    static async getAssets(projectId) {
        return await this.request(`/projects/${projectId}/assets`);
    }

    static async deleteAsset(projectId, assetId) {
        return await this.request(`/projects/${projectId}/assets/${assetId}`, "DELETE");
    }

    static async createTask(projectId, mode = "both", sourceVideoPath = null) {
        return await this.request("/tasks", "POST", {
            project_id: Number(projectId),
            mode,
            source_video_path: sourceVideoPath,
        });
    }

    static async listTasks(projectId = null) {
        const query = projectId ? `?project_id=${projectId}` : "";
        return await this.request(`/tasks${query}`);
    }

    static async getTask(taskId) {
        return await this.request(`/tasks/${taskId}`);
    }

    static async getTaskResult(taskId) {
        return await this.request(`/tasks/${taskId}/result`);
    }

    static async cancelTask(taskId) {
        return await this.request(`/tasks/${taskId}/cancel`, "POST");
    }

    static getTaskDownloadUrl(taskId) {
        return `${API_BASE_URL}/tasks/${taskId}/download`;
    }

    static _extractFilename(contentDisposition) {
        if (!contentDisposition) {
            return null;
        }

        const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i);
        if (utf8Match && utf8Match[1]) {
            try {
                return decodeURIComponent(utf8Match[1].trim().replace(/^"|"$/g, ""));
            } catch (_) {
                return utf8Match[1].trim().replace(/^"|"$/g, "");
            }
        }

        const asciiMatch = contentDisposition.match(/filename="?([^";]+)"?/i);
        if (asciiMatch && asciiMatch[1]) {
            return asciiMatch[1].trim();
        }

        return null;
    }

    static async downloadTask(taskId, fallbackFilename = "result.zip") {
        const headers = {};
        if (this.token) {
            headers["Authorization"] = `Bearer ${this.token}`;
        }

        const response = await fetch(`${API_BASE_URL}/tasks/${taskId}/download`, {
            method: "GET",
            headers,
        });

        if (response.status === 401) {
            localStorage.removeItem("access_token");
            window.location.href = "index.html";
            return;
        }

        if (!response.ok) {
            const error = await this.parseErrorResponse(response);
            let errorMessage = error.detail || "下载失败";
            if (Array.isArray(errorMessage)) {
                errorMessage = errorMessage.join("\n");
            }
            throw new Error(errorMessage);
        }

        const blob = await response.blob();
        const filename =
            this._extractFilename(response.headers.get("content-disposition")) || fallbackFilename;

        const blobUrl = window.URL.createObjectURL(blob);
        try {
            const link = document.createElement("a");
            link.href = blobUrl;
            link.download = filename;
            document.body.appendChild(link);
            link.click();
            link.remove();
        } finally {
            window.URL.revokeObjectURL(blobUrl);
        }
    }

    static async triggerProcess(projectId, mode = "both", sourceVideoPath = null) {
        return await this.request(`/projects/${projectId}/process`, "POST", {
            mode,
            source_video_path: sourceVideoPath,
        });
    }

    static async getProcessStatus(projectId) {
        return await this.request(`/projects/${projectId}/process`);
    }

    static async getResult(projectId) {
        return await this.request(`/projects/${projectId}/result`);
    }
}
