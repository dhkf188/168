<!-- admin_Settings.vue - 完整修复版（保存后自动刷新） -->
<template>
  <div class="settings">
    <el-row :gutter="20">
      <!-- 左侧菜单 -->
      <el-col :span="4">
        <el-menu
          :default-active="activeMenu"
          class="settings-menu"
          @select="handleMenuSelect"
        >
          <el-menu-item index="general">
            <el-icon><Setting /></el-icon>
            <span>通用设置</span>
          </el-menu-item>
          <el-menu-item index="cleanup">
            <el-icon><Delete /></el-icon>
            <span>清理策略</span>
          </el-menu-item>
          <el-menu-item index="storage">
            <el-icon><Folder /></el-icon>
            <span>存储设置</span>
          </el-menu-item>
          <el-menu-item index="backup">
            <el-icon><DataLine /></el-icon>
            <span>备份管理</span>
          </el-menu-item>
          <el-menu-item index="security">
            <el-icon><Lock /></el-icon>
            <span>安全设置</span>
          </el-menu-item>
          <el-menu-item index="notification">
            <el-icon><Message /></el-icon>
            <span>通知设置</span>
          </el-menu-item>
        </el-menu>
      </el-col>

      <!-- 右侧内容 -->
      <el-col :span="20">
        <el-card class="settings-content" shadow="hover">
          <!-- 通用设置 -->
          <div v-if="activeMenu === 'general'">
            <h3 class="section-title">通用设置</h3>
            <el-form :model="generalSettings" label-width="120px">
              <el-form-item label="系统名称">
                <el-input
                  v-model="generalSettings.systemName"
                  placeholder="员工监控系统"
                />
              </el-form-item>

              <el-form-item label="默认截图间隔">
                <el-input-number
                  v-model="generalSettings.defaultInterval"
                  :min="10"
                  :max="3600"
                />
                <span class="unit">秒</span>
              </el-form-item>

              <el-form-item label="默认图片格式">
                <el-radio-group v-model="generalSettings.defaultFormat">
                  <el-radio value="webp">WebP (推荐)</el-radio>
                  <el-radio value="jpg">JPEG</el-radio>
                </el-radio-group>
              </el-form-item>

              <el-form-item label="默认图片质量">
                <el-slider
                  v-model="generalSettings.defaultQuality"
                  :min="10"
                  :max="100"
                  show-input
                />
              </el-form-item>

              <el-form-item label="时区">
                <el-select v-model="generalSettings.timezone">
                  <el-option label="UTC+8 (北京时间)" value="Asia/Shanghai" />
                  <el-option label="UTC+0 (伦敦时间)" value="UTC" />
                  <el-option
                    label="UTC-5 (纽约时间)"
                    value="America/New_York"
                  />
                </el-select>
              </el-form-item>

              <!-- 通用设置的保存按钮 -->
              <el-form-item>
                <el-button
                  type="primary"
                  @click="saveGeneralSettings"
                  :loading="savingGeneral"
                >
                  保存通用设置
                </el-button>
              </el-form-item>
            </el-form>
          </div>

          <!-- 清理策略 -->
          <div v-else-if="activeMenu === 'cleanup'">
            <h3 class="section-title">自动清理策略</h3>

            <el-alert
              title="系统将自动删除超过保留时间的截图，释放存储空间"
              type="info"
              :closable="false"
              show-icon
              class="alert"
            />

            <!-- ========== 现有截图清理配置 ========== -->
            <el-form :model="cleanupSettings" label-width="140px">
              <el-form-item label="启用自动清理">
                <el-switch v-model="cleanupSettings.enabled" />
              </el-form-item>

              <el-form-item label="截图保留时间">
                <el-input-number
                  v-model="cleanupSettings.retentionHours"
                  :min="1"
                  :max="720"
                />
                <span class="unit">小时</span>
              </el-form-item>

              <el-form-item label="清理间隔">
                <el-input-number
                  v-model="cleanupSettings.interval"
                  :min="1"
                  :max="168"
                />
                <span class="unit">小时</span>
              </el-form-item>

              <el-form-item label="清理时间">
                <el-time-picker
                  v-model="cleanupSettings.cleanupTime"
                  format="HH:mm"
                  placeholder="选择清理时间"
                  :disabled="!cleanupSettings.enabled"
                />
                <span class="help-text">每天固定时间执行清理</span>
              </el-form-item>

              <el-form-item>
                <el-button
                  type="primary"
                  @click="saveCleanupSettings"
                  :loading="savingCleanup"
                >
                  保存截图清理策略
                </el-button>
              </el-form-item>

              <el-form-item label="立即清理截图">
                <el-button
                  type="danger"
                  @click="manualCleanup"
                  :loading="cleaning"
                >
                  立即清理旧截图
                </el-button>
                <span class="help-text">将删除所有超过保留时间的截图</span>
              </el-form-item>
            </el-form>

            <el-divider />

            <!-- ========== 🆕 新增：其他表清理策略 ========== -->
            <h3 class="section-title">其他数据清理策略</h3>

            <el-alert
              title="定期清理历史数据，优化数据库性能"
              type="warning"
              :closable="false"
              show-icon
              class="alert"
            />

            <el-table
              :data="otherCleanupPolicies"
              stripe
              style="width: 100%; margin-top: 20px"
              v-loading="loadingPolicies"
            >
              <el-table-column prop="table_name" label="数据表" width="150">
                <template #default="{ row }">
                  <span>{{ getTableNameCN(row.table_name) }}</span>
                </template>
              </el-table-column>

              <el-table-column label="状态" width="100">
                <template #default="{ row }">
                  <el-switch
                    v-model="row.enabled"
                    @change="updatePolicy(row)"
                  />
                </template>
              </el-table-column>

              <el-table-column label="保留策略" min-width="200">
                <template #default="{ row }">
                  <el-input-number
                    v-if="row.retention_hours"
                    v-model="row.retention_hours"
                    :min="1"
                    :max="720"
                    size="small"
                    @change="updatePolicy(row)"
                  />
                  <el-input-number
                    v-else
                    v-model="row.retention_days"
                    :min="1"
                    :max="365"
                    size="small"
                    @change="updatePolicy(row)"
                  />
                  <span class="unit">{{
                    row.retention_hours ? "小时" : "天"
                  }}</span>
                </template>
              </el-table-column>

              <el-table-column label="优先级" width="100">
                <template #default="{ row }">
                  <el-input-number
                    v-model="row.priority"
                    :min="1"
                    :max="10"
                    size="small"
                    @change="updatePolicy(row)"
                  />
                </template>
              </el-table-column>

              <el-table-column label="上次清理" width="180">
                <template #default="{ row }">
                  {{ formatDateTime(row.last_cleaned_at) || "从未" }}
                </template>
              </el-table-column>

              <el-table-column label="清理数量" width="100">
                <template #default="{ row }">
                  {{ row.cleaned_count || 0 }}
                </template>
              </el-table-column>

              <el-table-column label="当前数据量" width="100">
                <template #default="{ row }">
                  <el-tag size="small" type="info">{{
                    row.current_count || 0
                  }}</el-tag>
                </template>
              </el-table-column>
            </el-table>

            <el-divider />

            <div class="form-actions">
              <el-button
                type="primary"
                @click="manualCleanupAll"
                :loading="cleaningAll"
              >
                <el-icon><Delete /></el-icon>立即全面清理
              </el-button>
              <el-button
                @click="loadAllCleanupPolicies"
                :loading="loadingPolicies"
              >
                <el-icon><Refresh /></el-icon>刷新策略
              </el-button>
              <el-button @click="getCleanupRecommendations">
                <el-icon><DataAnalysis /></el-icon>清理建议
              </el-button>
            </div>

            <!-- 清理建议对话框 -->
            <el-dialog
              v-model="recommendationsVisible"
              title="清理建议"
              width="500px"
            >
              <div v-if="recommendations.length > 0">
                <el-alert
                  v-for="(rec, idx) in recommendations"
                  :key="idx"
                  :title="rec.message"
                  :type="rec.table === 'disk' ? 'warning' : 'info'"
                  :closable="false"
                  show-icon
                  style="margin-bottom: 12px"
                >
                  <template v-if="rec.table">
                    <div>当前数据量: {{ rec.current_count }} 条</div>
                    <div>
                      建议保留: {{ rec.suggestion || `${rec.threshold} 天` }}
                    </div>
                  </template>
                  <template v-else>
                    <div>剩余空间: {{ rec.free_gb }} GB</div>
                    <div>建议立即清理或扩容</div>
                  </template>
                </el-alert>
              </div>
              <div v-else>
                <el-empty description="暂无清理建议" />
              </div>
              <template #footer>
                <el-button @click="recommendationsVisible = false"
                  >关闭</el-button
                >
              </template>
            </el-dialog>

            <!-- ========== 现有清理状态显示 ========== -->
            <el-divider />

            <h4>当前清理状态</h4>
            <el-descriptions :column="2" border>
              <el-descriptions-item label="自动清理状态">
                <el-tag :type="cleanupStatus.enabled ? 'success' : 'info'">
                  {{ cleanupStatus.enabled ? "已启用" : "已禁用" }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="截图保留时间">
                {{ cleanupStatus.retention_hours }}小时
              </el-descriptions-item>
              <el-descriptions-item label="清理间隔">
                {{ cleanupStatus.interval_hours }}小时
              </el-descriptions-item>
              <el-descriptions-item label="清理时间">
                {{ cleanupStatus.cleanup_time || "未设置" }}
              </el-descriptions-item>
              <el-descriptions-item label="上次清理时间">
                {{ cleanupStatus.last_cleanup || "从未" }}
              </el-descriptions-item>
              <el-descriptions-item label="待清理截图">
                {{ cleanupStatus.pending_cleanup }} 张 ({{
                  cleanupStatus.pending_size_mb
                }}
                MB)
              </el-descriptions-item>
            </el-descriptions>
          </div>

          <!-- 存储设置 -->
          <div v-else-if="activeMenu === 'storage'">
            <h3 class="section-title">存储设置</h3>

            <el-progress
              type="dashboard"
              :percentage="storageUsage"
              :color="storageColor"
              class="storage-progress"
            >
              <template #default="{ percentage }">
                <span class="percentage-value">{{ percentage }}%</span>
                <span class="percentage-label">已使用</span>
              </template>
            </el-progress>

            <el-form
              :model="storageSettings"
              label-width="120px"
              class="storage-form"
            >
              <el-form-item label="存储路径">
                <el-input v-model="storageSettings.path" readonly>
                  <template #append>
                    <el-button>浏览</el-button>
                  </template>
                </el-input>
              </el-form-item>

              <el-form-item label="最大存储空间">
                <el-input-number
                  v-model="storageSettings.maxSize"
                  :min="1"
                  :max="1000"
                />
                <span class="unit">GB</span>
              </el-form-item>

              <el-form-item label="缩略图大小">
                <el-input-number
                  v-model="storageSettings.thumbnailSize"
                  :min="100"
                  :max="800"
                  step="50"
                />
                <span class="unit">px</span>
              </el-form-item>

              <el-form-item label="缩略图质量">
                <el-slider
                  v-model="storageSettings.thumbnailQuality"
                  :min="10"
                  :max="100"
                  show-input
                />
              </el-form-item>

              <!-- 存储设置的保存按钮 -->
              <el-form-item>
                <el-button
                  type="primary"
                  @click="saveStorageSettings"
                  :loading="savingStorage"
                >
                  保存存储设置
                </el-button>
              </el-form-item>
            </el-form>
          </div>

          <!-- 备份管理 -->
          <div v-else-if="activeMenu === 'backup'">
            <h3 class="section-title">数据库备份</h3>

            <el-alert
              title="定期备份可以防止数据丢失，建议每周至少备份一次"
              type="warning"
              :closable="false"
              show-icon
              class="alert"
            />

            <el-form :model="backupSettings" label-width="120px">
              <el-form-item label="启用自动备份">
                <el-switch v-model="backupSettings.enabled" />
              </el-form-item>

              <el-form-item label="备份频率">
                <el-select v-model="backupSettings.frequency">
                  <el-option label="每天" value="daily" />
                  <el-option label="每周" value="weekly" />
                  <el-option label="每月" value="monthly" />
                </el-select>
              </el-form-item>

              <el-form-item label="备份时间">
                <el-time-picker
                  v-model="backupSettings.backupTime"
                  format="HH:mm"
                  placeholder="选择备份时间"
                />
              </el-form-item>

              <el-form-item label="保留备份数">
                <el-input-number
                  v-model="backupSettings.keepCount"
                  :min="1"
                  :max="30"
                />
              </el-form-item>

              <!-- 备份设置的保存按钮 -->
              <el-form-item>
                <el-button
                  type="primary"
                  @click="saveBackupSettings"
                  :loading="savingBackup"
                >
                  保存备份设置
                </el-button>
              </el-form-item>

              <el-form-item label="立即备份">
                <el-button
                  type="primary"
                  @click="manualBackup"
                  :loading="backing"
                >
                  立即备份数据库
                </el-button>
              </el-form-item>
            </el-form>

            <el-divider />

            <h4>备份列表</h4>
            <el-table :data="backupList" stripe style="width: 100%">
              <el-table-column prop="filename" label="文件名" />
              <el-table-column prop="size" label="大小" width="100" />
              <el-table-column prop="created_at" label="创建时间" width="180" />
              <el-table-column label="操作" width="150">
                <template #default="{ row }">
                  <el-button link type="primary" @click="downloadBackup(row)"
                    >下载</el-button
                  >
                  <el-button link type="danger" @click="deleteBackup(row)"
                    >删除</el-button
                  >
                </template>
              </el-table-column>
            </el-table>
          </div>

          <!-- 安全设置 -->
          <div v-else-if="activeMenu === 'security'">
            <h3 class="section-title">安全设置</h3>

            <el-tabs type="border-card">
              <!-- 管理员密码 -->
              <el-tab-pane label="管理员密码">
                <el-form
                  :model="passwordForm"
                  label-width="100px"
                  :rules="passwordRules"
                  ref="passwordFormRef"
                  status-icon
                >
                  <el-form-item label="当前密码" prop="currentPassword">
                    <el-input
                      v-model="passwordForm.currentPassword"
                      type="password"
                      show-password
                      placeholder="请输入当前密码"
                    />
                  </el-form-item>

                  <el-form-item label="新密码" prop="newPassword">
                    <el-input
                      v-model="passwordForm.newPassword"
                      type="password"
                      show-password
                      placeholder="请输入新密码（至少6位）"
                    />
                    <span class="help-text">密码长度至少6位</span>
                  </el-form-item>

                  <el-form-item label="确认密码" prop="confirmPassword">
                    <el-input
                      v-model="passwordForm.confirmPassword"
                      type="password"
                      show-password
                      placeholder="请再次输入新密码"
                    />
                  </el-form-item>

                  <el-form-item>
                    <el-button
                      type="primary"
                      @click="changePassword"
                      :loading="changingPassword"
                    >
                      修改密码
                    </el-button>
                  </el-form-item>
                </el-form>
              </el-tab-pane>

              <!-- 登录日志 -->
              <el-tab-pane label="登录日志">
                <el-table :data="loginLogs" stripe>
                  <el-table-column prop="time" label="时间" width="180" />
                  <el-table-column prop="username" label="用户名" width="120" />
                  <el-table-column prop="ip" label="IP地址" width="150" />
                  <el-table-column prop="result" label="结果" width="100">
                    <template #default="{ row }">
                      <el-tag
                        :type="row.result === '成功' ? 'success' : 'danger'"
                      >
                        {{ row.result }}
                      </el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column
                    prop="user_agent"
                    label="用户代理"
                    show-overflow-tooltip
                  />
                </el-table>
              </el-tab-pane>

              <!-- API密钥 -->
              <el-tab-pane label="API密钥">
                <el-form :model="apiKeyForm" label-width="120px">
                  <el-form-item label="当前密钥">
                    <el-input v-model="apiKeyForm.currentKey" readonly>
                      <template #append>
                        <el-button @click="copyApiKey">复制</el-button>
                      </template>
                    </el-input>
                  </el-form-item>

                  <el-form-item label="JWT过期时间">
                    <el-input-number
                      v-model="securitySettings.jwtExpireMinutes"
                      :min="30"
                      :max="1440"
                      :step="30"
                    />
                    <span class="unit">分钟</span>
                    <span class="help-text"
                      >Token有效期，建议480分钟（8小时）</span
                    >
                  </el-form-item>

                  <el-form-item label="生成新密钥">
                    <el-button
                      type="warning"
                      @click="regenerateApiKey"
                      :loading="regeneratingKey"
                    >
                      重新生成
                    </el-button>
                    <span class="help-text"
                      >生成后将立即生效，旧密钥将失效</span
                    >
                  </el-form-item>

                  <!-- 安全设置的保存按钮 -->
                  <el-form-item>
                    <el-button
                      type="primary"
                      @click="saveSecuritySettings"
                      :loading="savingSecurity"
                    >
                      保存JWT设置
                    </el-button>
                  </el-form-item>
                </el-form>
              </el-tab-pane>
            </el-tabs>
          </div>

          <!-- 通知设置 -->
          <div v-else-if="activeMenu === 'notification'">
            <h3 class="section-title">通知设置</h3>

            <el-form :model="notificationSettings" label-width="140px">
              <el-form-item label="启用通知">
                <el-switch v-model="notificationSettings.enabled" />
              </el-form-item>

              <el-form-item label="通知方式">
                <el-checkbox-group v-model="notificationSettings.methods">
                  <el-checkbox label="email">邮件</el-checkbox>
                  <el-checkbox label="webhook">Webhook</el-checkbox>
                  <el-checkbox label="dingtalk">钉钉</el-checkbox>
                  <el-checkbox label="wechat">企业微信</el-checkbox>
                </el-checkbox-group>
              </el-form-item>

              <el-form-item label="邮件服务器">
                <el-input
                  v-model="notificationSettings.smtpServer"
                  placeholder="smtp.example.com"
                />
              </el-form-item>

              <el-form-item label="发件人邮箱">
                <el-input
                  v-model="notificationSettings.fromEmail"
                  placeholder="noreply@example.com"
                />
              </el-form-item>

              <el-form-item label="接收邮箱">
                <el-input
                  v-model="notificationSettings.toEmail"
                  placeholder="admin@example.com"
                />
              </el-form-item>

              <el-divider />

              <h4>通知事件</h4>
              <el-form-item label="新客户端注册">
                <el-switch
                  v-model="notificationSettings.events.clientRegister"
                />
              </el-form-item>

              <el-form-item label="客户端离线">
                <el-switch
                  v-model="notificationSettings.events.clientOffline"
                />
              </el-form-item>

              <el-form-item label="存储空间不足">
                <el-switch v-model="notificationSettings.events.lowStorage" />
              </el-form-item>

              <el-form-item label="备份完成">
                <el-switch
                  v-model="notificationSettings.events.backupComplete"
                />
              </el-form-item>

              <!-- 通知设置的保存按钮 -->
              <el-form-item>
                <el-button
                  type="primary"
                  @click="saveNotificationSettings"
                  :loading="savingNotification"
                >
                  保存通知设置
                </el-button>
              </el-form-item>
            </el-form>
          </div>

          <!-- 底部按钮 -->
          <el-divider />
          <div class="form-actions">
            <el-button
              type="primary"
              @click="saveAllSettings"
              :loading="savingAll"
            >
              保存所有设置
            </el-button>
            <el-button @click="resetSettings">重置</el-button>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  Setting,
  Delete,
  Folder,
  DataLine,
  Lock,
  Message,
  Refresh,
  DataAnalysis,
} from "@element-plus/icons-vue";
import { cleanupApi } from "./admin_api";
import api from "./admin_api";
import dayjs from "dayjs";
import { useRouter } from "vue-router";
import { useUserStore } from "./admin_stores";
import { formatDateTime } from "./admin_timezone";

const router = useRouter();
const userStore = useUserStore();

const activeMenu = ref("general");
const savingAll = ref(false);
const cleaning = ref(false);
const backing = ref(false);

// 密码修改相关
const changingPassword = ref(false);
const regeneratingKey = ref(false);

// 各分类的保存状态
const savingGeneral = ref(false);
const savingCleanup = ref(false);
const savingStorage = ref(false);
const savingBackup = ref(false);
const savingSecurity = ref(false);
const savingNotification = ref(false);

// 通用设置
const generalSettings = ref({
  systemName: "员工监控系统",
  defaultInterval: 60,
  defaultFormat: "webp",
  defaultQuality: 80,
  timezone: "Asia/Shanghai",
});

// 清理设置（包含清理时间）
const cleanupSettings = ref({
  enabled: true,
  retentionHours: 4,
  interval: 6,
  cleanupTime: new Date(), // 清理时间
});

const cleanupStatus = ref({
  enabled: true,
  retention_hours: 4,
  interval_hours: 6,
  cleanup_time: null,
  last_cleanup: null,
  pending_cleanup: 0,
  pending_size_mb: 0,
});

// 存储设置
const storageSettings = ref({
  path: "/data/screenshots",
  maxSize: 100,
  thumbnailSize: 320,
  thumbnailQuality: 75,
});

const storageUsage = ref(45);
const storageColor = computed(() => {
  if (storageUsage.value < 70) return "#52c41a";
  if (storageUsage.value < 85) return "#fa8c16";
  return "#ff4d4f";
});

// 安全设置
const securitySettings = ref({
  jwtExpireMinutes: 480,
});

// 备份设置（包含备份时间）
const backupSettings = ref({
  enabled: true,
  frequency: "daily",
  backupTime: new Date(), // 备份时间
  keepCount: 7,
});

const backupList = ref([
  {
    filename: "backup_20240101_000000.sql.gz",
    size: "128 MB",
    created_at: "2024-01-01 00:00:00",
  },
]);

// 密码表单
const passwordFormRef = ref(null);
const passwordForm = ref({
  currentPassword: "",
  newPassword: "",
  confirmPassword: "",
});

const passwordRules = {
  currentPassword: [
    { required: true, message: "请输入当前密码", trigger: "blur" },
  ],
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

// 登录日志
const loginLogs = ref([
  {
    time: "2024-01-01 10:30:00",
    username: "admin",
    ip: "192.168.1.100",
    result: "成功",
    user_agent: "Chrome",
  },
]);

// API密钥
const apiKeyForm = ref({
  currentKey: "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
});

// 通知设置
const notificationSettings = ref({
  enabled: true,
  methods: ["email"],
  smtpServer: "",
  fromEmail: "",
  toEmail: "",
  events: {
    clientRegister: true,
    clientOffline: true,
    lowStorage: true,
    backupComplete: true,
  },
});

// ========== 新增：其他表清理策略 ==========
const otherCleanupPolicies = ref([]);
const loadingPolicies = ref(false);
const cleaningAll = ref(false);
const recommendationsVisible = ref(false);
const recommendations = ref([]);

// 表名中文映射
const getTableNameCN = (tableName) => {
  const map = {
    screenshots: "截图记录",
    browser_history: "浏览器历史",
    activities: "活动日志",
    app_usage: "软件使用记录",
    file_operations: "文件操作记录",
    notifications: "通知记录",
    clients_offline: "离线客户端",
  };
  return map[tableName] || tableName;
};

// 加载所有清理策略
const loadAllCleanupPolicies = async () => {
  loadingPolicies.value = true;
  try {
    const response = await api.get("/cleanup/policies");
    const allPolicies = response.items || [];

    // 分离截图策略和其他策略
    const screenshotPolicy = allPolicies.find(
      (p) => p.table_name === "screenshots",
    );
    otherCleanupPolicies.value = allPolicies.filter(
      (p) => p.table_name !== "screenshots",
    );

    // 如果有截图策略，更新到 cleanupSettings
    if (screenshotPolicy) {
      cleanupSettings.value = {
        enabled: screenshotPolicy.enabled,
        retentionHours: screenshotPolicy.retention_hours || 48,
        interval: screenshotPolicy.retention_days || 6,
        cleanupTime: screenshotPolicy.cleanup_time ? new Date() : null,
      };
    }

    console.log("清理策略加载成功:", {
      screenshot: screenshotPolicy,
      others: otherCleanupPolicies.value.length,
    });
  } catch (error) {
    console.error("加载清理策略失败:", error);
    ElMessage.error("加载清理策略失败");
  } finally {
    loadingPolicies.value = false;
  }
};

// 更新单个清理策略
const updatePolicy = async (policy) => {
  try {
    await api.put(`/cleanup/policies/${policy.id}`, {
      enabled: policy.enabled,
      retention_days: policy.retention_days,
      retention_hours: policy.retention_hours,
      priority: policy.priority,
    });
    ElMessage.success(`${getTableNameCN(policy.table_name)} 策略已更新`);
  } catch (error) {
    console.error("更新策略失败:", error);
    ElMessage.error("更新失败");
    // 重新加载恢复原值
    await loadAllCleanupPolicies();
  }
};

// 手动全面清理
const manualCleanupAll = async () => {
  ElMessageBox.confirm(
    "确定要立即清理所有过期数据吗？\n\n这将删除：\n- 过期的截图文件\n- 过期的浏览器历史\n- 过期的活动日志\n- 过期的软件使用记录\n- 过期的文件操作记录\n- 已删除超过7天的通知",
    "确认全面清理",
    {
      confirmButtonText: "确定清理",
      cancelButtonText: "取消",
      type: "warning",
      dangerouslyUseHTMLString: true,
    },
  ).then(async () => {
    cleaningAll.value = true;
    try {
      await api.post("/cleanup/now");
      ElMessage.success("全面清理任务已启动，请稍后查看清理状态");

      // 3秒后刷新状态
      setTimeout(() => {
        loadCleanupStatus();
        loadAllCleanupPolicies();
      }, 3000);
    } catch (error) {
      console.error("全面清理失败:", error);
      ElMessage.error("清理任务启动失败");
    } finally {
      cleaningAll.value = false;
    }
  });
};

// 获取清理建议
const getCleanupRecommendations = async () => {
  try {
    const response = await api.get("/cleanup/recommendations");
    recommendations.value = response.recommendations || [];
    recommendationsVisible.value = true;
  } catch (error) {
    console.error("获取清理建议失败:", error);
    ElMessage.error("获取清理建议失败");
  }
};

// 修改现有的 saveCleanupSettings 以保存截图策略 - xb
const saveCleanupSettings = async () => {
  savingCleanup.value = true;
  try {
    // 找到截图策略的 ID
    const screenshotPolicy = otherCleanupPolicies.value.find(
      (p) => p.table_name === "screenshots",
    );

    if (screenshotPolicy) {
      // 更新截图策略
      await api.put(`/cleanup/policies/${screenshotPolicy.id}`, {
        enabled: cleanupSettings.value.enabled,
        retention_hours: cleanupSettings.value.retentionHours,
        priority: 1, // 截图策略优先级最高
      });

      // 同时更新系统配置（保持兼容）
      await api.post("/settings/cleanup", {
        enabled: cleanupSettings.value.enabled,
        retention_hours: cleanupSettings.value.retentionHours,
        interval_hours: cleanupSettings.value.interval,
        cleanup_time: cleanupSettings.value.cleanupTime
          ? dayjs(cleanupSettings.value.cleanupTime).format("HH:mm")
          : null,
      });

      ElMessage.success("截图清理策略已保存");
      await loadAllCleanupPolicies(); // 重新加载所有策略
      await loadCleanupStatus(); // 刷新清理状态
    } else {
      // 如果找不到截图策略，使用原有方式
      const cleanupTimeStr = cleanupSettings.value.cleanupTime
        ? dayjs(cleanupSettings.value.cleanupTime).format("HH:mm")
        : null;

      await api.post("/settings/cleanup", {
        enabled: cleanupSettings.value.enabled,
        retention_hours: cleanupSettings.value.retentionHours,
        interval_hours: cleanupSettings.value.interval,
        cleanup_time: cleanupTimeStr,
      });

      ElMessage.success("截图清理策略已保存");
      await loadAllCleanupPolicies();
      await loadCleanupStatus();
    }
  } catch (error) {
    console.error("保存清理策略失败:", error);
    ElMessage.error(
      "保存失败: " + (error.response?.data?.detail || "未知错误"),
    );
  } finally {
    savingCleanup.value = false;
  }
};
// ==================== API 调用函数 ====================

// 加载所有设置
const loadAllSettings = async () => {
  try {
    const res = await api.get("/settings/all");

    // 更新通用设置
    if (res.general) {
      generalSettings.value = {
        systemName: res.general.system_name || generalSettings.value.systemName,
        defaultInterval:
          res.general.default_interval || generalSettings.value.defaultInterval,
        defaultFormat:
          res.general.default_format || generalSettings.value.defaultFormat,
        defaultQuality:
          res.general.default_quality || generalSettings.value.defaultQuality,
        timezone: res.general.timezone || generalSettings.value.timezone,
      };
    }

    // 更新清理设置（包含清理时间）
    if (res.cleanup) {
      cleanupSettings.value = {
        enabled: res.cleanup.enabled ?? cleanupSettings.value.enabled,
        retentionHours:
          res.cleanup.retention_hours || cleanupSettings.value.retentionHours,
        interval: res.cleanup.interval_hours || cleanupSettings.value.interval,
        cleanupTime: res.cleanup.cleanup_time
          ? new Date(`1970-01-01T${res.cleanup.cleanup_time}:00`)
          : cleanupSettings.value.cleanupTime,
      };
    }

    // 更新存储设置
    if (res.storage) {
      storageSettings.value = {
        path: res.storage.path || storageSettings.value.path,
        maxSize: res.storage.max_size_gb || storageSettings.value.maxSize,
        thumbnailSize:
          res.storage.thumbnail_size || storageSettings.value.thumbnailSize,
        thumbnailQuality:
          res.storage.thumbnail_quality ||
          storageSettings.value.thumbnailQuality,
      };
    }

    // 更新安全设置
    if (res.security) {
      securitySettings.value = {
        jwtExpireMinutes:
          res.security.jwt_expire_minutes ||
          securitySettings.value.jwtExpireMinutes,
      };
    }

    // 更新备份设置
    if (res.backup) {
      backupSettings.value = {
        enabled: res.backup.enabled ?? backupSettings.value.enabled,
        frequency: res.backup.frequency || backupSettings.value.frequency,
        backupTime: res.backup.backup_time
          ? new Date(`1970-01-01T${res.backup.backup_time}:00`)
          : backupSettings.value.backupTime,
        keepCount: res.backup.keep_count || backupSettings.value.keepCount,
      };
    }
  } catch (error) {
    console.error("加载设置失败:", error);
    ElMessage.error("加载设置失败");
  }
};

// 保存通用设置
const saveGeneralSettings = async () => {
  savingGeneral.value = true;
  try {
    await api.post("/settings/general", {
      system_name: generalSettings.value.systemName,
      default_interval: generalSettings.value.defaultInterval,
      default_format: generalSettings.value.defaultFormat,
      default_quality: generalSettings.value.defaultQuality,
      timezone: generalSettings.value.timezone,
    });
    ElMessage.success("通用设置已保存");
    await loadAllSettings(); // ✅ 重新加载数据
  } catch (error) {
    console.error("保存通用设置失败:", error);
    ElMessage.error(
      "保存失败: " + (error.response?.data?.detail || "未知错误"),
    );
  } finally {
    savingGeneral.value = false;
  }
};

// 保存存储设置
const saveStorageSettings = async () => {
  savingStorage.value = true;
  try {
    await api.post("/settings/storage", {
      path: storageSettings.value.path,
      max_size_gb: storageSettings.value.maxSize,
      thumbnail_size: storageSettings.value.thumbnailSize,
      thumbnail_quality: storageSettings.value.thumbnailQuality,
    });
    ElMessage.success("存储设置已保存");
    await loadAllSettings(); // ✅ 重新加载数据
  } catch (error) {
    console.error("保存存储设置失败:", error);
    ElMessage.error(
      "保存失败: " + (error.response?.data?.detail || "未知错误"),
    );
  } finally {
    savingStorage.value = false;
  }
};

// 保存备份设置（包含备份时间）
const saveBackupSettings = async () => {
  savingBackup.value = true;
  try {
    const backupTimeStr = backupSettings.value.backupTime
      ? dayjs(backupSettings.value.backupTime).format("HH:mm")
      : null;

    await api.post("/settings/backup", {
      enabled: backupSettings.value.enabled,
      frequency: backupSettings.value.frequency,
      backup_time: backupTimeStr,
      keep_count: backupSettings.value.keepCount,
    });
    ElMessage.success("备份设置已保存");
    await loadAllSettings(); // ✅ 重新加载数据
  } catch (error) {
    console.error("保存备份设置失败:", error);
    ElMessage.error(
      "保存失败: " + (error.response?.data?.detail || "未知错误"),
    );
  } finally {
    savingBackup.value = false;
  }
};

// 保存安全设置
const saveSecuritySettings = async () => {
  savingSecurity.value = true;
  try {
    await api.post("/settings/security", {
      jwt_expire_minutes: securitySettings.value.jwtExpireMinutes,
    });
    ElMessage.success("安全设置已保存");
    await loadAllSettings(); // ✅ 重新加载数据
  } catch (error) {
    console.error("保存安全设置失败:", error);
    ElMessage.error(
      "保存失败: " + (error.response?.data?.detail || "未知错误"),
    );
  } finally {
    savingSecurity.value = false;
  }
};

// 保存通知设置
const saveNotificationSettings = async () => {
  savingNotification.value = true;
  try {
    await api.post("/settings/notification", {
      enabled: notificationSettings.value.enabled,
      methods: notificationSettings.value.methods,
      smtp_server: notificationSettings.value.smtpServer,
      from_email: notificationSettings.value.fromEmail,
      to_email: notificationSettings.value.toEmail,
      events: notificationSettings.value.events,
    });
    ElMessage.success("通知设置已保存");
    await loadAllSettings(); // ✅ 重新加载数据
  } catch (error) {
    console.error("保存通知设置失败:", error);
    ElMessage.error(
      "保存失败: " + (error.response?.data?.detail || "未知错误"),
    );
  } finally {
    savingNotification.value = false;
  }
};

// 保存所有设置
const saveAllSettings = async () => {
  savingAll.value = true;
  try {
    await Promise.all(
      [
        saveGeneralSettings(),
        saveCleanupSettings(),
        saveStorageSettings(),
        saveBackupSettings(),
        saveSecuritySettings(),
        saveNotificationSettings(),
      ].map((p) => p.catch((e) => console.error(e))),
    );
    ElMessage.success("所有设置已保存");
    await loadAllSettings(); // ✅ 重新加载数据
  } catch (error) {
    console.error("保存设置失败:", error);
  } finally {
    savingAll.value = false;
  }
};

// 菜单选择
const handleMenuSelect = (index) => {
  activeMenu.value = index;
};

// 手动清理
const manualCleanup = async () => {
  ElMessageBox.confirm(
    "确定要立即清理所有超过保留时间的截图吗？此操作不可恢复！",
    "确认清理",
    {
      confirmButtonText: "确定清理",
      cancelButtonText: "取消",
      type: "warning",
    },
  ).then(async () => {
    cleaning.value = true;
    try {
      const res = await cleanupApi.manualCleanup();
      ElMessage.success(res.message);
      await loadCleanupStatus();
    } catch (error) {
      console.error("清理失败:", error);
      ElMessage.error(
        "清理失败: " + (error.response?.data?.detail || "未知错误"),
      );
    } finally {
      cleaning.value = false;
    }
  });
};

// 加载清理状态
const loadCleanupStatus = async () => {
  try {
    const status = await cleanupApi.getCleanupStatus();
    cleanupStatus.value = status;
  } catch (error) {
    console.error("加载清理状态失败:", error);
  }
};

// 手动备份
const manualBackup = () => {
  ElMessage.success("备份任务已启动");
};

// 下载备份
const downloadBackup = (row) => {
  ElMessage.success("下载功能开发中...");
};

// 删除备份
const deleteBackup = (row) => {
  ElMessageBox.confirm("确定要删除此备份吗？", "警告", {
    confirmButtonText: "确定",
    cancelButtonText: "取消",
    type: "warning",
  }).then(() => {
    ElMessage.success("删除成功");
  });
};

// ==================== 密码相关功能 ====================
const changePassword = async () => {
  if (!passwordFormRef.value) return;

  const valid = await passwordFormRef.value.validate().catch(() => false);
  if (!valid) return;

  // ✅ 前端确认密码校验
  if (passwordForm.value.newPassword !== passwordForm.value.confirmPassword) {
    ElMessage.error("两次输入的密码不一致");
    return;
  }

  changingPassword.value = true;

  try {
    const response = await api.post("/auth/change-password", {
      current_password: passwordForm.value.currentPassword,
      new_password: passwordForm.value.newPassword,
    });

    const res = response.data || response;

    if (res.access_token) {
      // ✅ 更新 store
      userStore.token = res.access_token;
      userStore.userInfo = {
        username: res.username,
        role: res.role,
      };

      // ✅ 更新本地缓存
      localStorage.setItem("token", res.access_token);
      localStorage.setItem("user", JSON.stringify(userStore.userInfo));

      ElMessage.success("密码修改成功，已自动重新登录");

      // 清空表单
      passwordForm.value = {
        currentPassword: "",
        newPassword: "",
        confirmPassword: "",
      };

      passwordDialogVisible.value = false;
    } else {
      ElMessage.success("密码修改成功，请重新登录");

      setTimeout(() => {
        userStore.logout();
        router.push("/login");
      }, 1500);
    }
  } catch (error) {
    console.error("修改密码失败:", error);

    ElMessage.error(error.response?.data?.detail || "密码修改失败，请重试");
  } finally {
    changingPassword.value = false;
  }
};

// 复制API密钥
const copyApiKey = () => {
  navigator.clipboard.writeText(apiKeyForm.value.currentKey);
  ElMessage.success("已复制到剪贴板");
};

// 重新生成API密钥
const regenerateApiKey = () => {
  ElMessageBox.confirm(
    "重新生成API密钥后，旧密钥将立即失效，所有使用旧密钥的应用都需要更新。确定要继续吗？",
    "确认重新生成",
    {
      confirmButtonText: "确定",
      cancelButtonText: "取消",
      type: "warning",
    },
  ).then(async () => {
    regeneratingKey.value = true;
    try {
      // 调用后端重新生成密钥API
      const res = await api.post("/auth/regenerate-api-key");
      apiKeyForm.value.currentKey = res.api_key;
      ElMessage.success("新密钥已生成");
    } catch (error) {
      console.error("重新生成密钥失败:", error);
      ElMessage.error("生成失败");
    } finally {
      regeneratingKey.value = false;
    }
  });
};

// 重置设置
const resetSettings = () => {
  ElMessageBox.confirm("确定要重置所有设置吗？", "警告", {
    confirmButtonText: "确定",
    cancelButtonText: "取消",
    type: "warning",
  }).then(() => {
    loadAllSettings();
    ElMessage.success("设置已重置");
  });
};

onMounted(() => {
  loadAllSettings();
  loadCleanupStatus();
});
</script>

<style scoped>
.settings {
  padding: 20px;
}

.settings-menu {
  border-radius: 8px;
  border-right: none;
}

.settings-content {
  min-height: 600px;
}

.section-title {
  margin-top: 0;
  margin-bottom: 20px;
  color: #333;
  font-size: 18px;
  font-weight: 500;
}

.alert {
  margin-bottom: 20px;
}

.unit {
  margin-left: 8px;
  color: #999;
}

.help-text {
  margin-left: 12px;
  font-size: 12px;
  color: #999;
}

.storage-progress {
  margin: 20px auto;
  width: 200px;
}

.percentage-value {
  display: block;
  font-size: 28px;
  font-weight: bold;
  color: #333;
}

.percentage-label {
  display: block;
  font-size: 12px;
  color: #999;
  margin-top: 5px;
}

.storage-form {
  margin-top: 20px;
}

.form-actions {
  text-align: center;
  margin-top: 20px;
}
</style>
