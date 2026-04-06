// admin_router.js - 完整修复版

import { createRouter, createWebHistory } from "vue-router";
import { ElMessage } from "element-plus";

const routes = [
  {
    path: "/login",
    name: "Login",
    component: () => import("./admin_Login.vue"),
    meta: { requiresAuth: false },
  },
  {
    path: "/",
    component: () => import("./admin_Layout.vue"),
    meta: { requiresAuth: true },
    children: [
      {
        path: "",
        redirect: "/dashboard",
      },
      {
        path: "dashboard",
        name: "Dashboard",
        component: () => import("./admin_Dashboard.vue"),
        meta: { title: "仪表盘" },
      },
      {
        path: "employees",
        name: "Employees",
        component: () => import("./admin_Employees.vue"),
        meta: { title: "员工管理", permissions: ["employee:view"] },
      },
      {
        path: "screenshots",
        name: "Screenshots",
        component: () => import("./admin_Screenshots.vue"),
        meta: { title: "截图查看", permissions: ["screenshot:view"] },
      },
      {
        path: "clients",
        name: "Clients",
        component: () => import("./admin_Clients.vue"),
        meta: { title: "客户端管理", permissions: ["client:view"] },
      },
      {
        path: "browser",
        name: "Browser",
        component: () => import("./admin_Browser.vue"),
        meta: { title: "浏览历史", permissions: ["browser:view"] },
      },
      {
        path: "apps",
        name: "Apps",
        component: () => import("./admin_Apps.vue"),
        meta: { title: "软件统计", permissions: ["app:view"] },
      },
      {
        path: "files",
        name: "Files",
        component: () => import("./admin_Files.vue"),
        meta: { title: "文件监控", permissions: ["file:view"] },
      },
      {
        path: "stats",
        name: "Stats",
        component: () => import("./admin_Stats.vue"),
        meta: { title: "数据分析", permissions: ["stats:view"] },
      },
      {
        path: "settings",
        name: "Settings",
        component: () => import("./admin_Settings.vue"),
        meta: { title: "系统设置", permissions: ["settings:view"] },
      },
      {
        path: "remote",
        name: "RemoteScreen",
        component: () => import("./admin_RemoteScreen.vue"),
        meta: { title: "远程屏幕", permissions: ["remote:view"] },
      },
      {
        path: "notifications",
        name: "Notifications",
        component: () => import("./admin_Notifications.vue"),
        meta: { title: "通知中心", permissions: ["notification:view"] },
      },
      {
        path: "users",
        name: "Users",
        component: () => import("./admin_Users.vue"),
        meta: { title: "用户管理", permissions: ["user:view"] },
      },
      {
        path: "roles",
        name: "Roles",
        component: () => import("./admin_Roles.vue"),
        meta: { title: "角色管理", permissions: ["role:view"] },
      },
      {
        path: "site-management",
        name: "SiteManagement",
        component: () => import("./admin_SiteManagement.vue"),
        meta: { title: "出款管理", permissions: ["site:view"] },
      },
      {
        path: "site-stats",
        name: "SiteStats",
        component: () => import("./admin_SiteStats.vue"),
        meta: { title: "出款统计", permissions: ["site:stats:view"] },
      },
      {
        path: "monthly-stats",
        name: "MonthlyStats",
        component: () => import("./admin_MonthlyStats.vue"),
        meta: { title: "出款汇总", permissions: ["site:summary:view"] },
      },
      {
        path: "external-sync",
        name: "ExternalSync",
        component: () => import("./admin_ExternalSync.vue"),
        meta: { title: "出款同步", permissions: ["site:sync"] },
      },
      {
        path: "attendance",
        name: "Attendance",
        component: () => import("./admin_Attendance.vue"),
        meta: {
          title: "考勤绩效",
          permissions: ["attendance:view"],
          keepAlive: true,
        },
      },
    ],
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});
// admin_router.js - 修复后的权限检查函数

function checkUserPermission(user, requiredPermissions) {
  // 开发环境可开启详细日志
  const isDev = process.env.NODE_ENV === "development";

  if (isDev) {
  }

  // 无权限要求，直接通过
  if (!requiredPermissions?.length) {
    return true;
  }

  if (!user) {
    if (isDev) console.log("❌ 用户信息为空");
    return false;
  }

  // 管理员拥有所有权限
  if (user.role === "admin") {
    if (isDev) console.log("✅ 管理员，允许访问");
    return true;
  }

  // 获取并标准化权限对象
  let perms = user.permissions;

  // 处理字符串格式（从 localStorage 读取时可能出现）
  if (typeof perms === "string") {
    try {
      perms = JSON.parse(perms);
    } catch (e) {
      console.error("解析权限失败:", e);
      return false;
    }
  }

  if (!perms) {
    if (isDev) console.log("❌ 无权限配置");
    return false;
  }

  // 处理数组格式（旧版本兼容）
  if (Array.isArray(perms)) {
    // ✅ 修复：使用 some 而不是 every
    const hasPermission = requiredPermissions.some((perm) =>
      perms.includes(perm),
    );
    if (isDev) console.log(`📋 数组格式权限: ${hasPermission ? "✅" : "❌"}`);
    return hasPermission;
  }

  // 处理对象格式
  switch (perms.type) {
    case "none":
      if (isDev) console.log("❌ 权限类型: none");
      return false;

    case "all":
      if (isDev) console.log("✅ 权限类型: all");
      return true;

    case "custom":
      const permsList = perms.permissions || [];
      // ✅ 关键修复：使用 some 而不是 every
      // 路由只需要用户拥有任意一个所需权限即可访问
      const hasPermission = requiredPermissions.some((perm) =>
        permsList.includes(perm),
      );

      if (isDev) {
      }
      return hasPermission;

    default:
      if (isDev) console.log(`⚠️ 未知权限类型: ${perms.type}`);
      return false;
  }
}
// ✅ 修复：路由守卫，避免无限重定向
// admin_router.js - 添加异步等待

router.beforeEach(async (to, from, next) => {
  // ✅ 关键修复：确保 localStorage 数据已就绪
  // 等待一个微任务周期，让 Pinia store 有机会初始化
  await new Promise((resolve) => setTimeout(resolve, 10));

  const token = localStorage.getItem("token");

  let user = null;
  try {
    const userStr = localStorage.getItem("user");
    if (userStr && userStr !== "null" && userStr !== "undefined") {
      user = JSON.parse(userStr);
    }
  } catch (e) {
    console.error("解析用户信息失败:", e);
  }

  // 开发环境调试日志
  const isDev = process.env.NODE_ENV === "development";
  if (isDev) {
  }

  // 设置页面标题
  if (to.meta.title) {
    document.title = `${to.meta.title} - 员工监控系统`;
  }

  // 检查是否需要认证
  const requiresAuth = to.matched.some((record) => record.meta.requiresAuth);

  if (requiresAuth && !token) {
    next("/login");
    return;
  }

  if (to.path === "/login" && token) {
    next("/dashboard");
    return;
  }

  // 权限检查
  const requiredPermissions = to.meta.permissions;
  if (requiredPermissions && requiredPermissions.length > 0 && user) {
    const hasPermission = checkUserPermission(user, requiredPermissions);

    if (isDev) {
    }

    if (!hasPermission) {
      ElMessage.error("您没有权限访问该页面");

      if (
        from.path === "/dashboard" ||
        from.path === "/" ||
        from.path === to.path
      ) {
        next(false);
      } else {
        next("/dashboard");
      }
      return;
    }
  }

  next();
});

export default router;
