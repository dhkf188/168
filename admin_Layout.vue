<template>
  <el-container class="layout">
    <div v-if="!userStore.userInfo" class="loading-container">
      <el-icon class="is-loading" size="40"><Loading /></el-icon>
      <span>加载中...</span>
    </div>
    <!-- 侧边栏 -->
    <template v-else>
      <el-aside :width="sidebarWidth" class="sidebar">
        <div class="logo">
          <el-icon :size="32"><Camera /></el-icon>
          <span v-show="!appStore.sidebarCollapsed" class="logo-text"
            >DHPG监控系统</span
          >
        </div>
        <div class="sidebar-menu-container">
          <el-menu
            :default-active="activeMenu"
            class="sidebar-menu"
            :collapse="appStore.sidebarCollapsed"
            :collapse-transition="true"
            router
            background-color="#304156"
            text-color="#bfcbd9"
            active-text-color="#409EFF"
            :key="menuKey"
          >
            <!-- 仪表盘 - 所有人可见，不需要权限 -->
            <el-menu-item index="/dashboard">
              <el-icon><Odometer /></el-icon>
              <span>仪表盘</span>
            </el-menu-item>

            <!-- ✅ 员工管理 -->
            <el-menu-item
              index="/employees"
              v-if="hasPermission('employee:view')"
            >
              <el-icon><User /></el-icon>
              <span>员工管理</span>
            </el-menu-item>

            <!-- ✅ 截图查看 -->
            <el-menu-item
              index="/screenshots"
              v-if="hasPermission('screenshot:view')"
            >
              <el-icon><Picture /></el-icon>
              <span>截图查看</span>
            </el-menu-item>

            <!-- ✅ 远程屏幕 -->
            <el-menu-item index="/remote" v-if="hasPermission('remote:view')">
              <el-icon><VideoCamera /></el-icon>
              <span>远程屏幕</span>
            </el-menu-item>

            <!-- ✅ 浏览历史 -->
            <el-menu-item index="/browser" v-if="hasPermission('browser:view')">
              <el-icon><ChromeFilled /></el-icon>
              <span>浏览历史</span>
            </el-menu-item>

            <!-- ✅ 软件统计 -->
            <el-menu-item index="/apps" v-if="hasPermission('app:view')">
              <el-icon><Grid /></el-icon>
              <span>软件统计</span>
            </el-menu-item>

            <!-- ✅ 文件监控 -->
            <el-menu-item index="/files" v-if="hasPermission('file:view')">
              <el-icon><Folder /></el-icon>
              <span>文件监控</span>
            </el-menu-item>

            <!-- ✅ 数据分析 -->
            <el-menu-item index="/stats" v-if="hasPermission('stats:view')">
              <el-icon><DataLine /></el-icon>
              <span>数据分析</span>
            </el-menu-item>

            <!-- ✅ 客户端管理 -->
            <el-menu-item index="/clients" v-if="hasPermission('client:view')">
              <el-icon><Monitor /></el-icon>
              <span>客户端管理</span>
            </el-menu-item>

            <!-- 出款管理 -->
            <el-menu-item
              index="/site-management"
              v-if="hasPermission('site:view')"
            >
              <el-icon><Grid /></el-icon>
              <span>出款管理</span>
            </el-menu-item>

            <!-- 出款统计 -->
            <el-menu-item
              index="/site-stats"
              v-if="hasPermission('site:stats:view')"
            >
              <el-icon><DataLine /></el-icon>
              <span>出款统计</span>
            </el-menu-item>

            <!-- 出款汇总 -->
            <el-menu-item
              index="/monthly-stats"
              v-if="hasPermission('site:summary:view')"
            >
              <el-icon><TrendCharts /></el-icon>
              <span>出款汇总</span>
            </el-menu-item>

            <!-- 出款同步 -->
            <el-menu-item
              index="/external-sync"
              v-if="hasPermission('site:sync')"
            >
              <el-icon><Connection /></el-icon>
              <span>出款同步</span>
            </el-menu-item>

            <!-- 考勤管理 -->
            <el-menu-item
              index="/attendance"
              v-if="hasPermission('attendance:view')"
            >
              <el-icon><Calendar /></el-icon>
              <span>考勤绩效</span>
            </el-menu-item>

            <!-- 用户管理 -->
            <el-menu-item index="/users" v-if="hasPermission('user:view')">
              <el-icon><UserFilled /></el-icon>
              <span>用户管理</span>
            </el-menu-item>

            <!-- 角色管理 -->
            <el-menu-item index="/roles" v-if="hasPermission('role:view')">
              <el-icon><Avatar /></el-icon>
              <span>角色管理</span>
            </el-menu-item>

            <!-- ✅ 系统设置 -->
            <el-menu-item
              index="/settings"
              v-if="hasPermission('settings:view')"
            >
              <el-icon><Setting /></el-icon>
              <span>系统设置</span>
            </el-menu-item>
          </el-menu>
        </div>
      </el-aside>

      <el-container>
        <!-- 头部 -->
        <el-header class="header">
          <div class="header-left">
            <!-- 折叠/展开侧边栏按钮 -->
            <el-button
              class="toggle-btn"
              :icon="appStore.sidebarCollapsed ? Expand : Fold"
              @click="appStore.toggleSidebar"
              text
            />
            <el-breadcrumb separator="/">
              <el-breadcrumb-item :to="{ path: '/' }">首页</el-breadcrumb-item>
              <el-breadcrumb-item>{{
                currentRoute.meta.title
              }}</el-breadcrumb-item>
            </el-breadcrumb>
          </div>

          <div class="header-right">
            <!-- 全屏按钮 -->
            <el-tooltip content="全屏" placement="bottom">
              <el-button
                class="header-btn"
                :icon="isFullscreen ? FullScreenExit : FullScreen"
                @click="toggleFullscreen"
                text
              />
            </el-tooltip>

            <!-- 通知中心 -->
            <el-badge
              :value="unreadCount"
              :hidden="unreadCount === 0"
              class="notification-badge"
            >
              <el-dropdown
                trigger="click"
                @visible-change="handleDropdownVisible"
              >
                <el-button class="header-btn" :icon="Bell" text />
                <template #dropdown>
                  <el-dropdown-menu class="notification-dropdown">
                    <div class="notification-header">
                      <span class="notification-title">通知中心</span>
                      <div class="notification-actions">
                        <el-button
                          v-if="notifications.length > 0"
                          link
                          type="primary"
                          size="small"
                          @click="markAllAsRead"
                        >
                          全部已读
                        </el-button>
                        <el-button
                          v-if="notifications.length > 0"
                          link
                          type="danger"
                          size="small"
                          @click="clearAllNotifications"
                        >
                          清空
                        </el-button>
                      </div>
                    </div>

                    <el-divider style="margin: 8px 0" />

                    <div
                      class="notification-list"
                      v-loading="notificationLoading"
                    >
                      <template v-if="notifications.length > 0">
                        <el-dropdown-item
                          v-for="notif in notifications"
                          :key="notif.id"
                          :class="[
                            'notification-item',
                            { 'is-unread': !notif.read },
                          ]"
                          @click="handleNotificationClick(notif)"
                        >
                          <div class="notification-content">
                            <div class="notification-title-row">
                              <span class="notification-item-title">{{
                                notif.title
                              }}</span>
                              <el-tag
                                v-if="notif.type"
                                :type="getNotificationType(notif.type)"
                                size="small"
                                effect="plain"
                              >
                                {{ notif.type }}
                              </el-tag>
                            </div>
                            <div
                              class="notification-desc"
                              v-if="notif.description"
                            >
                              {{ notif.description }}
                            </div>
                            <div class="notification-time">
                              {{ formatRelativeTime(notif.created_at) }}
                            </div>
                          </div>
                          <div class="notification-actions">
                            <el-button
                              link
                              type="danger"
                              size="small"
                              @click.stop="deleteNotification(notif.id)"
                            >
                              删除
                            </el-button>
                          </div>
                        </el-dropdown-item>
                      </template>

                      <el-empty
                        v-else
                        description="暂无通知"
                        :image-size="80"
                      />
                    </div>

                    <el-divider style="margin: 8px 0" />

                    <div class="notification-footer">
                      <el-button
                        link
                        type="primary"
                        @click="viewAllNotifications"
                      >
                        查看全部
                      </el-button>
                    </div>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </el-badge>

            <!-- 用户下拉菜单 - 添加 popper-class -->
            <el-dropdown
              @command="handleCommand"
              popper-class="user-dropdown-menu"
            >
              <div class="user-info">
                <el-avatar :size="36" :icon="User" />
                <span class="username">{{
                  userStore.userInfo?.username || "管理员"
                }}</span>
                <el-icon><ArrowDown /></el-icon>
              </div>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="profile">
                    <el-icon><User /></el-icon>个人信息
                  </el-dropdown-item>
                  <el-dropdown-item command="password">
                    <el-icon><Lock /></el-icon>修改密码
                  </el-dropdown-item>
                  <el-dropdown-item divided command="logout">
                    <el-icon><SwitchButton /></el-icon>退出登录
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </el-header>

        <div class="tabs-view" v-if="showTabs">
          <el-tabs
            v-model="activeTab"
            type="card"
            closable
            @tab-remove="removeTab"
            @tab-click="handleTabClick"
          >
            <el-tab-pane
              v-for="item in visitedViews"
              :key="item.path"
              :label="item.title"
              :name="item.path"
            />
          </el-tabs>
        </div>

        <el-main class="main">
          <router-view v-slot="{ Component }">
            <transition name="fade" mode="out-in">
              <keep-alive :include="cachedViews">
                <component :is="Component" />
              </keep-alive>
            </transition>
          </router-view>
        </el-main>

        <el-footer class="footer">
          <div class="footer-content">
            <span>© DHPG监控系统</span>
            <span class="version">版本 4.0.1</span>
          </div>
        </el-footer>
      </el-container>
    </template>

    <el-dialog v-model="passwordDialogVisible" title="修改密码" width="400px">
      <el-form
        ref="passwordFormRef"
        :model="passwordForm"
        :rules="passwordRules"
        label-width="80px"
      >
        <el-form-item label="旧密码" prop="oldPassword">
          <el-input
            v-model="passwordForm.oldPassword"
            type="password"
            show-password
          />
        </el-form-item>
        <el-form-item label="新密码" prop="newPassword">
          <el-input
            v-model="passwordForm.newPassword"
            type="password"
            show-password
          />
        </el-form-item>
        <el-form-item label="确认密码" prop="confirmPassword">
          <el-input
            v-model="passwordForm.confirmPassword"
            type="password"
            show-password
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="passwordDialogVisible = false">取消</el-button>
        <el-button
          type="primary"
          @click="submitPassword"
          :loading="passwordLoading"
        >
          确定
        </el-button>
      </template>
    </el-dialog>
  </el-container>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { Calendar } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  Camera,
  Odometer,
  User,
  Picture,
  Monitor,
  DataLine,
  Setting,
  Fold,
  Expand,
  FullScreen,
  Bell,
  ArrowDown,
  Lock,
  SwitchButton,
  ChromeFilled,
  Grid,
  Folder,
  VideoCamera,
  VideoPause,
  UserFilled,
  Avatar,
  Loading,
} from "@element-plus/icons-vue";
import { useUserStore, useAppStore } from "./admin_stores";
import api from "./admin_api";
import { notificationApi } from "./admin_notification";
import { formatRelativeTime } from "./admin_timezone";

const route = useRoute();
const router = useRouter();
const userStore = useUserStore();
const appStore = useAppStore();

const menuKey = ref(0);
// 监听用户信息变化，刷新菜单
watch(
  () => userStore.userInfo,
  () => {
    menuKey.value++;
  },
  { deep: true },
);

// ==================== 权限检查函数 ====================

const hasPermission = (permission) => {
  const user = userStore.userInfo;
  if (!user) {
    return false;
  }

  // 超级管理员（role 为 admin）拥有所有权限
  if (user.role === "admin") {
    return true;
  }

  // 获取权限配置
  let permissions = user.permissions;

  // 处理字符串格式（从 localStorage 读取时可能出现）
  if (typeof permissions === "string") {
    try {
      permissions = JSON.parse(permissions);
    } catch (e) {
      console.error("解析权限失败:", e);
      return false;
    }
  }

  if (!permissions) {
    return false;
  }

  // 如果权限类型是 "none"
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

const sidebarWidth = computed(() =>
  appStore.sidebarCollapsed ? "64px" : "200px",
);
const currentRoute = computed(() => route);
const showTabs = ref(true);
const activeTab = ref("");
const visitedViews = ref([]);
const cachedViews = ref([]);
const isFullscreen = ref(false);
const notificationCount = ref(3);

const passwordDialogVisible = ref(false);
const passwordLoading = ref(false);
const passwordFormRef = ref(null);
const passwordForm = ref({
  oldPassword: "",
  newPassword: "",
  confirmPassword: "",
});

const passwordRules = {
  oldPassword: [{ required: true, message: "请输入旧密码", trigger: "blur" }],
  newPassword: [
    { required: true, message: "请输入新密码", trigger: "blur" },
    { min: 6, message: "密码至少6位", trigger: "blur" },
  ],
  confirmPassword: [
    { required: true, message: "请确认新密码", trigger: "blur" },
    {
      validator: (rule, value, callback) => {
        if (value !== passwordForm.value.newPassword) {
          callback(new Error("两次输入的密码不一致"));
        } else {
          callback();
        }
      },
      trigger: "blur",
    },
  ],
};

const activeMenu = computed(() => route.path);

const addView = (view) => {
  if (visitedViews.value.some((v) => v.path === view.path)) return;
  visitedViews.value.push({
    path: view.path,
    title: view.meta.title || "未命名",
  });
  if (view.meta.keepAlive) {
    cachedViews.value.push(view.name);
  }
};

const removeTab = (targetPath) => {
  const views = visitedViews.value;
  const index = views.findIndex((v) => v.path === targetPath);
  if (index !== -1) {
    views.splice(index, 1);
    if (targetPath === route.path) {
      const nextView = views[index] || views[index - 1];
      if (nextView) router.push(nextView.path);
    }
  }
};

const handleTabClick = (tab) => router.push(tab.props.name);

const toggleFullscreen = () => {
  if (!document.fullscreenElement) {
    document.documentElement.requestFullscreen();
    isFullscreen.value = true;
  } else {
    if (document.exitFullscreen) {
      document.exitFullscreen();
      isFullscreen.value = false;
    }
  }
};

const handleCommand = (command) => {
  switch (command) {
    case "profile":
      ElMessage.info("功能开发中...");
      break;
    case "password":
      passwordDialogVisible.value = true;
      break;
    case "logout":
      handleLogout();
      break;
  }
};

const handleLogout = () => {
  ElMessageBox.confirm("确定要退出登录吗？", "提示", {
    confirmButtonText: "确定",
    cancelButtonText: "取消",
    type: "info",
  }).then(() => {
    userStore.logout();
    router.push("/login");
  });
};

// 提交修改密码 - 真实API调用
// admin_Layout.vue - submitPassword 函数
const submitPassword = async () => {
  if (!passwordFormRef.value) return;

  const valid = await passwordFormRef.value.validate().catch(() => false);
  if (!valid) return;

  passwordLoading.value = true;

  try {
    const response = await api.post("/auth/change-password", {
      current_password: passwordForm.value.oldPassword,
      new_password: passwordForm.value.newPassword,
    });

    if (response.access_token) {
      // ✅ 获取完整的用户信息
      const userData = response.user || response;

      // 更新store - 保存完整用户信息
      userStore.token = response.access_token;
      userStore.userInfo = {
        id: userData.id,
        username: userData.username,
        role: userData.role,
        role_id: userData.role_id,
        role_name: userData.role_name,
        permissions: userData.permissions, // ✅ 关键
        department: userData.department,
        email: userData.email,
        phone: userData.phone,
        last_login: userData.last_login,
        last_ip: userData.last_ip,
      };

      // 更新localStorage
      localStorage.setItem("token", response.access_token);
      localStorage.setItem("user", JSON.stringify(userStore.userInfo));

      // 更新axios默认头
      api.defaults.headers.common["Authorization"] =
        `Bearer ${response.access_token}`;

      ElMessage.success("密码修改成功，已自动更新登录状态");
    } else {
      ElMessage.success("密码修改成功");
    }

    passwordDialogVisible.value = false;
    passwordForm.value = {
      oldPassword: "",
      newPassword: "",
      confirmPassword: "",
    };
  } catch (error) {
    console.error("修改密码失败:", error);
    const errorMsg = error.response?.data?.detail || "修改密码失败，请重试";
    ElMessage.error(errorMsg);
  } finally {
    passwordLoading.value = false;
  }
};

watch(
  route,
  (to) => {
    addView(to);
    activeTab.value = to.path;
  },
  { immediate: true },
);

// ==================== 通知功能 ====================
const notifications = ref([]);
const unreadCount = ref(0);
const notificationLoading = ref(false);
let pollTimer = null;

// 加载通知列表
const loadNotifications = async () => {
  notificationLoading.value = true;
  try {
    const response = await notificationApi.getNotifications({
      limit: 10,
      unread_first: true,
    });
    notifications.value = response.items || [];
  } catch (error) {
    console.error("加载通知失败:", error);
  } finally {
    notificationLoading.value = false;
  }
};

// 加载未读数量
const loadUnreadCount = async () => {
  try {
    const response = await notificationApi.getUnreadCount();
    unreadCount.value = response.count || 0;
  } catch (error) {
    console.error("加载未读数量失败:", error);
  }
};

// 标记为已读
const markAsRead = async (id) => {
  try {
    await notificationApi.markAsRead(id);
    await loadUnreadCount();
    await loadNotifications(); // 刷新列表
  } catch (error) {
    console.error("标记已读失败:", error);
  }
};

// 全部标记为已读
const markAllAsRead = async () => {
  try {
    await notificationApi.markAllAsRead();
    await loadUnreadCount();
    await loadNotifications();
    ElMessage.success("已全部标记为已读");
  } catch (error) {
    console.error("全部标记已读失败:", error);
  }
};

// 删除单条通知
const deleteNotification = async (id) => {
  try {
    await notificationApi.deleteNotification(id);
    await loadUnreadCount();
    await loadNotifications();
    ElMessage.success("通知已删除");
  } catch (error) {
    console.error("删除通知失败:", error);
  }
};

// 清空所有通知
const clearAllNotifications = () => {
  ElMessageBox.confirm("确定要清空所有通知吗？", "提示", {
    confirmButtonText: "确定",
    cancelButtonText: "取消",
    type: "warning",
  }).then(async () => {
    try {
      await notificationApi.clearAll();
      notifications.value = [];
      unreadCount.value = 0;
      ElMessage.success("通知已清空");
    } catch (error) {
      console.error("清空通知失败:", error);
    }
  });
};

// 点击通知
const handleNotificationClick = (notif) => {
  // 如果未读，标记为已读
  if (!notif.read) {
    markAsRead(notif.id);
  }

  // 根据通知类型跳转
  if (notif.action && notif.action.url) {
    router.push(notif.action.url);
  }
};

// 下拉菜单显示状态变化
const handleDropdownVisible = (visible) => {
  if (visible) {
    // 每次打开下拉菜单时刷新数据
    loadNotifications();
  }
};

// 获取通知类型对应的标签类型
const getNotificationType = (type) => {
  const typeMap = {
    info: "info",
    success: "success",
    warning: "warning",
    error: "danger",
    新客户端注册: "success",
    存储空间不足: "danger",
    备份完成: "info",
    清理完成: "success",
    系统更新: "warning",
  };
  return typeMap[type] || "info";
};

// 查看全部
const viewAllNotifications = () => {
  router.push("/notifications");
};

// 启动轮询
const startPolling = () => {
  // 每60秒检查一次新通知
  pollTimer = setInterval(() => {
    loadUnreadCount();
  }, 60000);
};

// 停止轮询
const stopPolling = () => {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
};

// 在组件挂载时加载数据并启动轮询
onMounted(() => {
  loadUnreadCount();
  loadNotifications();
  startPolling();
});

// 组件卸载时停止轮询
onUnmounted(() => {
  stopPolling();
});
</script>

<style scoped>
.layout {
  height: 100vh;
}
.sidebar {
  background: #304156;
  overflow: hidden;
  transition: width 0.3s;
  display: flex;
  flex-direction: column;
  height: 100vh;
}
.sidebar-menu-container {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
}
.logo {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: white;
  background: #1f2d3d;
  overflow: hidden;
  flex-shrink: 0;
}
.logo-text {
  font-size: 16px;
  font-weight: 500;
  white-space: nowrap;
}

.sidebar-menu-container::-webkit-scrollbar {
  width: 4px;
}

.sidebar-menu-container::-webkit-scrollbar-track {
  background: #1f2d3d;
  border-radius: 4px;
}

.sidebar-menu-container::-webkit-scrollbar-thumb {
  background: #4a5a6e;
  border-radius: 4px;
}

.sidebar-menu-container::-webkit-scrollbar-thumb:hover {
  background: #667eea;
}

.sidebar-menu {
  border-right: none;
}

:deep(.el-menu) {
  border-right: none;
}

:deep(.el-menu-item) {
  padding-left: 24px !important;
}

:deep(.el-menu-item [class^="el-icon"]) {
  font-size: 18px;
}

/* 🆕 新增：折叠时的滚动条 */
.el-menu--collapse .sidebar-menu-container {
  overflow-x: hidden;
}
.sidebar-menu {
  border-right: none;
}
:deep(.el-menu) {
  border-right: none;
}
:deep(.el-menu-item) {
  padding-left: 24px !important;
}
:deep(.el-menu-item [class^="el-icon"]) {
  font-size: 18px;
}
.header {
  background: white;
  border-bottom: 1px solid #e6e6e6;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 20px;
}
.toggle-btn {
  font-size: 20px;
  padding: 8px;
}
.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}
.header-btn {
  font-size: 18px;
  padding: 8px;
}
.notification-badge :deep(.el-badge__content) {
  top: 12px;
  right: 8px;
}
.user-info {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 4px;
  transition: background 0.3s;
}
.user-info:hover {
  background: #f5f5f5;
}
.username {
  font-size: 14px;
  color: #333;
}
.tabs-view {
  background: white;
  padding: 8px 20px 0;
  border-bottom: 1px solid #e6e6e6;
}
:deep(.el-tabs__header) {
  margin: 0;
}
.main {
  background: #f0f2f5;
  padding: 0;
  overflow-y: auto;
}
.footer {
  height: 40px;
  background: white;
  border-top: 1px solid #e6e6e6;
  display: flex;
  align-items: center;
  justify-content: center;
}
.footer-content {
  font-size: 12px;
  color: #999;
}
.version {
  margin-left: 20px;
}
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>

<!-- 全局样式 - 作用于整个页面，用于渲染在 body 下的下拉菜单 -->
<style>
/* ===== 1. 基础容器样式 ===== */
.el-popper {
  --el-popover-padding: 0;
  padding: 0 !important;
  border: none !important;
  margin-top: 8px !important;
}

/* 所有下拉菜单的基础样式 */
.el-dropdown-menu {
  padding: 0 !important;
  border: none !important;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15) !important;
  border-radius: 8px !important;
  overflow: hidden;
  min-width: 120px !important;
}

.el-dropdown-menu__item {
  padding: 10px 16px !important;
  height: auto !important;
  line-height: normal !important;
  font-size: 14px !important;
  color: #333 !important;
  border-bottom: 1px solid #f0f2f5 !important;
  display: flex !important;
  align-items: center !important;
  gap: 8px !important;
  transition: all 0.3s ease !important;
  white-space: nowrap !important;
}

.el-dropdown-menu__item:last-child {
  border-bottom: none !important;
}

.el-dropdown-menu__item:hover {
  background-color: #f5f7fa !important;
  color: #409eff !important;
}

.el-dropdown-menu__item .el-icon {
  font-size: 16px !important;
  color: #909399 !important;
}

.el-dropdown-menu__item:hover .el-icon {
  color: #409eff !important;
}

/* 退出登录项特殊样式 */
.el-dropdown-menu__item:last-child:hover {
  background-color: #fef0f0 !important;
  color: #f56c6c !important;
}

.el-dropdown-menu__item:last-child:hover .el-icon {
  color: #f56c6c !important;
}

/* 分割线样式 */
.el-dropdown-menu__item.is-divided {
  margin-top: 4px !important;
  border-top: 1px solid #ebeef5 !important;
}

/* ===== 2. 用户下拉菜单专用样式（新增）===== */
.user-dropdown-menu {
  min-width: 160px !important;
}

/* 用户菜单项左对齐（覆盖通知菜单的居中样式） */
.user-dropdown-menu .el-dropdown-menu__item {
  justify-content: flex-start !important;
}

/* ===== 3. 通知铃铛图标样式 ===== */
.notification-badge .header-btn {
  position: relative;
}

.notification-badge .header-btn .el-icon {
  font-size: 20px;
}

/* ===== 4. 分割线样式优化 ===== */
.notification-dropdown .el-divider--horizontal {
  margin: 0;
  border-top-color: #ebeef5;
}

/* ===== 5. 通知下拉菜单容器 ===== */
.notification-dropdown {
  width: 360px;
  max-width: 90vw;
  padding: 0 !important;
  margin-top: 8px !important;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15) !important;
  border-radius: 8px !important;
  overflow: hidden;
  border: 1px solid #e4e7ed;
  z-index: 9999 !important;
}

/* 通知菜单头部 */
.notification-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid #ebeef5;
  background-color: #f8f9fa;
}

.notification-title {
  font-weight: 600;
  color: #303133;
  font-size: 15px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.notification-title::before {
  content: "🔔";
  font-size: 14px;
}

.notification-actions {
  display: flex;
  gap: 8px;
}

.notification-actions .el-button {
  padding: 0 4px;
  font-size: 12px;
}

/* 通知列表 */
.notification-list {
  max-height: 400px;
  overflow-y: auto;
  background-color: #fff;
}

/* 通知项 - 覆盖默认的下拉菜单项样式 */
.notification-dropdown .el-dropdown-menu__item {
  display: flex !important;
  justify-content: space-between !important;
  align-items: flex-start !important;
  padding: 14px 16px !important;
  height: auto !important;
  line-height: 1.5 !important;
  white-space: normal !important;
  border-bottom: 1px solid #f0f2f5 !important;
  cursor: pointer;
  transition: all 0.3s ease;
  background-color: transparent !important;
}

.notification-dropdown .el-dropdown-menu__item:last-child {
  border-bottom: none !important;
}

.notification-dropdown .el-dropdown-menu__item:hover {
  background-color: #f5f7fa !important;
  transform: translateX(2px);
}

.notification-dropdown .el-dropdown-menu__item.is-unread {
  background-color: #f0f9ff !important;
  position: relative;
}

.notification-dropdown .el-dropdown-menu__item.is-unread::before {
  content: "";
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 3px;
  background-color: #409eff;
}

.notification-dropdown .el-dropdown-menu__item.is-unread:hover {
  background-color: #e6f7ff !important;
}

/* 通知内容 */
.notification-content {
  flex: 1;
  min-width: 0;
  margin-right: 12px;
}

.notification-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
  flex-wrap: wrap;
}

.notification-item-title {
  font-weight: 500;
  color: #303133;
  font-size: 14px;
  word-break: break-word;
}

.notification-title-row .el-tag {
  margin-left: 2px;
  padding: 0 6px;
  height: 18px;
  line-height: 16px;
  font-size: 10px;
  border-radius: 4px;
  border: none;
}

.notification-desc {
  font-size: 12px;
  color: #606266;
  margin-bottom: 6px;
  line-height: 1.5;
  word-break: break-word;
}

.notification-time {
  font-size: 11px;
  color: #909399;
  display: flex;
  align-items: center;
  gap: 4px;
}

.notification-time::before {
  content: "⏱️";
  font-size: 10px;
  opacity: 0.7;
}

/* 通知项的删除按钮 */
.notification-dropdown .el-dropdown-menu__item .el-button {
  opacity: 0.3;
  transition: all 0.3s ease;
  padding: 4px 6px;
  min-height: auto;
  margin: -4px 0;
  border-radius: 4px;
}

.notification-dropdown .el-dropdown-menu__item .el-button:hover {
  opacity: 1;
  background-color: #fef0f0 !important;
  color: #f56c6c !important;
}

.notification-dropdown .el-dropdown-menu__item:hover .el-button {
  opacity: 0.8;
}

/* 通知底部 */
.notification-footer {
  text-align: center;
  padding: 10px 16px;
  border-top: 1px solid #ebeef5;
  background-color: #f8f9fa;
}

.notification-footer .el-button {
  width: 100%;
  color: #409eff;
  font-size: 13px;
  font-weight: 500;
  padding: 8px 0;
  height: auto;
  transition: all 0.3s;
}

.notification-footer .el-button:hover {
  background-color: #ecf5ff !important;
  transform: translateY(-1px);
}

/* ===== 6. 空状态样式 ===== */
.notification-list .el-empty {
  padding: 40px 0;
  background-color: #fff;
}

.notification-list .el-empty__image {
  width: 80px;
}

.notification-list .el-empty__image svg {
  color: #dcdfe6;
  width: 60px;
  height: 60px;
}

.notification-list .el-empty__description p {
  color: #909399;
  font-size: 13px;
}

/* ===== 7. 自定义滚动条样式 ===== */
.notification-list::-webkit-scrollbar {
  width: 4px;
}

.notification-list::-webkit-scrollbar-track {
  background: #f5f7fa;
  border-radius: 4px;
}

.notification-list::-webkit-scrollbar-thumb {
  background: #dcdfe6;
  border-radius: 4px;
  transition: background 0.3s;
}

.notification-list::-webkit-scrollbar-thumb:hover {
  background: #c0c4cc;
}

/* 加载状态样式 */
.loading-container {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  height: 100vh;
  width: 100%;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  gap: 16px;
}

.loading-container .el-icon {
  font-size: 48px;
}

.loading-container span {
  font-size: 14px;
}

/* ===== 8. 响应式调整 ===== */
@media screen and (max-width: 768px) {
  .notification-dropdown {
    width: 300px;
  }

  .notification-dropdown .el-dropdown-menu__item {
    padding: 10px 12px !important;
  }

  .notification-title-row {
    gap: 4px;
  }

  .notification-item-title {
    font-size: 13px;
  }
}
</style>
