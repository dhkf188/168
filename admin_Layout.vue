<template>
  <el-container class="layout">
    <!-- 侧边栏 -->
    <el-aside :width="sidebarWidth" class="sidebar">
      <div class="logo">
        <el-icon :size="32"><Camera /></el-icon>
        <span v-show="!appStore.sidebarCollapsed" class="logo-text"
          >员工监控系统</span
        >
      </div>

      <el-menu
        :default-active="activeMenu"
        class="sidebar-menu"
        :collapse="appStore.sidebarCollapsed"
        :collapse-transition="true"
        router
        background-color="#304156"
        text-color="#bfcbd9"
        active-text-color="#409EFF"
      >
        <el-menu-item index="/dashboard">
          <el-icon><Odometer /></el-icon>
          <span>仪表盘</span>
        </el-menu-item>
        <el-menu-item index="/employees">
          <el-icon><User /></el-icon>
          <span>员工管理</span>
        </el-menu-item>
        <el-menu-item index="/screenshots">
          <el-icon><Picture /></el-icon>
          <span>截图查看</span>
        </el-menu-item>
        <el-menu-item index="/clients">
          <el-icon><Monitor /></el-icon>
          <span>客户端管理</span>
        </el-menu-item>
        <el-menu-item index="/stats">
          <el-icon><DataLine /></el-icon>
          <span>数据分析</span>
        </el-menu-item>
        <el-menu-item index="/settings">
          <el-icon><Setting /></el-icon>
          <span>系统设置</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <!-- 头部 -->
      <el-header class="header">
        <div class="header-left">
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
          <el-tooltip content="全屏" placement="bottom">
            <el-button
              class="header-btn"
              :icon="isFullscreen ? FullScreenExit : FullScreen"
              @click="toggleFullscreen"
              text
            />
          </el-tooltip>

          <el-badge
            :value="notificationCount"
            :hidden="notificationCount === 0"
            class="notification-badge"
          >
            <el-dropdown trigger="click">
              <el-button class="header-btn" :icon="Bell" text />
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item
                    v-for="notif in notifications"
                    :key="notif.id"
                  >
                    <div class="notification-item">
                      <div class="notification-title">{{ notif.title }}</div>
                      <div class="notification-time">{{ notif.time }}</div>
                    </div>
                  </el-dropdown-item>
                  <el-dropdown-item divided>
                    <el-button link type="primary" @click="viewAllNotifications"
                      >查看全部</el-button
                    >
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </el-badge>

          <el-dropdown @command="handleCommand">
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
          <span class="version">版本 1.0.0</span>
        </div>
      </el-footer>
    </el-container>

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
import { ref, computed, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
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
} from "@element-plus/icons-vue";
import { useUserStore, useAppStore } from "./admin_stores";

const route = useRoute();
const router = useRouter();
const userStore = useUserStore();
const appStore = useAppStore();

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
const notifications = ref([
  { id: 1, title: "新客户端注册", time: "5分钟前" },
  { id: 2, title: "存储空间不足", time: "10分钟前" },
  { id: 3, title: "备份完成", time: "1小时前" },
]);

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

const viewAllNotifications = () => ElMessage.info("功能开发中...");

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

const submitPassword = async () => {
  if (!passwordFormRef.value) return;
  await passwordFormRef.value.validate((valid) => {
    if (valid) {
      passwordLoading.value = true;
      setTimeout(() => {
        ElMessage.success("密码修改成功");
        passwordDialogVisible.value = false;
        passwordForm.value = {
          oldPassword: "",
          newPassword: "",
          confirmPassword: "",
        };
        passwordLoading.value = false;
      }, 1000);
    }
  });
};

watch(
  route,
  (to) => {
    addView(to);
    activeTab.value = to.path;
  },
  { immediate: true },
);
</script>

<style scoped>
.layout {
  height: 100vh;
}
.sidebar {
  background: #304156;
  overflow: hidden;
  transition: width 0.3s;
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
}
.logo-text {
  font-size: 16px;
  font-weight: 500;
  white-space: nowrap;
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
