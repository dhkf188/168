import { defineStore } from "pinia";
import { ref, computed } from "vue";
import { authApi } from "./admin_api";
import { ElMessage } from "element-plus";

export const useUserStore = defineStore("user", () => {
  const token = ref(localStorage.getItem("token") || "");
  const userInfo = ref(JSON.parse(localStorage.getItem("user") || "null"));
  const isAuthenticated = computed(() => !!token.value);

  // 登录
  const login = async (username, password) => {
    try {
      const res = await authApi.login(username, password);
      token.value = res.access_token;
      userInfo.value = {
        username: res.username,
        role: res.role,
      };

      localStorage.setItem("token", res.access_token);
      localStorage.setItem("user", JSON.stringify(userInfo.value));

      ElMessage.success("登录成功");
      return true;
    } catch (error) {
      console.error("登录失败:", error);
      return false;
    }
  };

  // 登出
  const logout = () => {
    token.value = "";
    userInfo.value = null;
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    ElMessage.success("已退出登录");
  };

  // 检查登录状态
  const checkAuth = async () => {
    if (!token.value) return false;

    try {
      const user = await authApi.getCurrentUser();
      userInfo.value = {
        username: user.username,
        role: user.role,
      };
      return true;
    } catch (error) {
      logout();
      return false;
    }
  };

  return {
    token,
    userInfo,
    isAuthenticated,
    login,
    logout,
    checkAuth,
  };
});

export const useAppStore = defineStore("app", () => {
  const sidebarCollapsed = ref(
    localStorage.getItem("sidebarCollapsed") === "true",
  );
  const theme = ref(localStorage.getItem("theme") || "light");

  const toggleSidebar = () => {
    sidebarCollapsed.value = !sidebarCollapsed.value;
    localStorage.setItem("sidebarCollapsed", sidebarCollapsed.value);
  };

  const setTheme = (newTheme) => {
    theme.value = newTheme;
    localStorage.setItem("theme", newTheme);
    // 应用主题
    document.documentElement.setAttribute("data-theme", newTheme);
  };

  return {
    sidebarCollapsed,
    theme,
    toggleSidebar,
    setTheme,
  };
});
