import { createRouter, createWebHistory } from "vue-router";

const routes = [
  {
    path: "/login",
    name: "Login",
    component: () => import("./admin_Login.vue"),
    meta: { requiresAuth: false },
  },
  {
    path: "/",
    component: () => import("./admin_Layout.vue"), // 布局组件
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
        meta: { title: "员工管理" },
      },
      {
        path: "screenshots",
        name: "Screenshots",
        component: () => import("./admin_Screenshots.vue"),
        meta: { title: "截图查看" },
      },
      {
        path: "clients",
        name: "Clients",
        component: () => import("./admin_Clients.vue"),
        meta: { title: "客户端管理" },
      },
      {
        path: "stats",
        name: "Stats",
        component: () => import("./admin_Stats.vue"),
        meta: { title: "数据分析" },
      },
      {
        path: "settings",
        name: "Settings",
        component: () => import("./admin_Settings.vue"),
        meta: { title: "系统设置" },
      },
    ],
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

// 路由守卫
router.beforeEach((to, from, next) => {
  const token = localStorage.getItem("token");

  // 设置页面标题
  document.title = to.meta.title
    ? `${to.meta.title} - 员工监控系统`
    : "员工监控系统";

  // 检查是否需要认证
  if (to.matched.some((record) => record.meta.requiresAuth) && !token) {
    next("/login");
  } else if (to.path === "/login" && token) {
    next("/dashboard");
  } else {
    next();
  }
});

export default router;
