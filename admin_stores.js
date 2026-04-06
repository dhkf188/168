import { defineStore } from "pinia";
import { ref, computed } from "vue";
import { authApi } from "./admin_api";
import { ElMessage } from "element-plus";

// admin_stores.js - 修复 hasPermission 函数

export const useUserStore = defineStore("user", () => {
  const token = ref(localStorage.getItem("token") || "");
  const userInfo = ref(JSON.parse(localStorage.getItem("user") || "null"));
  const isAuthenticated = computed(() => !!token.value);

  // admin_stores.js - 修改 login 函数
  const login = async (username, password) => {
    try {
      const res = await authApi.login(username, password);

      // ✅ 检查是否有 access_token
      if (!res.access_token) {
        console.error("❌ 响应中没有 access_token");
        ElMessage.error("登录失败：服务器返回数据异常");
        return false;
      }

      const userData = res.user || {
        id: res.id,
        username: res.username,
        role: res.role,
      };

      // ✅ 保存 token
      localStorage.setItem("token", res.access_token);
      token.value = res.access_token;

      // ✅ 保存用户信息
      userInfo.value = {
        id: userData.id,
        username: userData.username,
        role: userData.role,
        role_id: userData.role_id,
        role_name: userData.role_name,
        permissions: userData.permissions || { type: "none" },
        last_login: userData.last_login,
        last_ip: userData.last_ip,
        department: userData.department,
        email: userData.email,
        phone: userData.phone,
      };

      localStorage.setItem("user", JSON.stringify(userInfo.value));

      ElMessage.success("登录成功");
      return true;
    } catch (error) {
      console.error("❌ 登录失败:", error);
      console.error("错误详情:", error.response?.data);
      localStorage.removeItem("token");
      localStorage.removeItem("user");
      token.value = "";
      userInfo.value = null;
      ElMessage.error(error.response?.data?.detail || "登录失败");
      return false;
    }
  };

  const logout = () => {
    token.value = "";
    userInfo.value = null;
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    ElMessage.success("已退出登录");
  };

  // admin_stores.js - 修复 checkAuth

  const checkAuth = async () => {
    if (!token.value) return false;

    try {
      const user = await authApi.getCurrentUser();
      // ✅ 确保 permissions 被正确保存
      let permissions = user.permissions;

      // 如果 permissions 是字符串，保持原样
      if (typeof permissions === "string") {
        // 已经是字符串，直接使用
      } else if (permissions && typeof permissions === "object") {
        // 已经是对象
      } else {
        permissions = { type: "none" };
      }

      userInfo.value = {
        id: user.id,
        username: user.username,
        role: user.role,
        role_id: user.role_id,
        role_name: user.role_name,
        permissions: permissions,
        department: user.department,
        email: user.email,
        phone: user.phone,
      };

      localStorage.setItem("user", JSON.stringify(userInfo.value));
      return true;
    } catch (error) {
      logout();
      return false;
    }
  };

  // ✅ 修复：增强权限检查函数
  // admin_stores.js - 修复 hasPermission 函数
  const hasPermission = (permission) => {
    const user = userInfo.value;
    if (!user) {
      return false;
    }

    // 超级管理员拥有所有权限
    if (user.role === "admin") {
      return true;
    }

    // ✅ 关键修复：获取用户的权限配置
    let permissions = user.permissions;

    if (!permissions) {
      return false;
    }

    // 如果是字符串，尝试解析
    if (typeof permissions === "string") {
      try {
        permissions = JSON.parse(permissions);
      } catch (e) {
        console.error("解析权限失败:", e);
        return false;
      }
    }

    // ✅ 关键修复：如果权限是 "none" 类型
    if (permissions.type === "none") {
      return false;
    }

    // 如果权限是 "all" 类型
    if (permissions.type === "all") {
      return true;
    }

    // 如果是自定义权限列表
    if (permissions.type === "custom") {
      const permsList = permissions.permissions || [];
      const hasPerm = permsList.includes(permission);

      return hasPerm;
    }

    // 兼容旧格式（直接数组）
    if (Array.isArray(permissions)) {
      const hasPerm = permissions.includes(permission);

      return hasPerm;
    }

    return false;
  };

  return {
    token,
    userInfo,
    isAuthenticated,
    login,
    logout,
    checkAuth,
    hasPermission,
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
