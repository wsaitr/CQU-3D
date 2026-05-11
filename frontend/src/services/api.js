export const API_BASE_URL = window.location.port === "3000" || window.location.port === "5173"
    ? "http://localhost:8000/api/v1"
    : "/api/v1";

class API {
    static get token() {
        return localStorage.getItem("access_token");
    }

    static async request(endpoint, method = "GET", body = null, isFile = false) {
        const headers = {};
        if (this.token) {
            headers["Authorization"] = `Bearer ${this.token}`;
        }
        
        const options = {
            method,
            headers,
        };

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
                    const error = await response.json();
                    throw new Error(error.detail || "登录失败");
                }
                localStorage.removeItem("access_token");
                window.dispatchEvent(new CustomEvent('unauthorized'));
                throw new Error("登录已过期，请重新登录");
            }
            if (response.status === 204) {
                return null;
            }
            if (!response.ok) {
                const error = await response.json();
                let errorMessage = error.detail || "请求失败";
                if (Array.isArray(errorMessage)) {
                    errorMessage = errorMessage.join('\n');
                }
                throw new Error(errorMessage);
            }
            return await response.json();
        } catch (error) {
            console.error("API Error:", error);
            if (error.message === "Failed to fetch") {
                throw new Error("无法连接到服务器，请确保后端服务已启动");
            }
            throw error;
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

    static async logout() {
        localStorage.removeItem("access_token");
        window.dispatchEvent(new CustomEvent('unauthorized'));
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

    static async uploadAssets(projectId, files, onProgress) {
        return new Promise((resolve, reject) => {
            const formData = new FormData();
            for (let i = 0; i < files.length; i++) {
                formData.append("files", files[i]);
            }

            const xhr = new XMLHttpRequest();
            xhr.open("POST", `${API_BASE_URL}/projects/${projectId}/assets`);
            xhr.setRequestHeader("Authorization", `Bearer ${this.token}`);

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
                    } catch {
                        resolve(xhr.response);
                    }
                } else {
                    if (xhr.status === 401) {
                        localStorage.removeItem("access_token");
                        window.dispatchEvent(new CustomEvent('unauthorized'));
                        reject(new Error("登录已过期，请重新登录"));
                        return;
                    }
                    try {
                        const error = JSON.parse(xhr.response);
                        let errorMessage = error.detail || "上传失败";
                        if (Array.isArray(errorMessage)) {
                            errorMessage = errorMessage.join('\n');
                        }
                        reject(new Error(errorMessage));
                    } catch {
                        reject(new Error(xhr.statusText || "上传失败"));
                    }
                }
            };

            xhr.onerror = () => reject(new Error("网络错误，请检查服务器连接"));
            xhr.send(formData);
        });
    }

    static async getAssets(projectId) {
        return await this.request(`/projects/${projectId}/assets`);
    }

    static async triggerProcess(projectId) {
        return await this.request(`/projects/${projectId}/process`, "POST");
    }

    static async getProcessStatus(projectId) {
        return await this.request(`/projects/${projectId}/process`);
    }

    static async getResult(projectId) {
        return await this.request(`/projects/${projectId}/result`);
    }

    static getPlyUrl(projectId) {
        return `${API_BASE_URL}/projects/${projectId}/result.ply`;
    }

    static async deleteAsset(projectId, assetId) {
        return await this.request(`/projects/${projectId}/assets/${assetId}`, "DELETE");
    }

    static async deleteProject(projectId) {
        return await this.request(`/projects/${projectId}`, "DELETE");
    }
}

export default API;
