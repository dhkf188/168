<template>
  <div class="login-container">
    <el-card class="login-card" shadow="xl">
      <template #header>
        <div class="login-header">
          <el-icon :size="48"><Camera /></el-icon>
          <h2>DHPG监控系统</h2>
          <p class="subtitle">努力的人都有好运</p>
        </div>
      </template>

      <el-form
        ref="formRef"
        :model="loginForm"
        :rules="rules"
        label-width="0"
        @keyup.enter="handleLogin"
      >
        <el-form-item prop="username">
          <el-input
            v-model="loginForm.username"
            placeholder="用户名"
            :prefix-icon="User"
            size="large"
            clearable
          />
        </el-form-item>

        <el-form-item prop="password">
          <el-input
            v-model="loginForm.password"
            type="password"
            placeholder="密码"
            :prefix-icon="Lock"
            size="large"
            show-password
            clearable
          />
        </el-form-item>

        <el-form-item>
          <el-button
            type="primary"
            :loading="loading"
            @click="handleLogin"
            size="large"
            style="width: 100%"
          >
            登录系统
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <div class="version">
      <el-icon><InfoFilled /></el-icon>
      DHPG监控系统 | 版本 4.0.1
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { User, Lock, Camera, InfoFilled } from "@element-plus/icons-vue";
import { useUserStore } from "./admin_stores";

const router = useRouter();
const userStore = useUserStore();
const formRef = ref();
const loading = ref(false);

const loginForm = reactive({
  username: "",
  password: "",
});

const rules = {
  username: [{ required: true, message: "请输入用户名", trigger: "blur" }],
  password: [
    { required: true, message: "请输入密码", trigger: "blur" },
    { min: 6, message: "密码长度至少6位", trigger: "blur" },
  ],
};

const handleLogin = async () => {
  if (!formRef.value) return;

  await formRef.value.validate(async (valid) => {
    if (valid) {
      loading.value = true;
      try {
        const success = await userStore.login(
          loginForm.username,
          loginForm.password,
        );
        if (success) {
          router.push("/dashboard");
        }
      } finally {
        loading.value = false;
      }
    }
  });
};
</script>

<style scoped>
.login-container {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  padding: 20px;
}

.login-card {
  width: 100%;
  max-width: 420px;
  border-radius: 16px;
  overflow: hidden;
  animation: slideUp 0.5s ease;
}

@keyframes slideUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.login-header {
  text-align: center;
  padding: 20px 0;
}

.login-header h2 {
  margin: 16px 0 8px;
  color: #333;
  font-size: 24px;
}

.login-header .subtitle {
  color: #666;
  font-size: 14px;
  margin: 0;
}

.login-footer {
  text-align: center;
  margin-top: 16px;
  color: #999;
  font-size: 13px;
}

.demo-info {
  color: #909399;
  font-size: 12px;
}

.version {
  margin-top: 20px;
  color: rgba(255, 255, 255, 0.7);
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: 4px;
}

:deep(.el-card__header) {
  border-bottom: none;
  padding-bottom: 0;
}

:deep(.el-form-item:last-child) {
  margin-bottom: 0;
}
</style>
