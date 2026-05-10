document.addEventListener("DOMContentLoaded", () => {
    const loginForm = document.getElementById("login-form");
    const registerForm = document.getElementById("register-form");
    const toggleLinks = document.querySelectorAll(".toggle-auth");

    if (localStorage.getItem("access_token")) {
        window.location.href = "dashboard.html";
    }

    if (toggleLinks) {
        toggleLinks.forEach(link => {
            link.addEventListener("click", (event) => {
                event.preventDefault();
                document.getElementById("login-container").classList.toggle("hidden");
                document.getElementById("register-container").classList.toggle("hidden");
            });
        });
    }

    if (loginForm) {
        loginForm.addEventListener("submit", async (event) => {
            event.preventDefault();
            const username = loginForm.username.value;
            const password = loginForm.password.value;
            try {
                await API.login(username, password);
                window.location.href = "dashboard.html";
            } catch (error) {
                alert("登录失败: " + error.message);
            }
        });
    }

    if (registerForm) {
        registerForm.addEventListener("submit", async (event) => {
            event.preventDefault();

            const usernameInput = registerForm.elements["username"];
            const emailInput = registerForm.elements["email"];
            const passwordInput = registerForm.elements["password"];

            if (!usernameInput || !emailInput || !passwordInput) {
                alert("表单元素缺失，请刷新页面重试");
                return;
            }

            const username = usernameInput.value.trim();
            const email = emailInput.value.trim();
            const password = passwordInput.value;

            if (!username || !email || !password) {
                alert("请填写所有必填项");
                return;
            }

            try {
                await API.register(username, email, password);
                alert("注册成功，请登录");
                document.getElementById("login-container").classList.remove("hidden");
                document.getElementById("register-container").classList.add("hidden");
            } catch (error) {
                alert("注册失败: " + error.message);
            }
        });
    }
});
