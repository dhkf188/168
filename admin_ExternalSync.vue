<template>
  <div class="data-sync-page">
    <!-- 页面标题 -->
    <div class="page-header">
      <h2>
        <el-icon><Connection /></el-icon>
        外部数据同步
      </h2>
      <p class="page-desc">
        从提现审核系统同步员工操作数据，自动统计笔数和处理时间
      </p>
    </div>

    <!-- 快速导入卡片 -->
    <el-card class="import-card" shadow="hover">
      <template #header>
        <div class="card-header">
          <span>
            <el-icon><Document /></el-icon>
            快速导入
          </span>
          <el-tag type="info" size="small">粘贴请求信息自动提取配置</el-tag>
        </div>
      </template>

      <el-input
        v-model="importText"
        type="textarea"
        :rows="5"
        placeholder="粘贴从浏览器复制的请求信息，例如：&#10;Request URL: https://api2.b-4-s-f.com/api/backend/trpc/withdrawal.ReviewedList?input=...&#10;authorization: Bearer augu29egcr0ugtk2wu3kgs331jbl23ohy8u7y8v5&#10;tenantId: 7457478"
        clearable
      />
      <div class="import-actions">
        <el-button type="primary" @click="parseImportText" :loading="parsing">
          <el-icon><MagicStick /></el-icon>
          解析并填充
        </el-button>
        <el-button @click="importText = ''">清空</el-button>
      </div>
      <div class="import-tip">
        <el-icon><InfoFilled /></el-icon>
        支持自动提取：API地址、Authorization Token、租户ID、区域ID等
      </div>
    </el-card>

    <!-- API配置卡片 -->
    <el-card class="config-card" shadow="hover">
      <template #header>
        <div class="card-header">
          <span>
            <el-icon><Setting /></el-icon>
            API配置
          </span>
          <el-tag :type="getTagType(apiStatus.type)" size="small">{{
            apiStatus.text
          }}</el-tag>
        </div>
      </template>

      <el-form :model="apiConfig" label-width="100px" label-position="left">
        <el-row :gutter="20">
          <el-col :span="24">
            <el-form-item label="API地址" required>
              <el-input
                v-model="apiConfig.baseUrl"
                placeholder="https://api2.b-4-s-f.com/api/backend/trpc/withdrawal.ReviewedList"
                clearable
              >
                <template #prepend>
                  <el-icon><Link /></el-icon>
                </template>
              </el-input>
              <div class="form-tip">完整的API接口地址，包含路径</div>
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="20">
          <el-col :span="24">
            <el-form-item label="Bearer Token" required>
              <el-input
                v-model="apiConfig.token"
                type="password"
                placeholder="请输入 Bearer Token"
                show-password
                clearable
              >
                <template #prepend>
                  <el-icon><Key /></el-icon>
                </template>
              </el-input>
              <div class="form-tip">从提现审核系统获取的认证Token</div>
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="租户ID">
              <el-input-number
                v-model="apiConfig.tenantId"
                :min="1"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="区域ID">
              <el-input-number
                v-model="apiConfig.regionId"
                :min="1"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="每页数量">
              <el-input-number
                v-model="apiConfig.pageSize"
                :min="100"
                :max="5000"
                :step="100"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="超时时间(秒)">
              <el-input-number
                v-model="apiConfig.timeout"
                :min="10"
                :max="120"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
        </el-row>

        <el-row>
          <el-col :span="24" class="text-right">
            <el-button
              type="primary"
              @click="testConnection"
              :loading="testing"
              :disabled="!apiConfig.baseUrl || !apiConfig.token"
            >
              <el-icon><Connection /></el-icon>
              {{ testing ? "测试中..." : "测试连接" }}
            </el-button>
            <el-button @click="saveApiConfig">
              <el-icon><Check /></el-icon>
              保存配置
            </el-button>
            <el-button @click="resetApiConfig">
              <el-icon><Refresh /></el-icon>
              重置
            </el-button>
          </el-col>
        </el-row>
      </el-form>

      <!-- 连接状态显示 -->
      <div v-if="apiStatus.message" class="api-status">
        <el-alert
          :type="
            apiStatus.type === 'success'
              ? 'success'
              : apiStatus.type === 'error'
                ? 'error'
                : 'info'
          "
          :title="apiStatus.message"
          :closable="false"
          show-icon
        />
      </div>
    </el-card>

    <!-- 同步参数卡片 - 支持手动时间选择 -->
    <el-card class="sync-card" shadow="hover">
      <template #header>
        <div class="card-header">
          <span>
            <el-icon><DataLine /></el-icon>
            同步参数
          </span>
          <el-radio-group v-model="timeMode" size="small">
            <el-radio-button value="auto">自动(班次)</el-radio-button>
            <el-radio-button value="manual">手动时间</el-radio-button>
          </el-radio-group>
        </div>
      </template>

      <el-form :model="syncForm" label-width="100px" label-position="left">
        <el-row :gutter="20">
          <el-col :span="8">
            <el-form-item label="目标站点" required>
              <el-select
                v-model="syncForm.siteId"
                placeholder="请选择站点"
                filterable
                style="width: 100%"
              >
                <el-option
                  v-for="site in sites"
                  :key="site.id"
                  :label="`${site.code} - ${site.name}`"
                  :value="site.id"
                />
              </el-select>
            </el-form-item>
          </el-col>

          <!-- 自动模式：班次选择 -->
          <el-col :span="8" v-if="timeMode === 'auto'">
            <el-form-item label="班次">
              <el-radio-group v-model="syncForm.shift">
                <el-radio-button value="day">
                  <el-icon><Sunny /></el-icon>
                  白班 (08:00-20:00)
                </el-radio-button>
                <el-radio-button value="night">
                  <el-icon><Moon /></el-icon>
                  夜班 (20:00-次日08:00)
                </el-radio-button>
              </el-radio-group>
            </el-form-item>
          </el-col>

          <!-- 自动模式：日期选择 -->
          <el-col :span="8" v-if="timeMode === 'auto'">
            <el-form-item label="统计日期">
              <el-date-picker
                v-model="syncForm.date"
                type="date"
                placeholder="选择日期"
                format="YYYY年MM月DD日"
                value-format="YYYY-MM-DD"
                :disabled-date="disabledFutureDate"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>

          <!-- 手动模式：开始时间 -->
          <el-col :span="12" v-if="timeMode === 'manual'">
            <el-form-item label="开始时间" required>
              <el-date-picker
                v-model="syncForm.startTime"
                type="datetime"
                placeholder="选择开始时间"
                format="YYYY-MM-DD HH:mm:ss"
                value-format="YYYY-MM-DD HH:mm:ss"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>

          <!-- 手动模式：结束时间 -->
          <el-col :span="12" v-if="timeMode === 'manual'">
            <el-form-item label="结束时间" required>
              <el-date-picker
                v-model="syncForm.endTime"
                type="datetime"
                placeholder="选择结束时间"
                format="YYYY-MM-DD HH:mm:ss"
                value-format="YYYY-MM-DD HH:mm:ss"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
        </el-row>

        <el-row>
          <el-col :span="24" class="text-right">
            <el-button
              type="primary"
              size="large"
              @click="fetchData"
              :loading="fetching"
              :disabled="!syncForm.siteId || !apiConfig.token"
            >
              <el-icon><Download /></el-icon>
              获取并预览数据
            </el-button>
          </el-col>
        </el-row>
      </el-form>

      <!-- 时间范围说明 -->
      <div class="time-range-info">
        <el-alert
          :type="timeMode === 'auto' ? 'info' : 'warning'"
          :closable="false"
          show-icon
        >
          <template #title>
            <strong>时间范围：</strong>{{ getDisplayTimeRange() }}
          </template>
          <div v-if="timeMode === 'auto'">
            • 系统自动将北京时间转换为UTC时间
          </div>
          <div v-else>
            • 手动输入的时间将作为北京时间处理，自动转换为UTC时间
          </div>
          <div>• 只统计处理时间在1小时内的有效记录</div>
        </el-alert>
      </div>
    </el-card>

    <!-- 数据预览卡片 -->
    <el-card
      v-if="previewData && previewData.length > 0"
      class="preview-card"
      shadow="hover"
    >
      <template #header>
        <div class="card-header">
          <span>
            <el-icon><View /></el-icon>
            数据预览
            <el-tag type="success" size="small" style="margin-left: 8px">
              共 {{ previewData.length }} 个账号
            </el-tag>
            <el-tag type="info" size="small" style="margin-left: 8px">
              总计 {{ totalOrders }} 笔订单
            </el-tag>
          </span>
          <span class="preview-date">
            <el-icon><Calendar /></el-icon>
            {{ getDisplayTimeRange() }}
          </span>
        </div>
      </template>

      <el-table
        :data="previewData"
        stripe
        border
        style="width: 100%"
        :default-sort="{ prop: 'total_orders', order: 'descending' }"
      >
        <el-table-column type="index" label="序号" width="60" align="center">
          <template #default="{ $index }">
            <span :class="getRankClass($index)">{{ $index + 1 }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="account_name" label="后台账号" min-width="150">
          <template #default="{ row }">
            <div class="account-cell">
              <el-icon><User /></el-icon>
              <span>{{ row.account_name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="employee_name" label="员工姓名" min-width="120">
          <template #default="{ row }">
            <span>{{ row.employee_name || "-" }}</span>
          </template>
        </el-table-column>
        <el-table-column
          prop="total_orders"
          label="处理笔数"
          width="100"
          align="center"
          sortable
        >
          <template #default="{ row }">
            <el-tag type="primary" size="large">{{ row.total_orders }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column
          prop="avg_time_str"
          label="平均处理时间"
          width="140"
          align="center"
          sortable
        >
          <template #default="{ row }">
            <el-tag :type="getAvgTimeType(row.avg_seconds)" size="large">
              <el-icon><Timer /></el-icon>
              {{ row.avg_time_str }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="匹配状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="row.is_matched ? 'success' : 'warning'" size="small">
              {{ row.is_matched ? "已匹配" : "未匹配" }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>

      <div class="sync-actions">
        <el-button
          type="success"
          size="large"
          @click="confirmSync"
          :loading="syncing"
        >
          <el-icon><Check /></el-icon>
          同步到本地统计
        </el-button>
        <el-button size="large" @click="previewData = null">
          <el-icon><Close /></el-icon>
          取消
        </el-button>
      </div>
    </el-card>

    <!-- 加载中状态 -->
    <div v-if="fetching && !previewData" class="loading-container">
      <el-skeleton :rows="5" animated />
      <div class="loading-text">
        <el-icon class="is-loading"><Loading /></el-icon>
        正在从外部系统获取数据，请稍候...
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  Connection,
  Download,
  Refresh,
  Sunny,
  Moon,
  Key,
  InfoFilled,
  View,
  Calendar,
  User,
  Timer,
  Check,
  Close,
  Loading,
  Setting,
  DataLine,
  Link,
  Document,
  MagicStick,
} from "@element-plus/icons-vue";
import api from "./admin_api";

// 站点列表
const sites = ref([]);

// 状态
const fetching = ref(false);
const syncing = ref(false);
const testing = ref(false);
const parsing = ref(false);
const previewData = ref(null);
const rawData = ref(null);
const importText = ref("");
const timeMode = ref("auto"); // 'auto' 或 'manual'

// API状态
const apiStatus = ref({
  type: "info",
  text: "未配置",
  message: "",
});

// API配置
const apiConfig = ref({
  baseUrl: "",
  token: "",
  tenantId: 7457478,
  regionId: 1,
  pageSize: 2000,
  timeout: 30,
});

// 同步参数
const syncForm = ref({
  siteId: null,
  shift: "day",
  date: getYesterdayDate(),
  startTime: "",
  endTime: "",
});

// 获取昨天日期
function getYesterdayDate() {
  const yesterday = new Date();
  yesterday.setDate(yesterday.getDate() - 1);
  return yesterday.toISOString().split("T")[0];
}

// 禁用未来日期
const disabledFutureDate = (time) => {
  return time.getTime() > Date.now();
};

// 总订单数
const totalOrders = computed(() => {
  if (!previewData.value) return 0;
  return previewData.value.reduce((sum, p) => sum + p.total_orders, 0);
});

// 获取显示的时间范围
const getDisplayTimeRange = () => {
  if (timeMode.value === "auto") {
    if (!syncForm.value.date) return "请选择日期";
    const date = syncForm.value.date;
    const isDayShift = syncForm.value.shift === "day";
    if (isDayShift) {
      return `${date} 08:00:00 至 ${date} 20:00:00 (北京时间)`;
    } else {
      const nextDate = new Date(date);
      nextDate.setDate(nextDate.getDate() + 1);
      const nextDateStr = nextDate.toISOString().split("T")[0];
      return `${date} 20:00:00 至 ${nextDateStr} 08:00:00 (北京时间)`;
    }
  } else {
    if (!syncForm.value.startTime || !syncForm.value.endTime) {
      return "请选择开始和结束时间";
    }
    return `${syncForm.value.startTime} 至 ${syncForm.value.endTime} (北京时间)`;
  }
};

// 获取标签类型
const getTagType = (type) => {
  const map = {
    success: "success",
    error: "danger",
    info: "info",
    warning: "warning",
  };
  return map[type] || "info";
};

// 解析导入的文本
const parseImportText = () => {
  if (!importText.value.trim()) {
    ElMessage.warning("请粘贴请求信息");
    return;
  }

  parsing.value = true;

  try {
    const text = importText.value;
    const extracted = {
      baseUrl: "",
      token: "",
      tenantId: null,
      regionId: null,
    };

    // 1. 提取API地址
    const urlMatch = text.match(/Request URL:\s*([^\s?]+)/i);
    if (urlMatch) {
      extracted.baseUrl = urlMatch[1];
    } else {
      const urlMatch2 = text.match(/https?:\/\/[^\s?]+/i);
      if (urlMatch2) {
        extracted.baseUrl = urlMatch2[0].split("?")[0];
      }
    }

    // 2. 提取Token
    const tokenMatch = text.match(/authorization:\s*Bearer\s+([a-zA-Z0-9]+)/i);
    if (tokenMatch) {
      extracted.token = tokenMatch[1];
    }
    const tokenMatch2 = text.match(/Bearer\s+([a-zA-Z0-9]+)/i);
    if (tokenMatch2 && !extracted.token) {
      extracted.token = tokenMatch2[1];
    }

    // 3. 提取租户ID - 支持多种格式
    const tenantMatch1 = text.match(/tenantId["']?\s*:\s*(\d+)/i);
    if (tenantMatch1) extracted.tenantId = parseInt(tenantMatch1[1]);
    const tenantMatch2 = text.match(/["']tenantId["']\s*:\s*(\d+)/i);
    if (tenantMatch2 && !extracted.tenantId)
      extracted.tenantId = parseInt(tenantMatch2[1]);
    const urlTenantMatch = text.match(/%22tenantId%22%3A(\d+)/i);
    if (urlTenantMatch && !extracted.tenantId)
      extracted.tenantId = parseInt(urlTenantMatch[1]);

    // 4. 提取区域ID
    const regionMatch1 = text.match(/regionId["']?\s*:\s*(\d+)/i);
    if (regionMatch1) extracted.regionId = parseInt(regionMatch1[1]);
    const urlRegionMatch = text.match(/%22regionId%22%3A(\d+)/i);
    if (urlRegionMatch && !extracted.regionId)
      extracted.regionId = parseInt(urlRegionMatch[1]);

    // 填充到表单
    if (extracted.baseUrl) apiConfig.value.baseUrl = extracted.baseUrl;
    if (extracted.token) apiConfig.value.token = extracted.token;
    if (extracted.tenantId) apiConfig.value.tenantId = extracted.tenantId;
    if (extracted.regionId) apiConfig.value.regionId = extracted.regionId;

    const extractedItems = [];
    if (extracted.baseUrl) extractedItems.push("API地址");
    if (extracted.token) extractedItems.push("Token");
    if (extracted.tenantId)
      extractedItems.push(`租户ID (${extracted.tenantId})`);
    if (extracted.regionId)
      extractedItems.push(`区域ID (${extracted.regionId})`);

    if (extractedItems.length > 0) {
      ElMessage.success(`成功提取: ${extractedItems.join("、")}`);
    } else {
      ElMessage.warning("未能提取到有效信息，请检查粘贴内容格式");
    }
  } catch (error) {
    console.error("解析失败:", error);
    ElMessage.error("解析失败，请检查粘贴内容");
  } finally {
    parsing.value = false;
  }
};

// 构建API请求的时间参数
const buildTimeParams = () => {
  if (timeMode.value === "auto") {
    // 自动模式：根据日期和班次计算
    const date = syncForm.value.date;
    const shift = syncForm.value.shift;
    const beijingDate = new Date(date);
    let startBeijing, endBeijing;

    if (shift === "day") {
      startBeijing = new Date(beijingDate);
      startBeijing.setHours(8, 0, 0, 0);
      endBeijing = new Date(beijingDate);
      endBeijing.setHours(20, 0, 0, 0);
    } else {
      startBeijing = new Date(beijingDate);
      startBeijing.setHours(20, 0, 0, 0);
      endBeijing = new Date(beijingDate);
      endBeijing.setDate(endBeijing.getDate() + 1);
      endBeijing.setHours(8, 0, 0, 0);
    }

    const startUTC = new Date(startBeijing.getTime() - 8 * 60 * 60 * 1000);
    const endUTC = new Date(endBeijing.getTime() - 8 * 60 * 60 * 1000);

    return {
      startTime: startUTC.toISOString(),
      endTime: endUTC.toISOString(),
      startTimeUTC: startUTC.toISOString(),
      endTimeUTC: endUTC.toISOString(),
    };
  } else {
    // 手动模式：直接使用用户输入的时间
    const startBeijing = new Date(syncForm.value.startTime);
    const endBeijing = new Date(syncForm.value.endTime);

    const startUTC = new Date(startBeijing.getTime() - 8 * 60 * 60 * 1000);
    const endUTC = new Date(endBeijing.getTime() - 8 * 60 * 60 * 1000);

    return {
      startTime: startUTC.toISOString(),
      endTime: endUTC.toISOString(),
      startTimeUTC: startUTC.toISOString(),
      endTimeUTC: endUTC.toISOString(),
    };
  }
};

// 从外部API获取提现审核数据
const fetchWithdrawalData = async (params) => {
  const requestParams = {
    page: params.page || 1,
    pageSize: params.pageSize || apiConfig.value.pageSize,
    queryTimeType: "completeTime",
    regionId: apiConfig.value.regionId,
    tenantId: apiConfig.value.tenantId,
    startTime: params.startTime,
    endTime: params.endTime,
    startTimeUTC: params.startTime,
    endTimeUTC: params.endTime,
  };

  let baseUrl = apiConfig.value.baseUrl;
  if (!baseUrl.includes("withdrawal.ReviewedList")) {
    if (baseUrl.endsWith("/")) {
      baseUrl = `${baseUrl}withdrawal.ReviewedList`;
    } else {
      baseUrl = `${baseUrl}/withdrawal.ReviewedList`;
    }
  }

  const url = `${baseUrl}?input=${encodeURIComponent(JSON.stringify({ json: requestParams }))}`;

  console.log("请求URL:", url);
  console.log("租户ID:", apiConfig.value.tenantId);
  console.log("区域ID:", apiConfig.value.regionId);
  console.log("时间参数:", {
    startTime: params.startTime,
    endTime: params.endTime,
  });

  const controller = new AbortController();
  const timeoutId = setTimeout(
    () => controller.abort(),
    apiConfig.value.timeout * 1000,
  );

  try {
    const response = await fetch(url, {
      method: "GET",
      headers: {
        Authorization: `Bearer ${apiConfig.value.token}`,
        "Content-Type": "application/json",
        Accept: "*/*",
        "client-language": "zh-CN",
      },
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    return await response.json();
  } catch (error) {
    clearTimeout(timeoutId);
    throw error;
  }
};

// 处理提现数据
const processWithdrawalData = (withdrawalList, employeeMap) => {
  const records = withdrawalList?.result?.data?.json?.queryData || [];

  console.log("获取到的记录数:", records.length);
  if (records.length > 0) {
    console.log("示例记录:", records[0]);
  }

  const accountStats = {};

  for (const record of records) {
    const accountName = record.OperationalInfo || record.account;
    if (!accountName) continue;

    const startTime = record.createTime;
    const endTime = record.updateTime;

    let processSeconds = 0;
    if (startTime && endTime) {
      const start = new Date(startTime);
      const end = new Date(endTime);
      const diff = (end - start) / 1000;
      if (diff > 0 && diff < 3600) {
        processSeconds = Math.floor(diff);
      }
    }

    if (!accountStats[accountName]) {
      accountStats[accountName] = {
        account_name: accountName,
        total_orders: 0,
        total_time_seconds: 0,
        valid_time_count: 0,
      };
    }

    accountStats[accountName].total_orders += 1;
    if (processSeconds > 0) {
      accountStats[accountName].total_time_seconds += processSeconds;
      accountStats[accountName].valid_time_count += 1;
    }
  }

  const preview = [];
  for (const [accountName, stats] of Object.entries(accountStats)) {
    const avgSeconds =
      stats.valid_time_count > 0
        ? Math.round(stats.total_time_seconds / stats.valid_time_count)
        : 0;

    preview.push({
      account_name: accountName,
      employee_name: employeeMap[accountName]?.name || null,
      employee_id: employeeMap[accountName]?.id || null,
      total_orders: stats.total_orders,
      avg_time_str: formatSecondsToTime(avgSeconds),
      avg_seconds: avgSeconds,
      is_matched: !!employeeMap[accountName],
      stats: stats,
    });
  }

  preview.sort((a, b) => b.total_orders - a.total_orders);

  return { preview, rawStats: accountStats };
};

// 测试连接
const testConnection = async () => {
  if (!apiConfig.value.baseUrl) {
    ElMessage.warning("请填写API地址");
    return;
  }

  if (!apiConfig.value.token) {
    ElMessage.warning("请填写Bearer Token");
    return;
  }

  testing.value = true;
  apiStatus.value = {
    type: "info",
    text: "测试中",
    message: "正在测试连接...",
  };

  try {
    const timeParams = buildTimeParams();

    const response = await fetchWithdrawalData({
      page: 1,
      pageSize: 1,
      ...timeParams,
    });

    if (response?.result?.data?.json) {
      const total = response.result.data.json.total || 0;
      apiStatus.value = {
        type: "success",
        text: "已连接",
        message: `连接成功！共 ${total} 条记录，租户ID: ${apiConfig.value.tenantId}`,
      };
      ElMessage.success(`连接成功！共 ${total} 条记录`);
    } else {
      throw new Error("返回数据格式异常");
    }
  } catch (error) {
    console.error("连接测试失败:", error);

    let errorMessage = error.message;
    if (error.message.includes("401")) {
      errorMessage = "Token无效或已过期，请重新获取Token";
    } else if (error.message.includes("403")) {
      errorMessage = `没有访问权限，请检查Token是否有权访问租户ID ${apiConfig.value.tenantId}`;
    } else if (error.message.includes("404")) {
      errorMessage = "API地址错误，请检查地址";
    }

    apiStatus.value = {
      type: "error",
      text: "连接失败",
      message: errorMessage,
    };
    ElMessage.error(errorMessage);
  } finally {
    testing.value = false;
  }
};

// 获取数据
const fetchData = async () => {
  if (!syncForm.value.siteId) {
    ElMessage.warning("请选择目标站点");
    return;
  }

  // 验证时间参数
  if (timeMode.value === "auto") {
    if (!syncForm.value.date) {
      ElMessage.warning("请选择统计日期");
      return;
    }
  } else {
    if (!syncForm.value.startTime || !syncForm.value.endTime) {
      ElMessage.warning("请选择开始时间和结束时间");
      return;
    }
    if (
      new Date(syncForm.value.startTime) >= new Date(syncForm.value.endTime)
    ) {
      ElMessage.warning("结束时间必须大于开始时间");
      return;
    }
  }

  if (!apiConfig.value.token) {
    ElMessage.warning("请先配置API Token");
    return;
  }

  fetching.value = true;
  previewData.value = null;

  try {
    const timeParams = buildTimeParams();

    ElMessage.info("正在从外部系统获取数据...");

    const response = await fetchWithdrawalData({
      page: 1,
      pageSize: apiConfig.value.pageSize,
      ...timeParams,
    });

    const employeeResponse = await api.get("/site-stats/employee-accounts", {
      params: { site_id: syncForm.value.siteId, limit: 1000 },
    });

    const employeeMap = {};
    employeeResponse.items?.forEach((emp) => {
      employeeMap[emp.account_name] = emp;
    });

    const { preview, rawStats } = processWithdrawalData(response, employeeMap);

    if (preview.length === 0) {
      ElMessage.warning("该时间段没有找到数据");
      return;
    }

    previewData.value = preview;
    rawData.value = rawStats;

    const totalOrdersCount = preview.reduce(
      (sum, p) => sum + p.total_orders,
      0,
    );
    ElMessage.success(
      `成功获取 ${preview.length} 个账号，共 ${totalOrdersCount} 笔订单`,
    );
  } catch (error) {
    console.error("获取数据失败:", error);
    ElMessage.error(error.message || "获取数据失败，请检查API配置");
  } finally {
    fetching.value = false;
  }
};

// 确认同步到本地
// 确认同步到本地
const confirmSync = async () => {
  if (!rawData.value) return;

  try {
    await ElMessageBox.confirm(
      `将同步 ${previewData.value.length} 个账号的数据到本地统计系统，是否继续？\n时间段：${getDisplayTimeRange()}`,
      "确认同步",
      {
        confirmButtonText: "确定同步",
        cancelButtonText: "取消",
        type: "info",
      },
    );

    syncing.value = true;

    const formData = new FormData();
    formData.append("site_id", syncForm.value.siteId);
    formData.append(
      "shift",
      timeMode.value === "auto" ? syncForm.value.shift : "manual",
    );
    formData.append(
      "date",
      timeMode.value === "auto"
        ? syncForm.value.date
        : new Date().toISOString().split("T")[0],
    );
    formData.append("data", JSON.stringify(rawData.value));

    // ✅ 手动模式时传递开始和结束时间
    if (timeMode.value === "manual") {
      formData.append("start_time", syncForm.value.startTime);
      formData.append("end_time", syncForm.value.endTime);
    }

    console.log("同步请求参数:");
    for (let [key, value] of formData.entries()) {
      console.log(`  ${key}: ${value}`);
    }

    const response = await api.post("/site-stats/sync", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });

    ElMessage.success(
      `同步成功！共同步 ${previewData.value.length} 个账号的数据`,
    );

    previewData.value = null;
    rawData.value = null;
  } catch (error) {
    if (error !== "cancel") {
      console.error("同步失败:", error);
      if (error.response) {
        console.error("错误详情:", error.response.data);
        ElMessage.error(error.response.data?.detail || "同步失败");
      } else {
        ElMessage.error(error.message || "同步失败");
      }
    }
  } finally {
    syncing.value = false;
  }
};

// 保存API配置
const saveApiConfig = () => {
  if (!apiConfig.value.baseUrl) {
    ElMessage.warning("请填写API地址");
    return;
  }

  if (!apiConfig.value.token) {
    ElMessage.warning("请填写Bearer Token");
    return;
  }

  localStorage.setItem(
    "withdrawal_api_config",
    JSON.stringify(apiConfig.value),
  );
  ElMessage.success("API配置已保存");
};

// 重置API配置
const resetApiConfig = () => {
  apiConfig.value = {
    baseUrl: "",
    token: "",
    tenantId: 7457478,
    regionId: 1,
    pageSize: 2000,
    timeout: 30,
  };
  apiStatus.value = { type: "info", text: "未配置", message: "" };
  ElMessage.info("API配置已重置");
};

// 加载API配置
const loadApiConfig = () => {
  const saved = localStorage.getItem("withdrawal_api_config");
  if (saved) {
    try {
      const config = JSON.parse(saved);
      apiConfig.value = { ...apiConfig.value, ...config };
      apiStatus.value = {
        type: "info",
        text: "已加载",
        message: "配置已从本地加载",
      };
    } catch (e) {
      console.error("加载配置失败:", e);
    }
  }
};

// 加载站点列表
const loadSites = async () => {
  try {
    const response = await api.get("/site-stats/sites", {
      params: { is_active: true },
    });
    sites.value = response.items || [];
  } catch (error) {
    console.error("加载站点失败:", error);
  }
};

// 格式化时间
const formatSecondsToTime = (seconds) => {
  if (!seconds || seconds <= 0) return "0秒";
  const minutes = Math.floor(seconds / 60);
  const secs = seconds % 60;
  if (minutes > 0 && secs > 0) return `${minutes}分${secs}秒`;
  if (minutes > 0) return `${minutes}分`;
  return `${secs}秒`;
};

// 获取排名样式
const getRankClass = (index) => {
  if (index === 0) return "rank-gold";
  if (index === 1) return "rank-silver";
  if (index === 2) return "rank-bronze";
  return "";
};

// 获取平均时间标签类型
const getAvgTimeType = (seconds) => {
  if (!seconds) return "info";
  if (seconds < 60) return "success";
  if (seconds < 120) return "warning";
  return "danger";
};

onMounted(() => {
  loadSites();
  loadApiConfig();
});
</script>

<style scoped>
/* 样式保持不变 */
.data-sync-page {
  padding: 20px;
  background: #f0f2f5;
  min-height: 100vh;
}

.page-header {
  margin-bottom: 24px;
}

.page-header h2 {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 24px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 8px;
}

.page-desc {
  color: #909399;
  font-size: 14px;
  margin: 0;
}

.import-card,
.config-card,
.sync-card,
.preview-card {
  margin-bottom: 20px;
  border-radius: 12px;
}

.import-card :deep(.el-card__body) {
  padding: 20px;
}

.import-actions {
  margin-top: 12px;
  display: flex;
  gap: 12px;
}

.import-tip {
  margin-top: 12px;
  font-size: 12px;
  color: #909399;
  display: flex;
  align-items: center;
  gap: 4px;
}

.config-card :deep(.el-card__body),
.sync-card :deep(.el-card__body) {
  padding: 24px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.form-tip {
  margin-top: 4px;
  font-size: 12px;
  color: #909399;
}

.time-range-info {
  margin-top: 20px;
}

.text-right {
  text-align: right;
  margin-top: 16px;
}

.api-status {
  margin-top: 16px;
}

.preview-card :deep(.el-card__body) {
  padding: 20px;
}

.preview-date {
  font-size: 14px;
  color: #606266;
  display: flex;
  align-items: center;
  gap: 4px;
}

.account-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.sync-actions {
  margin-top: 24px;
  display: flex;
  justify-content: center;
  gap: 16px;
  padding-top: 16px;
  border-top: 1px solid #ebeef5;
}

.loading-container {
  padding: 40px;
  text-align: center;
}

.loading-text {
  margin-top: 20px;
  color: #909399;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.rank-gold {
  font-weight: bold;
  color: #ffd700;
}

.rank-silver {
  font-weight: bold;
  color: #c0c0c0;
}

.rank-bronze {
  font-weight: bold;
  color: #cd7f32;
}
</style>
