<template>
  <div class="site-stats">
    <!-- 筛选栏 -->
    <!-- 筛选栏 -->
    <el-card class="filter-bar" shadow="hover">
      <el-row :gutter="16" align="middle">
        <el-col :span="5">
          <el-select
            v-model="filters.siteId"
            placeholder="选择站点"
            clearable
            filterable
            @change="handleSiteFilterChange"
          >
            <el-option
              v-for="site in sites"
              :key="site.id"
              :label="`${site.code} - ${site.name}`"
              :value="site.id"
            />
          </el-select>
        </el-col>
        <el-col :span="5">
          <el-select
            v-model="filters.employeeId"
            placeholder="选择员工"
            clearable
            filterable
            @change="loadData"
            :disabled="!filters.siteId"
          >
            <el-option
              v-for="emp in filteredEmployees"
              :key="emp.id"
              :label="`${emp.name} (${emp.account_name})`"
              :value="emp.id"
            />
          </el-select>
        </el-col>
        <el-col :span="6">
          <el-date-picker
            v-model="filters.dateRange"
            type="daterange"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
            @change="handleDateRangeChange"
            style="width: 100%"
          />
        </el-col>
        <el-col :span="3">
          <el-radio-group
            v-model="activeShift"
            @change="loadData"
            size="default"
          >
            <el-radio-button value="day">🌞 A班</el-radio-button>
            <el-radio-button value="night">🌙 B班</el-radio-button>
          </el-radio-group>
        </el-col>
        <el-col :span="5">
          <el-button-group>
            <el-button
              :type="displayMode === 'site' ? 'primary' : 'default'"
              @click="switchMode('site')"
            >
              站点汇总
            </el-button>
            <el-button
              :type="displayMode === 'stacked' ? 'primary' : 'default'"
              @click="switchMode('stacked')"
            >
              日期堆叠
            </el-button>
          </el-button-group>
        </el-col>
      </el-row>
    </el-card>

    <!-- 统计卡片 -->
    <el-row :gutter="20" class="stats-row">
      <el-col :span="6">
        <el-card class="stat-card" shadow="hover">
          <div class="stat-content">
            <div class="stat-icon" style="background: #e6f7ff; color: #1890ff">
              <el-icon><Document /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ summaryStats.totalRecords }}</div>
              <div class="stat-label">总记录数</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card" shadow="hover">
          <div class="stat-content">
            <div class="stat-icon" style="background: #f6ffed; color: #52c41a">
              <el-icon><TrendCharts /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ summaryStats.totalValue }}</div>
              <div class="stat-label">总处理笔数</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card" shadow="hover">
          <div class="stat-content">
            <div class="stat-icon" style="background: #fff7e6; color: #fa8c16">
              <el-icon><Timer /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ summaryStats.avgTimeStr }}</div>
              <div class="stat-label">平均处理时间</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card" shadow="hover">
          <div class="stat-content">
            <div class="stat-icon" style="background: #f9f0ff; color: #722ed1">
              <el-icon><User /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ summaryStats.activeEmployees }}</div>
              <div class="stat-label">出款人员</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 动态列表格 -->
    <!-- ========== 模式1：站点汇总模式（原有表格） ========== -->
    <el-card v-if="displayMode === 'site'" class="summary-card" shadow="hover">
      <template #header>
        <div
          class="card-header"
          style="
            display: flex;
            justify-content: space-between;
            align-items: center;
          "
        >
          <div>
            <span>
              <el-icon v-if="activeShift === 'day'"><Sunny /></el-icon>
              <el-icon v-else><Moon /></el-icon>
              {{ activeShift === "day" ? "A班" : "B班" }} - 出款统计
            </span>
            <span class="header-tip" v-if="selectedSiteName">
              (当前站点: {{ selectedSiteName }})
            </span>
          </div>
          <div>
            <el-button type="primary" @click="showUploadDialog">
              <el-icon><Upload /></el-icon>上传数据
            </el-button>
            <el-button @click="resetFilters">
              <el-icon><Refresh /></el-icon>重置筛选
            </el-button>
            <el-button @click="exportData" :disabled="summaryData.length === 0">
              <el-icon><Download /></el-icon>导出报表
            </el-button>
            <el-button type="danger" plain @click="showClearDialog">
              <el-icon><Delete /></el-icon>清除指定数据
            </el-button>
            <el-button type="danger" @click="clearAllData" plain>
              <el-icon><Delete /></el-icon>清空所有数据
            </el-button>
          </div>
        </div>
      </template>

      <!-- 原有表格内容保持不变 -->
      <el-table
        v-loading="loading"
        :data="sortedSummaryData"
        stripe
        style="width: 100%"
        border
        height="calc(100vh - 280px)"
        @sort-change="handleSortChange"
        :header-cell-style="{
          background:
            'linear-gradient(180deg, #A6CDF7 0%, #62ADF0 50%, #0971E0 100%)',
          color: '#1a2a3a',
          fontWeight: 'bold',
          fontSize: '14px',
          borderTop: '1px solid rgba(255,255,255,0.6)',
          borderBottom: '2px solid #7cb3e0',
          boxShadow:
            'inset 0 1px 0 rgba(255,255,255,0.4), 0 2px 6px rgba(0,0,0,0.08)',
          textShadow: '0 1px 0 rgba(255,255,255,0.3)',
        }"
      >
        <el-table-column
          type="index"
          width="60"
          fixed="left"
          label="序号"
          align="center"
        />
        <el-table-column
          label="统计日期"
          width="120"
          fixed="left"
          align="center"
        >
          <template #default>
            <div class="date-cell">
              <span class="display-date">
                {{
                  filters.dateRange && filters.dateRange.length === 2
                    ? `${filters.dateRange[0]} 至 ${filters.dateRange[1]}`
                    : selectedDate
                }}
              </span>
            </div>
          </template>
        </el-table-column>
        <el-table-column
          prop="employee_name"
          label="姓名"
          min-width="70"
          fixed="left"
          align="center"
        />

        <!-- 动态站点列 -->
        <el-table-column
          v-for="site in siteColumns"
          :key="site"
          :label="site"
          min-width="140"
          align="center"
          sortable="custom"
          :prop="`sites.${site}.value`"
        >
          <template #default="{ row }">
            <div v-if="row.sites && row.sites[site]" class="site-cell">
              <div class="value">笔数: {{ row.sites[site].value || 0 }}</div>
              <div class="time">
                平均: {{ row.sites[site].avg_time_str || "-" }}
              </div>
            </div>
            <div v-else class="site-cell empty">
              <div class="value">-</div>
            </div>
          </template>
        </el-table-column>

        <el-table-column
          label="总计"
          min-width="140"
          align="center"
          fixed="right"
          sortable="custom"
          prop="total_value"
        >
          <template #default="{ row }">
            <div class="total-cell">
              <div class="value">笔数: {{ row.total_value || 0 }}</div>
              <div class="time">平均: {{ row.total_avg_time || "-" }}</div>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="!loading && summaryData.length === 0" class="empty-data">
        <el-empty description="暂无数据，请先上传数据文件" />
      </div>
    </el-card>

    <!-- ========== 模式2：日期堆叠模式（新增） ========== -->
    <el-card
      v-if="displayMode === 'stacked'"
      class="summary-card"
      shadow="hover"
    >
      <template #header>
        <div
          class="card-header"
          style="
            display: flex;
            justify-content: space-between;
            align-items: center;
          "
        >
          <div>
            <span>
              <el-icon v-if="activeShift === 'day'"><Sunny /></el-icon>
              <el-icon v-else><Moon /></el-icon>
              {{ activeShift === "day" ? "A班" : "B班" }} - 出款统计（日期堆叠）
            </span>
            <span
              class="header-tip"
              v-if="filters.dateRange && filters.dateRange.length === 2"
            >
              ({{ filters.dateRange[0] }} 至 {{ filters.dateRange[1] }})
            </span>
          </div>
          <div>
            <el-button type="primary" @click="showUploadDialog">
              <el-icon><Upload /></el-icon>上传数据
            </el-button>
            <el-button @click="resetFilters">
              <el-icon><Refresh /></el-icon>重置筛选
            </el-button>
            <el-button
              @click="exportStackedData"
              :disabled="stackedDisplayData.length === 0"
            >
              <el-icon><Download /></el-icon>导出报表
            </el-button>
            <el-button type="danger" plain @click="showClearDialog">
              <el-icon><Delete /></el-icon>清除指定数据
            </el-button>
            <el-button type="danger" @click="clearAllData" plain>
              <el-icon><Delete /></el-icon>清空所有数据
            </el-button>
          </div>
        </div>
      </template>

      <el-table
        v-loading="stackedLoading"
        :data="stackedDisplayData"
        stripe
        border
        height="calc(100vh - 280px)"
        style="width: 100%"
        :row-class-name="getRowClassName"
        :header-cell-style="{
          background:
            'linear-gradient(180deg, #A6CDF7 0%, #62ADF0 50%, #0971E0 100%)',
          color: '#1a2a3a',
          fontWeight: 'bold',
          fontSize: '14px',
          borderTop: '1px solid rgba(255,255,255,0.6)',
          borderBottom: '2px solid #7cb3e0',
          boxShadow:
            'inset 0 1px 0 rgba(255,255,255,0.4), 0 2px 6px rgba(0,0,0,0.08)',
          textShadow: '0 1px 0 rgba(255,255,255,0.3)',
        }"
      >
        <el-table-column
          type="index"
          width="60"
          label="序号"
          align="center"
          fixed="left"
        />

        <el-table-column
          prop="date"
          label="统计日期"
          width="110"
          align="center"
          fixed="left"
        >
          <template #default="{ row }">
            <span :class="{ 'date-group-start': row.isDateStart }">{{
              row.date
            }}</span>
          </template>
        </el-table-column>

        <el-table-column
          prop="employee_name"
          label="姓名"
          min-width="100"
          align="center"
          fixed="left"
        />

        <!-- 动态站点列 -->
        <el-table-column
          v-for="site in siteColumns"
          :key="site"
          :label="site"
          min-width="120"
          align="center"
        >
          <template #default="{ row }">
            <div v-if="row.sites && row.sites[site]" class="site-cell">
              <div class="value">{{ row.sites[site].value || 0 }}笔</div>
              <div class="time">{{ row.sites[site].avg_time_str || "-" }}</div>
            </div>
            <div v-else class="site-cell empty">
              <div class="value">-</div>
            </div>
          </template>
        </el-table-column>

        <el-table-column
          label="总计"
          min-width="100"
          align="center"
          fixed="right"
        >
          <template #default="{ row }">
            <div class="total-cell">
              <div class="value">{{ row.total_value || 0 }}笔</div>
              <div class="time">{{ row.total_avg_time || "-" }}</div>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <div
        v-if="!stackedLoading && stackedDisplayData.length === 0"
        class="empty-data"
      >
        <el-empty description="暂无数据" />
      </div>
    </el-card>

    <!-- 上传对话框（保持不变） -->
    <el-dialog v-model="uploadVisible" title="上传站点数据" width="700px">
      <el-form :model="uploadForm" label-width="100px">
        <el-form-item label="选择站点" required>
          <el-select
            v-model="uploadForm.siteId"
            placeholder="请选择站点"
            style="width: 100%"
            @change="handleSiteChange"
          >
            <el-option
              v-for="site in sites"
              :key="site.id"
              :label="`${site.code} - ${site.name}`"
              :value="site.id"
            />
          </el-select>
          <div class="form-tip">
            上传的数据将自动匹配该站点下已配置的员工账号
          </div>
        </el-form-item>

        <el-form-item label="选择班次" required>
          <el-radio-group v-model="uploadForm.shift">
            <el-radio value="day">🌞 A班</el-radio>
            <el-radio value="night">🌙 B班</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="统计日期" required>
          <el-date-picker
            v-model="uploadForm.statDate"
            type="date"
            placeholder="选择统计日期"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
            style="width: 100%"
            :clearable="false"
          />
          <div class="form-tip">默认显示昨天日期，可选择其他日期</div>
        </el-form-item>

        <el-form-item label="上传文件" required>
          <el-upload
            ref="uploadRef"
            :auto-upload="false"
            :on-change="handleFileChange"
            :limit="1"
            accept=".xlsx,.xls,.csv"
          >
            <el-button type="primary">
              <el-icon><Upload /></el-icon>选择文件
            </el-button>
            <template #tip>
              <div class="el-upload__tip">
                <p>文件格式要求：</p>
                <ul>
                  <li><strong>V列（第22列）</strong>：后台账号（必填）</li>
                  <li>
                    <strong>R列（第18列）</strong>：开始时间（用于计算处理时间）
                  </li>
                  <li>
                    <strong>S列（第19列）</strong>：完成时间（用于计算处理时间）
                  </li>
                </ul>
                <p style="color: #e6a23c">
                  注意：文件会自动跳过格式错误的行，只处理有效数据
                </p>
              </div>
            </template>
          </el-upload>
        </el-form-item>
      </el-form>

      <!-- 上传预览 -->
      <div v-if="uploadPreview" class="upload-preview">
        <el-divider>文件解析预览</el-divider>
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="文件名">
            {{ uploadPreview.filename }}
          </el-descriptions-item>
          <el-descriptions-item label="目标站点">
            {{ uploadPreview.site_code }} - {{ uploadPreview.site_name }}
          </el-descriptions-item>
          <el-descriptions-item label="班次">
            {{ uploadPreview.shift === "day" ? "A班" : "B班" }}
          </el-descriptions-item>
          <el-descriptions-item label="统计日期">
            {{ uploadPreview.statDate }}
          </el-descriptions-item>
          <el-descriptions-item label="识别到的账号数">
            {{ uploadPreview.account_count }}
          </el-descriptions-item>
        </el-descriptions>

        <!-- 账号匹配预览 -->
        <div v-if="uploadPreview.details && uploadPreview.details.length > 0">
          <el-divider>账号匹配详情</el-divider>
          <el-table :data="uploadPreview.details" size="small" max-height="200">
            <el-table-column prop="account_name" label="账号" min-width="120" />
            <el-table-column
              prop="order_count"
              label="笔数"
              width="80"
              align="center"
            />
            <el-table-column
              prop="avg_time_str"
              label="平均时间"
              width="100"
              align="center"
            />
            <el-table-column label="匹配状态" width="80" align="center">
              <template #default="{ row }">
                <el-tag
                  :type="row.is_matched ? 'success' : 'danger'"
                  size="small"
                >
                  {{ row.is_matched ? "已匹配" : "未匹配" }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
          <div
            v-if="
              uploadPreview.unmatched_accounts &&
              uploadPreview.unmatched_accounts.length > 0
            "
            class="unmatched-warning"
          >
            <el-alert
              :title="`发现 ${uploadPreview.unmatched_accounts.length} 个未匹配账号，请先在员工管理中添加这些账号`"
              type="warning"
              :closable="false"
              show-icon
            />
          </div>
        </div>
      </div>

      <template #footer>
        <el-button @click="uploadVisible = false">取消</el-button>
        <el-button type="primary" @click="uploadData" :loading="uploading">
          开始上传
        </el-button>
      </template>
    </el-dialog>

    <!-- 清除数据对话框 -->
    <el-dialog
      v-model="clearDialogVisible"
      title="清除站点数据"
      width="450px"
      @close="resetClearForm"
    >
      <el-form :model="clearForm" label-width="80px">
        <el-form-item label="选择站点" required>
          <el-select
            v-model="clearForm.siteId"
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

        <el-form-item label="选择班次" required>
          <el-radio-group v-model="clearForm.shift">
            <el-radio value="day">🌞 A班</el-radio>
            <el-radio value="night">🌙 B班</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="选择日期" required>
          <el-date-picker
            v-model="clearForm.date"
            type="date"
            placeholder="选择要清除的日期"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
            style="width: 100%"
            :disabled-date="disabledFutureDate"
          />
        </el-form-item>

        <el-alert title="⚠️ 警告" type="warning" :closable="false" show-icon>
          <template #default>
            此操作将删除该站点 {{ clearForm.shift === "day" ? "A班" : "B班" }}
            {{ clearForm.date || "所选日期" }} 的所有数据，不可恢复！
          </template>
        </el-alert>
      </el-form>

      <template #footer>
        <el-button @click="clearDialogVisible = false">取消</el-button>
        <el-button
          type="danger"
          @click="confirmClearData"
          :loading="clearingData"
        >
          确认清除
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from "vue";
import { ElMessage, ElMessageBox, ElLoading } from "element-plus";
import {
  Sunny,
  Moon,
  Upload,
  Refresh,
  Document,
  TrendCharts,
  Timer,
  User,
  Download,
  Delete,
} from "@element-plus/icons-vue";
import api from "./admin_api";
import { getCurrentBeijingTime, formatDate } from "./admin_timezone";

const loading = ref(false);
const sites = ref([]);
const allEmployees = ref([]);
const activeShift = ref("day");
const summaryData = ref([]);
const siteColumns = ref([]);
const selectedDate = ref(getTodayDate()); // 现在获取的是今天

const uploadVisible = ref(false);
const uploading = ref(false);
const uploadPreview = ref(null);
const uploadForm = ref({
  siteId: null,
  shift: "day",
  statDate: getTodayDate(), // 默认昨天
  file: null,
});
const uploadRef = ref(null);

const filters = ref({
  siteId: "",
  employeeId: "",
  dateRange: [],
});

const clearDialogVisible = ref(false);
const clearingData = ref(false);
const clearForm = ref({
  siteId: null,
  shift: "day",
  date: "",
});

// 显示清除数据对话框
const showClearDialog = () => {
  // 如果当前有选中的站点，自动填入
  clearForm.value = {
    siteId: filters.value.siteId || null,
    shift: activeShift.value,
    date: selectedDate.value || getTodayDate(),
  };
  clearDialogVisible.value = true;
};

// 重置清除表单
const resetClearForm = () => {
  clearForm.value = {
    siteId: null,
    shift: "day",
    date: "",
  };
};

// 禁用未来日期
const disabledFutureDate = (time) => {
  return time.getTime() > Date.now();
};

// 确认清除数据
const confirmClearData = async () => {
  if (!clearForm.value.siteId) {
    ElMessage.warning("请选择站点");
    return;
  }
  if (!clearForm.value.date) {
    ElMessage.warning("请选择日期");
    return;
  }

  clearingData.value = true;
  try {
    const params = new URLSearchParams();
    params.append("site_id", clearForm.value.siteId);
    params.append("shift", clearForm.value.shift);
    params.append("date", clearForm.value.date);

    const response = await fetch(
      `/api/site-stats/data/clear-by-date?${params.toString()}`,
      {
        method: "DELETE",
        headers: {
          Authorization: `Bearer ${localStorage.getItem("token")}`,
        },
      },
    );

    const result = await response.json();

    if (response.ok) {
      ElMessage.success(result.message || "数据清除成功");
      clearDialogVisible.value = false;
      // 刷新数据
      await loadData();
    } else {
      throw new Error(result.detail || "清除失败");
    }
  } catch (error) {
    console.error("清除数据失败:", error);
    ElMessage.error(error.message || "清除数据失败");
  } finally {
    clearingData.value = false;
  }
};

// 获取当天日期
function getTodayDate() {
  const beijingTimeStr = getCurrentBeijingTime(); // 返回 "2026-04-04 14:30:00"
  return beijingTimeStr.split(" ")[0]; // 提取日期部分 "2026-04-04"
}

// 获取选中的站点名称
const selectedSiteName = computed(() => {
  if (!filters.value.siteId) return "";
  const site = sites.value.find((s) => s.id === filters.value.siteId);
  return site ? `${site.code} - ${site.name}` : "";
});

// 根据选择的站点过滤员工列表
const filteredEmployees = computed(() => {
  if (!filters.value.siteId) return [];
  return allEmployees.value.filter(
    (emp) => emp.site_id === filters.value.siteId,
  );
});

// 统计汇总
// 统计汇总 - 根据当前模式返回不同的统计数据
const summaryStats = computed(() => {
  // 站点汇总模式：基于 summaryData
  if (displayMode.value === "site") {
    let totalRecords = 0;
    let totalValue = 0;
    let totalWeightedTime = 0;
    let totalWeight = 0;

    summaryData.value.forEach((row) => {
      totalRecords += row.total_value || 0;
      totalValue += row.total_value || 0;

      if (row.total_avg_seconds && row.total_value) {
        totalWeightedTime += row.total_avg_seconds * row.total_value;
        totalWeight += row.total_value;
      }
    });

    const avgTime =
      totalWeight > 0 ? Math.round(totalWeightedTime / totalWeight) : 0;

    return {
      totalRecords,
      totalValue,
      avgTimeStr: formatSecondsToTime(avgTime),
      activeEmployees: summaryData.value.length,
    };
  }

  // 日期堆叠模式：基于 stackedDisplayData
  else {
    let totalRecords = 0;
    let totalValue = 0;
    let totalWeightedTime = 0;
    let totalWeight = 0;

    // 用于统计不重复的员工
    const uniqueEmployees = new Set();

    stackedDisplayData.value.forEach((row) => {
      // 统计不重复的员工
      if (row.employee_name) {
        uniqueEmployees.add(row.employee_name);
      }

      totalRecords += row.total_value || 0;
      totalValue += row.total_value || 0;

      // 计算加权平均时间
      if (row.total_weighted_time && row.total_weight) {
        totalWeightedTime += row.total_weighted_time;
        totalWeight += row.total_weight;
      } else if (row.total_value > 0 && row.total_avg_time) {
        // 如果没有加权数据，从 avg_time_str 反推
        // 这里简单处理，直接累加 total_value 作为权重
        totalWeight += row.total_value;
      }
    });

    // 如果有加权数据，计算平均时间
    let avgTime = 0;
    if (totalWeight > 0 && totalWeightedTime > 0) {
      avgTime = Math.round(totalWeightedTime / totalWeight);
    } else if (totalWeight > 0) {
      // 如果没有加权时间，使用简化计算（取所有行的平均值）
      let sumAvg = 0;
      let count = 0;
      stackedDisplayData.value.forEach((row) => {
        if (row.total_avg_time && row.total_avg_time !== "-") {
          // 尝试解析时间字符串，这里简单处理，实际可能需要更复杂的解析
          count++;
        }
      });
    }

    return {
      totalRecords,
      totalValue,
      avgTimeStr: formatSecondsToTime(avgTime),
      activeEmployees: uniqueEmployees.size,
    };
  }
});

// 日期变化处理
const handleDateChange = (date) => {
  // 更新筛选条件中的日期范围
  if (date) {
    filters.value.dateRange = [date, date];
  } else {
    filters.value.dateRange = [];
  }
  loadData();
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
    ElMessage.error("加载站点失败");
  }
};

// 加载所有员工（带站点信息）
const loadEmployees = async () => {
  try {
    const response = await api.get("/site-stats/employee-accounts", {
      params: { limit: 1000 },
    });
    allEmployees.value = response.items || [];
  } catch (error) {
    console.error("加载员工失败:", error);
    ElMessage.error("加载员工失败");
  }
};

// 加载汇总数据

const loadData = async () => {
  loading.value = true;
  try {
    const params = {};
    if (filters.value.siteId) params.site_id = filters.value.siteId;
    if (filters.value.employeeId)
      params.employee_account_id = filters.value.employeeId;
    if (filters.value.dateRange && filters.value.dateRange.length === 2) {
      // ✅ 修改：添加时间部分，匹配数据库格式
      params.start_date = `${filters.value.dateRange[0]} 00:00:00`;
      params.end_date = `${filters.value.dateRange[1]} 23:59:59`;
    }
    params.shift = activeShift.value;

    console.log("请求参数:", params);

    const response = await api.get("/site-stats/summary", { params });

    summaryData.value = response.items || [];
    siteColumns.value = response.site_columns || [];

    console.log("加载数据成功:", {
      employees: summaryData.value.length,
      sites: siteColumns.value,
    });
  } catch (error) {
    console.error("加载数据失败:", error);
    ElMessage.error("加载数据失败");
  } finally {
    loading.value = false;
  }
};

// 站点筛选变化处理
const handleSiteFilterChange = () => {
  filters.value.employeeId = "";
  loadData();
};

// 重置筛选
// 重置筛选
const resetFilters = () => {
  filters.value = {
    siteId: "",
    employeeId: "",
    dateRange: [],
  };

  // 根据当前模式重置日期
  if (displayMode.value === "site") {
    siteSummaryDate.value = getTodayDate();
    filters.value.dateRange = [siteSummaryDate.value, siteSummaryDate.value];
  } else {
    initStackedDateRange();
    filters.value.dateRange = [...stackedDateRange.value];
  }

  if (displayMode.value === "site") {
    loadData();
  } else {
    loadStackedData();
  }
};

// 清空所有数据
const clearAllData = async () => {
  try {
    await ElMessageBox.confirm(
      "确定要清空所有站点数据吗？此操作不可恢复！\n\n注意：只会清空上传的数据记录，不会删除站点和员工配置。",
      "警告",
      {
        confirmButtonText: "确定清空",
        cancelButtonText: "取消",
        type: "warning",
      },
    );

    const loading = ElLoading.service({
      fullscreen: true,
      text: "正在清空数据...",
      background: "rgba(0, 0, 0, 0.7)",
    });

    try {
      const response = await api.delete("/site-stats/data/clear");
      ElMessage.success(response.message || "数据已清空");
      await loadData();
    } finally {
      loading.close();
    }
  } catch (error) {
    if (error !== "cancel") {
      console.error("清空数据失败:", error);
      ElMessage.error(error.response?.data?.detail || "清空数据失败");
    }
  }
};

// 显示上传对话框
const showUploadDialog = () => {
  uploadForm.value = {
    siteId: filters.value.siteId || null,
    shift: activeShift.value,
    statDate: getTodayDate(),
    file: null,
  };
  uploadPreview.value = null;
  if (uploadRef.value) uploadRef.value.clearFiles();
  uploadVisible.value = true;
};

// 站点变化时更新预览
const handleSiteChange = (siteId) => {
  if (uploadPreview.value) {
    const site = sites.value.find((s) => s.id === siteId);
    if (site) {
      uploadPreview.value.site_code = site.code;
      uploadPreview.value.site_name = site.name;
    }
  }
};

// 文件选择
const handleFileChange = async (file) => {
  uploadForm.value.file = file.raw;

  const site = sites.value.find((s) => s.id === uploadForm.value.siteId);
  uploadPreview.value = {
    filename: file.name,
    site_id: uploadForm.value.siteId,
    site_code: site?.code,
    site_name: site?.name,
    shift: uploadForm.value.shift,
    statDate: uploadForm.value.statDate,
    total_records: 0,
    account_count: 0,
    details: [],
    unmatched_accounts: [],
  };
};

// 上传数据
const uploadData = async () => {
  if (!uploadForm.value.siteId) {
    ElMessage.warning("请选择站点");
    return;
  }
  if (!uploadForm.value.file) {
    ElMessage.warning("请选择文件");
    return;
  }
  if (!uploadForm.value.statDate) {
    ElMessage.warning("请选择统计日期");
    return;
  }

  uploading.value = true;
  try {
    const formData = new FormData();
    formData.append("file", uploadForm.value.file);
    formData.append("site_id", uploadForm.value.siteId);
    formData.append("shift", uploadForm.value.shift);
    formData.append("date", uploadForm.value.statDate);

    const response = await api.post("/site-stats/upload", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });

    const result = response;

    if (uploadPreview.value) {
      uploadPreview.value.total_records = result.stats.total_records;
      uploadPreview.value.account_count = result.stats.total_accounts;
      uploadPreview.value.details = result.stats.details || [];
      uploadPreview.value.unmatched_accounts =
        result.stats.unmatched_accounts || [];
    }

    let message = `上传成功！共处理 ${result.stats.total_records} 条记录`;
    if (result.matched_count > 0) {
      message += `，匹配 ${result.matched_count} 个账号`;
    }
    if (result.unmatched_count > 0) {
      message += `，未匹配 ${result.unmatched_count} 个账号`;
    }
    ElMessage.success(message);

    if (result.unmatched_count > 0) {
      ElMessage.warning(
        `发现 ${result.unmatched_count} 个未匹配的账号，请在员工管理中添加`,
      );
    }

    uploadVisible.value = false;

    setTimeout(() => {
      loadData();
      loadEmployees();
    }, 500);
  } catch (error) {
    console.error("上传失败:", error);
    ElMessage.error(error.response?.data?.detail || "上传失败");
  } finally {
    uploading.value = false;
  }
};

// 导出数据
const exportData = () => {
  if (summaryData.value.length === 0) {
    ElMessage.warning("暂无数据可导出");
    return;
  }

  const exportRows = summaryData.value.map((row) => {
    const rowData = {
      统计日期: selectedDate.value,
      员工姓名: row.employee_name,
    };
    siteColumns.value.forEach((site) => {
      const siteData = row.sites[site];
      if (siteData) {
        rowData[`${site}_笔数`] = siteData.value;
        rowData[`${site}_平均时间`] = siteData.avg_time_str;
      } else {
        rowData[`${site}_笔数`] = "-";
        rowData[`${site}_平均时间`] = "-";
      }
    });
    rowData["总计_笔数"] = row.total_value;
    rowData["总计_平均时间"] = row.total_avg_time;
    return rowData;
  });

  const headers = Object.keys(exportRows[0]);
  const csvRows = [
    headers.join(","),
    ...exportRows.map((row) =>
      headers
        .map((h) => {
          const val = row[h] || "";
          return `"${String(val).replace(/"/g, '""')}"`;
        })
        .join(","),
    ),
  ];

  const blob = new Blob(["\uFEFF" + csvRows.join("\n")], {
    type: "text/csv;charset=utf-8;",
  });
  const link = document.createElement("a");
  const url = URL.createObjectURL(blob);
  link.href = url;

  const siteInfo = selectedSiteName.value || "全部站点";
  const shiftText = activeShift.value === "day" ? "A班" : "B班";

  link.setAttribute(
    "download",
    `${siteInfo}_${shiftText}_${selectedDate.value}_出款统计.csv`,
  );
  link.click();
  URL.revokeObjectURL(url);
};

const formatSecondsToTime = (seconds) => {
  if (!seconds || seconds <= 0) return "0秒";
  const minutes = Math.floor(seconds / 60);
  const secs = seconds % 60;
  if (minutes > 0 && secs > 0) return `${minutes}分${secs}秒`;
  if (minutes > 0) return `${minutes}分`;
  return `${secs}秒`;
};
// ==================== 新增：日期堆叠模式 ====================
const displayMode = ref("site"); // 'site' 或 'stacked'
const stackedLoading = ref(false);
const stackedRawData = ref([]);
const stackedDisplayData = ref([]);

// 切换模式
const switchMode = (mode) => {
  displayMode.value = mode;
  console.log("切换到模式:", mode, "当前班次:", activeShift.value);

  // 切换模式时重新设置日期范围
  setDateRangeByMode();

  if (mode === "site") {
    loadData();
  } else {
    loadStackedData();
  }
};

// 日期范围变化处理
const handleDateRangeChange = (value) => {
  if (displayMode.value === "site") {
    // 站点汇总模式：保存当天日期（取范围的开始日期）
    if (value && value.length === 2) {
      siteSummaryDate.value = value[0];
    }
  } else {
    // 日期堆叠模式：保存完整范围
    if (value && value.length === 2) {
      stackedDateRange.value = [...value];
    } else {
      stackedDateRange.value = [];
    }
  }

  // 重新加载数据
  if (displayMode.value === "site") {
    loadData();
  } else {
    loadStackedData();
  }
};

// 加载日期堆叠数据（最终优化版）
const loadStackedData = async () => {
  stackedLoading.value = true;

  try {
    const params = {};

    if (filters.value.siteId) {
      params.site_id = filters.value.siteId;
    }

    if (filters.value.employeeId) {
      params.employee_account_id = filters.value.employeeId;
    }

    if (filters.value.dateRange && filters.value.dateRange.length === 2) {
      params.start_date = `${filters.value.dateRange[0]} 00:00:00`;
      params.end_date = `${filters.value.dateRange[1]} 23:59:59`;
    }

    params.shift = activeShift.value;

    console.log("📊 堆叠请求参数:", params);

    const response = await api.get("/site-stats/stacked-summary", { params });

    const items = response.items || [];
    siteColumns.value = response.site_columns || [];

    console.log("📦 原始数据条数:", items.length);

    if (items.length === 0) {
      stackedDisplayData.value = [];
      return;
    }

    const map = new Map();

    for (const item of items) {
      // ✅ 使用 employee_name 作为分组 key（同名合并）
      const employeeKey = item.employee_name;
      if (!employeeKey) {
        console.warn("⚠️ 跳过无效数据:", item);
        continue;
      }

      // ✅ 强制转为字符串
      const key = `${item.date}|${String(employeeKey)}`;

      if (!map.has(key)) {
        map.set(key, {
          date: item.date,
          employee_id: item.employee_id,
          employee_name: item.employee_name,
          account_name: item.account_name,
          sites: {},
          total_value: 0,
          total_weighted_time: 0,
          total_weight: 0,
        });
      }

      const record = map.get(key);
      const siteCode = item.site_code;

      if (!record.sites[siteCode]) {
        record.sites[siteCode] = {
          value: 0,
          avg_time_seconds: 0,
          avg_time_str: "-",
        };
      }

      const site = record.sites[siteCode];
      const newValue = site.value + item.value;
      const oldTotalTime = site.value * site.avg_time_seconds;
      const newTotalTime = oldTotalTime + item.value * item.avg_time_seconds;
      const newAvg = newValue > 0 ? Math.round(newTotalTime / newValue) : 0;

      site.value = newValue;
      site.avg_time_seconds = newAvg;
      site.avg_time_str = formatSecondsToTime(newAvg);

      record.total_value += item.value;

      if (item.value > 0 && item.avg_time_seconds > 0) {
        record.total_weighted_time += item.value * item.avg_time_seconds;
        record.total_weight += item.value;
      }
    }

    // 合并完成后检查
    console.log("合并前条数:", items.length);
    console.log("合并后员工数:", map.size);
    console.log(
      "书记的站点数:",
      Array.from(map.values()).find((v) => v.employee_name === "书记")?.sites,
    );

    let dataArray = Array.from(map.values());

    dataArray.sort((a, b) => {
      if (a.date !== b.date) {
        return new Date(b.date) - new Date(a.date);
      }
      return (a.employee_name || "").localeCompare(b.employee_name || "");
    });

    let lastDate = null;

    for (const item of dataArray) {
      item.isDateStart = item.date !== lastDate;
      lastDate = item.date;

      if (item.total_weight > 0) {
        const avg = item.total_weighted_time / item.total_weight;
        item.total_avg_time = formatSecondsToTime(Math.round(avg));
      } else {
        item.total_avg_time = "-";
      }
    }

    stackedDisplayData.value = dataArray;

    console.log("✅ 合并后行数:", dataArray.length);
  } catch (error) {
    console.error("❌ 加载堆叠数据失败:", error);
    ElMessage.error(
      "加载数据失败: " + (error.response?.data?.detail || error.message),
    );
  } finally {
    stackedLoading.value = false;
  }
};

// 获取行样式（日期分组间的分隔线）
const getRowClassName = ({ row, rowIndex }) => {
  if (row.isDateStart && rowIndex > 0) {
    return "date-group-separator";
  }
  return "";
};

// 导出堆叠数据
const exportStackedData = () => {
  if (stackedDisplayData.value.length === 0) {
    ElMessage.warning("暂无数据可导出");
    return;
  }

  const exportRows = stackedDisplayData.value.map((row, index) => {
    const rowData = {
      序号: index + 1,
      统计日期: row.date,
      姓名: row.employee_name,
    };
    siteColumns.value.forEach((site) => {
      const siteData = row.sites[site];
      if (siteData && siteData.value > 0) {
        rowData[site] = `${siteData.value}笔/${siteData.avg_time_str}`;
      } else {
        rowData[site] = "-";
      }
    });
    rowData["总计"] = `${row.total_value}笔/${row.total_avg_time}`;
    return rowData;
  });

  const headers = Object.keys(exportRows[0]);
  const csvRows = [
    headers.join(","),
    ...exportRows.map((row) =>
      headers.map((h) => `"${row[h] || ""}"`).join(","),
    ),
  ];

  const blob = new Blob(["\uFEFF" + csvRows.join("\n")], {
    type: "text/csv;charset=utf-8;",
  });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  const shiftText = activeShift.value === "day" ? "A班" : "B班";
  link.setAttribute(
    "download",
    `${shiftText}_出款统计_堆叠视图_${new Date().toISOString().slice(0, 10)}.csv`,
  );
  link.click();
  URL.revokeObjectURL(link.href);
};

// ✅ 修改：监听筛选条件变化，根据当前模式重新加载数据
// 在 onMounted 之前添加
watch(
  [
    () => filters.value.siteId,
    () => filters.value.employeeId,
    () => filters.value.dateRange,
    activeShift,
  ],
  () => {
    console.log(
      "筛选条件变化，当前模式:",
      displayMode.value,
      "当前班次:",
      activeShift.value,
    );
    if (displayMode.value === "site") {
      loadData();
    } else if (displayMode.value === "stacked") {
      loadStackedData();
    }
  },
  { deep: true },
);

onMounted(() => {
  loadSites();
  loadEmployees();

  // 初始化堆叠模式的日期范围
  initStackedDateRange();

  // 默认显示站点汇总模式，使用当天日期
  displayMode.value = "site";
  siteSummaryDate.value = getTodayDate();
  filters.value.dateRange = [siteSummaryDate.value, siteSummaryDate.value];

  // 加载数据
  loadData();
});

// 排序相关
const sortField = ref("employee_name");
const sortOrder = ref("ascending");

// 在现有的 ref 声明区域添加（约第300行附近）

// 站点汇总模式的日期（当天）
const siteSummaryDate = ref(getTodayDate());

// 日期堆叠模式的日期范围（当月1-30号）
const stackedDateRange = ref([]);

// 获取当月1号和30号
const getCurrentMonthRange = () => {
  const now = new Date();
  const year = now.getFullYear();
  const month = now.getMonth();

  // 当月1号
  const firstDay = new Date(year, month, 1);
  // 当月30号
  let lastDay = new Date(year, month, 30);
  // 如果30号不存在（比如2月），则取当月最后一天
  if (lastDay.getMonth() !== month) {
    lastDay = new Date(year, month + 1, 0);
  }

  const formatDate = (date) => {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, "0");
    const d = String(date.getDate()).padStart(2, "0");
    return `${y}-${m}-${d}`;
  };

  return [formatDate(firstDay), formatDate(lastDay)];
};

// 初始化堆叠模式的日期范围
const initStackedDateRange = () => {
  const [startDate, endDate] = getCurrentMonthRange();
  stackedDateRange.value = [startDate, endDate];
};

// 根据当前模式设置日期筛选条件
const setDateRangeByMode = () => {
  if (displayMode.value === "site") {
    // 站点汇总模式：使用当天
    filters.value.dateRange = [siteSummaryDate.value, siteSummaryDate.value];
  } else {
    // 日期堆叠模式：使用1-30号范围
    if (stackedDateRange.value.length === 2) {
      filters.value.dateRange = [...stackedDateRange.value];
    } else {
      initStackedDateRange();
      filters.value.dateRange = [...stackedDateRange.value];
    }
  }
};

// 计算排序后的数据
const sortedSummaryData = computed(() => {
  let data = [...summaryData.value];

  if (!sortField.value) return data;

  data.sort((a, b) => {
    let valA, valB;

    // 处理站点列
    if (sortField.value.startsWith("sites.")) {
      const siteCode = sortField.value.split(".")[1];
      valA = a.sites?.[siteCode]?.value || 0;
      valB = b.sites?.[siteCode]?.value || 0;
    } else if (sortField.value === "total_value") {
      valA = a.total_value || 0;
      valB = b.total_value || 0;
    } else if (sortField.value === "stat_date") {
      valA = selectedDate.value;
      valB = selectedDate.value;
      return sortOrder.value === "ascending" ? 0 : 0;
    } else {
      // 员工姓名
      valA = a[sortField.value] || "";
      valB = b[sortField.value] || "";
    }

    if (typeof valA === "number" && typeof valB === "number") {
      return sortOrder.value === "ascending" ? valA - valB : valB - valA;
    } else {
      const strA = String(valA);
      const strB = String(valB);
      if (sortOrder.value === "ascending") {
        return strA.localeCompare(strB, "zh-CN");
      } else {
        return strB.localeCompare(strA, "zh-CN");
      }
    }
  });

  return data;
});

// 处理排序变化
const handleSortChange = ({ prop, order }) => {
  if (prop) {
    sortField.value = prop;
    sortOrder.value = order === "ascending" ? "ascending" : "descending";
  }
};
// 在 script setup 中添加 computed
const maxTotalValue = computed(() => {
  const values = summaryData.value.map((item) => item.total_value || 0);
  return values.length > 0 ? Math.max(...values) : 0;
});

const minTotalValue = computed(() => {
  const values = summaryData.value.map((item) => item.total_value || 0);
  return values.length > 0 ? Math.min(...values) : 0;
});

// 获取总计列单元格样式
const getTotalCellStyle = ({ row }) => {
  const totalValue = row.total_value || 0;
  const maxVal = maxTotalValue.value;
  const minVal = minTotalValue.value;

  // 如果只有一个值或所有值相同，不应用特殊样式
  if (maxVal === minVal) {
    return {};
  }

  // 最大值：淡绿色背景
  if (totalValue === maxVal) {
    return {
      backgroundColor: "#f0f9eb",
      color: "#67c23a",
      fontWeight: "bold",
    };
  }

  // 最小值：淡黄色背景
  if (totalValue === minVal) {
    return {
      backgroundColor: "#fdf6ec",
      color: "#e6a23c",
    };
  }

  return {};
};
</script>

<style scoped>
/* 样式保持不变，添加日期选择器样式 */
.date-cell {
  padding: 4px 0;
  font-size: 12px;
}

.date-cell :deep(.el-date-editor) {
  width: 100%;
}

.date-cell :deep(.el-input__wrapper) {
  padding: 0 8px;
}

/* 其他样式保持不变 */
.site-stats {
  padding: 20px;
}

.filter-bar {
  margin-bottom: 20px;
}

.filter-bar :deep(.el-card__body) {
  padding: 16px 20px;
}

.stats-row {
  margin-bottom: 20px;
}

.stat-card {
  cursor: default;
}

.stat-card :deep(.el-card__body) {
  padding: 16px;
}

.stat-content {
  display: flex;
  align-items: center;
}

.stat-icon {
  width: 48px;
  height: 48px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  margin-right: 16px;
}

.stat-info {
  flex: 1;
}

.stat-value {
  font-size: 24px;
  font-weight: bold;
  line-height: 1.2;
}

.stat-label {
  font-size: 14px;
  color: #909399;
  margin-top: 4px;
}

.action-bar {
  margin-bottom: 20px;
}

.text-right {
  text-align: right;
}

.summary-card {
  min-height: 400px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
}

.header-tip {
  font-size: 12px;
  color: #909399;
}

.site-cell {
  padding: 4px 0;
}

.site-cell .value {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
}

.site-cell .time {
  font-size: 14px;
  color: #909399;
  margin-top: 2px;
}

.site-cell.empty .value {
  color: #c0c4cc;
}

.total-cell {
  padding: 4px 0;
}

.total-cell .value {
  font-size: 14px;
  font-weight: 600;
  color: #409eff;
}

.total-cell .time {
  font-size: 14px;
  color: #909399;
  margin-top: 2px;
}

.form-tip {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}

.upload-preview {
  margin-top: 16px;
}

.upload-preview ul {
  margin: 4px 0;
  padding-left: 20px;
}

.upload-preview li {
  font-size: 12px;
  color: #606266;
}

.empty-data {
  padding: 40px 0;
}

.unmatched-warning {
  margin-top: 12px;
}

/* 日期堆叠模式 - 日期分组行样式 */
:deep(.date-group-separator) {
  border-top: 2px solid #409eff !important;
  background-color: #f0f9ff !important;
}

.date-group-start {
  font-weight: bold;
  color: #409eff;
}

:deep(.date-group-separator:hover) {
  background-color: #e6f7ff !important;
}
</style>
