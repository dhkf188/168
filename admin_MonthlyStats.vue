<template>
  <div class="monthly-stats">
    <!-- 筛选栏 -->
    <el-card class="filter-bar" shadow="hover">
      <el-row :gutter="16" align="middle">
        <el-col :span="6">
          <el-select
            v-model="filters.shift"
            placeholder="选择班次"
            clearable
            @change="loadData"
          >
            <el-option label="白班" value="day" />
            <el-option label="夜班" value="night" />
          </el-select>
        </el-col>
        <el-col :span="8">
          <el-date-picker
            v-model="filters.month"
            type="month"
            placeholder="选择月份"
            format="YYYY年MM月"
            value-format="YYYY-MM"
            @change="loadData"
            style="width: 100%"
          />
        </el-col>
        <el-col :span="6">
          <el-select
            v-model="filters.rankBy"
            placeholder="排行依据"
            @change="loadData"
          >
            <el-option label="处理订单总数" value="total_value" />
            <el-option label="平均处理时间" value="avg_time" />
            <el-option label="最快平均时间" value="fastest" />
          </el-select>
        </el-col>
        <el-col :span="4" class="text-right">
          <el-button @click="resetFilters">
            <el-icon><Refresh /></el-icon>重置
          </el-button>
          <el-button type="primary" @click="exportData">
            <el-icon><Download /></el-icon>导出报表
          </el-button>
        </el-col>
      </el-row>
    </el-card>

    <!-- 统计卡片 -->
    <el-row :gutter="20" class="stats-row">
      <el-col :span="6">
        <el-card class="stat-card" shadow="hover">
          <div class="stat-content">
            <div class="stat-icon" style="background: #e6f7ff; color: #1890ff">
              <el-icon><User /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ summaryStats.totalEmployees }}</div>
              <div class="stat-label">出款人数</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card" shadow="hover">
          <div class="stat-content">
            <div class="stat-icon" style="background: #f6ffed; color: #52c41a">
              <el-icon><Document /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ summaryStats.totalRecords }}</div>
              <div class="stat-label">订单总数</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card" shadow="hover">
          <div class="stat-content">
            <div class="stat-icon" style="background: #fff7e6; color: #fa8c16">
              <el-icon><TrendCharts /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ summaryStats.totalValue }}</div>
              <div class="stat-label">处理订单总数</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card" shadow="hover">
          <div class="stat-content">
            <div class="stat-icon" style="background: #f9f0ff; color: #722ed1">
              <el-icon><Timer /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ summaryStats.avgTimeStr }}</div>
              <div class="stat-label">整体平均时间</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 排行榜卡片 -->
    <el-row :gutter="20">
      <el-col :span="8">
        <el-card class="rank-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <span>
                <el-icon><Trophy /></el-icon>
                处理订单排行榜
              </span>
              <el-tag type="success" size="small">TOP 10</el-tag>
            </div>
          </template>
          <div class="rank-list">
            <div
              v-for="(item, index) in topByValue"
              :key="item.employee_name"
              class="rank-item"
              :class="{ 'top-three': index < 3 }"
            >
              <div class="rank-number" :class="getRankClass(index)">
                {{ index + 1 }}
              </div>
              <div class="rank-name">{{ item.employee_name }}</div>
              <div class="rank-value">{{ item.total_value }} 笔</div>
              <div class="rank-time">{{ item.total_avg_time }}</div>
            </div>
            <div v-if="topByValue.length === 0" class="empty-rank">
              暂无数据
            </div>
          </div>
        </el-card>
      </el-col>

      <el-col :span="8">
        <el-card class="rank-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <span>
                <el-icon><Timer /></el-icon>
                平均时间排行榜（快）
              </span>
              <el-tag type="warning" size="small">TOP 10</el-tag>
            </div>
          </template>
          <div class="rank-list">
            <div
              v-for="(item, index) in topByFastest"
              :key="item.employee_name"
              class="rank-item"
              :class="{ 'top-three': index < 3 }"
            >
              <div class="rank-number" :class="getRankClass(index)">
                {{ index + 1 }}
              </div>
              <div class="rank-name">{{ item.employee_name }}</div>
              <div class="rank-value">{{ item.total_value }} 笔</div>
              <div class="rank-time">{{ item.total_avg_time }}</div>
            </div>
            <div v-if="topByFastest.length === 0" class="empty-rank">
              暂无数据
            </div>
          </div>
        </el-card>
      </el-col>

      <el-col :span="8">
        <el-card class="rank-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <span>
                <el-icon><Warning /></el-icon>
                平均时间排行榜（慢）
              </span>
              <el-tag type="danger" size="small">TOP 10</el-tag>
            </div>
          </template>
          <div class="rank-list">
            <div
              v-for="(item, index) in topBySlowest"
              :key="item.employee_name"
              class="rank-item"
              :class="{ 'top-three': index < 3 }"
            >
              <div class="rank-number" :class="getRankClass(index)">
                {{ index + 1 }}
              </div>
              <div class="rank-name">{{ item.employee_name }}</div>
              <div class="rank-value">{{ item.total_value }} 笔</div>
              <div class="rank-time">{{ item.total_avg_time }}</div>
            </div>
            <div v-if="topBySlowest.length === 0" class="empty-rank">
              暂无数据
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 详细数据表格 -->
    <el-card class="table-card" shadow="hover">
      <template #header>
        <div class="card-header">
          <span>
            <el-icon><DataAnalysis /></el-icon>
            月度详细统计
            <span class="header-tip" v-if="filters.month">
              ({{ filters.month }})
            </span>
            <span class="header-tip" v-if="filters.shift === 'day'">白班</span>
            <span class="header-tip" v-else-if="filters.shift === 'night'"
              >夜班</span
            >
          </span>
        </div>
      </template>

      <el-table
        v-loading="loading"
        :data="sortedData"
        stripe
        style="width: 100%"
        border
        :default-sort="{ prop: 'total_value', order: 'descending' }"
        @sort-change="handleSortChange"
        :header-cell-style="{
          background:
            'linear-gradient(180deg, #1a3a5c 0%, #2c5a7a 50%, #3a7a9a 100%)',
          color: '#ffffff',
          fontWeight: 'bold',
          fontSize: '14px',
          textAlign: 'center',
          boxShadow:
            'inset 0 1px 0 rgba(255,255,255,0.2), 0 2px 4px rgba(0,0,0,0.1)',
        }"
      >
        <el-table-column type="index" width="50" label="排名" fixed="left">
          <template #default="{ $index }">
            <span :class="getRankClass($index)">{{ $index + 1 }}</span>
          </template>
        </el-table-column>

        <el-table-column
          prop="employee_name"
          label="处理人"
          min-width="100"
          fixed="left"
          align="center"
        />

        <!-- 动态站点列 -->
        <el-table-column
          v-for="site in siteColumns"
          :key="site"
          :prop="`sites.${site}.value`"
          :label="site"
          min-width="100"
          align="center"
          sortable="custom"
        >
          <template #default="{ row }">
            <span v-if="row.sites && row.sites[site]">
              {{ row.sites[site].value || 0 }}
            </span>
            <span v-else>-</span>
          </template>
        </el-table-column>

        <el-table-column
          prop="total_value"
          label="处理订单总数"
          min-width="120"
          align="center"
          sortable="custom"
          fixed="right"
        >
          <template #default="{ row }">
            <span class="total-value">{{ row.total_value || 0 }}</span>
          </template>
        </el-table-column>

        <el-table-column
          prop="total_avg_time"
          label="总平均时间"
          min-width="120"
          align="center"
          sortable="custom"
          fixed="right"
        >
          <template #default="{ row }">
            <el-tag :type="getAvgTimeType(row.total_avg_seconds)" size="small">
              {{ row.total_avg_time || "-" }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from "vue";
import { ElMessage } from "element-plus";
import {
  Refresh,
  Download,
  User,
  Document,
  TrendCharts,
  Timer,
  Trophy,
  Warning,
  DataAnalysis,
} from "@element-plus/icons-vue";
import api from "./admin_api";

const loading = ref(false);
const summaryData = ref([]);
const siteColumns = ref([]);
const sortField = ref("total_value");
const sortOrder = ref("descending");

const filters = ref({
  shift: "",
  month: getCurrentMonth(),
  rankBy: "total_value",
});

// 获取当前月份
function getCurrentMonth() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

// 统计汇总
// 统计汇总
const summaryStats = computed(() => {
  let totalEmployees = summaryData.value.length;
  let totalRecords = 0; // 总记录数 = 所有员工笔数之和
  let totalValue = 0;
  let totalWeightedTime = 0;
  let totalWeight = 0;

  summaryData.value.forEach((row) => {
    // ✅ 使用 total_value 作为总记录数
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
    totalEmployees,
    totalRecords, // ✅ 现在会有正确的数值
    totalValue,
    avgTimeStr: formatSecondsToTime(avgTime),
  };
});

// 出勤数排行榜 TOP 10
const topByValue = computed(() => {
  return [...summaryData.value]
    .sort((a, b) => (b.total_value || 0) - (a.total_value || 0))
    .slice(0, 10);
});

// 最快平均时间排行榜 TOP 10
const topByFastest = computed(() => {
  return [...summaryData.value]
    .filter((item) => item.total_avg_seconds > 0)
    .sort(
      (a, b) => (a.total_avg_seconds || 9999) - (b.total_avg_seconds || 9999),
    )
    .slice(0, 10);
});

// 最慢平均时间排行榜 TOP 10
const topBySlowest = computed(() => {
  return [...summaryData.value]
    .filter((item) => item.total_avg_seconds > 0)
    .sort((a, b) => (b.total_avg_seconds || 0) - (a.total_avg_seconds || 0))
    .slice(0, 10);
});

// 排序后的数据
const sortedData = computed(() => {
  let data = [...summaryData.value];

  if (sortField.value === "total_value") {
    data.sort((a, b) => {
      const valA = a.total_value || 0;
      const valB = b.total_value || 0;
      return sortOrder.value === "descending" ? valB - valA : valA - valB;
    });
  } else if (sortField.value === "total_avg_time") {
    data.sort((a, b) => {
      const valA = a.total_avg_seconds || 0;
      const valB = b.total_avg_seconds || 0;
      return sortOrder.value === "descending" ? valB - valA : valA - valB;
    });
  } else if (sortField.value.startsWith("sites.")) {
    // 站点列排序
    const siteCode = sortField.value.split(".")[1];
    data.sort((a, b) => {
      const valA = a.sites?.[siteCode]?.value || 0;
      const valB = b.sites?.[siteCode]?.value || 0;
      return sortOrder.value === "descending" ? valB - valA : valA - valB;
    });
  }

  return data;
});

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

// 加载数据
const loadData = async () => {
  loading.value = true;
  try {
    const params = {};
    if (filters.value.shift) params.shift = filters.value.shift;
    if (filters.value.month) {
      params.start_date = `${filters.value.month}-01`;
      const lastDay = new Date(filters.value.month + "-01");
      lastDay.setMonth(lastDay.getMonth() + 1);
      lastDay.setDate(0);
      params.end_date = `${filters.value.month}-${String(lastDay.getDate()).padStart(2, "0")}`;
    }

    const response = await api.get("/site-stats/summary", { params });

    summaryData.value = response.items || [];
    siteColumns.value = response.site_columns || [];

    console.log("加载月度数据成功:", {
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

// 排序变化处理
const handleSortChange = ({ prop, order }) => {
  if (prop) {
    sortField.value = prop;
    sortOrder.value = order;
  }
};

// 重置筛选
const resetFilters = () => {
  filters.value = {
    shift: "",
    month: getCurrentMonth(),
    rankBy: "total_value",
  };
  loadData();
};

// 导出数据
const exportData = () => {
  if (summaryData.value.length === 0) {
    ElMessage.warning("暂无数据可导出");
    return;
  }

  const exportRows = summaryData.value.map((row, index) => {
    const rowData = {
      排名: index + 1,
      处理人: row.employee_name,
    };
    siteColumns.value.forEach((site) => {
      const siteData = row.sites[site];
      rowData[site] = siteData?.value || "-";
    });
    rowData["总出勤数"] = row.total_value;
    rowData["总平均时间"] = row.total_avg_time;
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

  const shiftText =
    filters.value.shift === "day"
      ? "白班"
      : filters.value.shift === "night"
        ? "夜班"
        : "全部";
  link.setAttribute(
    "download",
    `${filters.value.month}_${shiftText}_月度汇总统计.csv`,
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

onMounted(() => {
  loadData();
});
</script>

<style scoped>
.monthly-stats {
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

.text-right {
  text-align: right;
}

/* 排行榜卡片样式 */
.rank-card {
  margin-bottom: 20px;
}

.rank-card :deep(.el-card__header) {
  background: #f5f7fa;
  padding: 12px 16px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.rank-list {
  max-height: 400px;
  overflow-y: auto;
}

.rank-item {
  display: flex;
  align-items: center;
  padding: 10px 12px;
  border-bottom: 1px solid #ebeef5;
  transition: background 0.3s;
}

.rank-item:hover {
  background: #f5f7fa;
}

.rank-item.top-three {
  background: #fef6e6;
}

.rank-number {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: bold;
  border-radius: 50%;
  margin-right: 12px;
  background: #f5f7fa;
  color: #606266;
}

.rank-number.rank-gold {
  background: linear-gradient(135deg, #ffd700, #ffb347);
  color: white;
}

.rank-number.rank-silver {
  background: linear-gradient(135deg, #c0c0c0, #a0a0a0);
  color: white;
}

.rank-number.rank-bronze {
  background: linear-gradient(135deg, #cd7f32, #b87333);
  color: white;
}

.rank-name {
  flex: 1;
  font-weight: 500;
  color: #303133;
}

.rank-value {
  margin-right: 16px;
  font-weight: bold;
  color: #409eff;
}

.rank-time {
  min-width: 80px;
  text-align: right;
  color: #909399;
  font-size: 12px;
}

.empty-rank {
  text-align: center;
  padding: 40px;
  color: #909399;
}

/* 表格样式 */
.table-card {
  margin-top: 20px;
}

.header-tip {
  font-size: 12px;
  color: #909399;
  margin-left: 8px;
}

.total-value {
  font-weight: bold;
  color: #409eff;
}

/* 排名样式 */
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
