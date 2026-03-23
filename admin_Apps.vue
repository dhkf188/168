<!-- admin_Apps.vue -->
<template>
  <div class="apps-monitor">
    <!-- 筛选栏 -->
    <el-card class="filter-bar" shadow="hover">
      <el-row :gutter="20" align="middle">
        <el-col :span="5">
          <el-select
            v-model="filters.employeeId"
            placeholder="选择员工"
            clearable
            filterable
            @change="handleFilterChange"
          >
            <el-option
              v-for="emp in employees"
              :key="emp.id"
              :label="emp.name"
              :value="emp.id"
            />
          </el-select>
        </el-col>

        <el-col :span="4">
          <el-input
            v-model="filters.appName"
            placeholder="软件名称"
            clearable
            @input="handleSearch"
          />
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
            @change="handleFilterChange"
          />
        </el-col>

        <el-col :span="5">
          <el-switch
            v-model="filters.foregroundOnly"
            active-text="仅前台应用"
            inactive-text="全部"
            @change="handleFilterChange"
          />
        </el-col>

        <el-col :span="4" class="text-right">
          <el-button type="primary" @click="loadData">
            <el-icon><Search /></el-icon>查询
          </el-button>
          <el-button @click="resetFilters">
            <el-icon><Refresh /></el-icon>重置
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
              <el-icon><Grid /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ stats.totalApps }}</div>
              <div class="stat-label">使用软件数</div>
            </div>
          </div>
        </el-card>
      </el-col>

      <el-col :span="6">
        <el-card class="stat-card" shadow="hover">
          <div class="stat-content">
            <div class="stat-icon" style="background: #f6ffed; color: #52c41a">
              <el-icon><Timer /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">
                {{ formatDuration(stats.totalDuration) }}
              </div>
              <div class="stat-label">总使用时长</div>
            </div>
          </div>
        </el-card>
      </el-col>

      <el-col :span="6">
        <el-card class="stat-card" shadow="hover">
          <div class="stat-content">
            <div class="stat-icon" style="background: #fff7e6; color: #fa8c16">
              <el-icon><Cpu /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ stats.avgCpu }}%</div>
              <div class="stat-label">平均CPU</div>
            </div>
          </div>
        </el-card>
      </el-col>

      <el-col :span="6">
        <el-card class="stat-card" shadow="hover">
          <div class="stat-content">
            <div class="stat-icon" style="background: #f9f0ff; color: #722ed1">
              <el-icon><Memo /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ stats.avgMemory }}MB</div>
              <div class="stat-label">平均内存</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 图表区域 -->
    <el-row :gutter="20" class="chart-row">
      <el-col :span="12">
        <el-card class="chart-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <span>软件使用TOP10</span>
            </div>
          </template>
          <div class="chart-container" ref="barChartRef"></div>
        </el-card>
      </el-col>

      <el-col :span="12">
        <el-card class="chart-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <span>使用趋势</span>
              <el-radio-group v-model="trendType" size="small">
                <el-radio-button label="hourly">按小时</el-radio-button>
                <el-radio-button label="daily">按天</el-radio-button>
              </el-radio-group>
            </div>
          </template>
          <div class="chart-container" ref="trendChartRef"></div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 软件使用列表 -->
    <el-card class="table-card" shadow="hover">
      <el-table v-loading="loading" :data="items" stripe style="width: 100%">
        <el-table-column type="index" width="50" />

        <el-table-column label="员工" width="150">
          <template #default="{ row }">
            <div class="employee-cell">
              <el-avatar :size="24" :icon="User" />
              <span>{{ row.employee_name || row.employee_id }}</span>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="开始时间" width="160">
          <template #default="{ row }">
            {{ formatDateTime(row.start_time) }}
          </template>
        </el-table-column>

        <el-table-column label="结束时间" width="160">
          <template #default="{ row }">
            {{ formatDateTime(row.end_time) }}
          </template>
        </el-table-column>

        <el-table-column label="软件名称" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">
            <el-tag size="small" effect="dark" type="primary">
              {{ row.app_name }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="窗口标题" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            {{ row.window_title || "-" }}
          </template>
        </el-table-column>

        <el-table-column label="使用时长" width="120" align="center">
          <template #default="{ row }">
            <span class="duration-badge">
              {{ formatDuration(row.duration) }}
            </span>
          </template>
        </el-table-column>

        <el-table-column label="前台" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="row.is_foreground ? 'success' : 'info'" size="small">
              {{ row.is_foreground ? "是" : "否" }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="CPU" width="80" align="center">
          <template #default="{ row }"> {{ row.cpu_avg || 0 }}% </template>
        </el-table-column>

        <el-table-column label="内存" width="100" align="center">
          <template #default="{ row }"> {{ row.memory_avg || 0 }}MB </template>
        </el-table-column>

        <el-table-column label="客户端" width="150">
          <template #default="{ row }">
            {{ row.computer_name || "-" }}
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="pagination">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[20, 50, 100, 200]"
          :total="total"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch } from "vue";
import { ElMessage } from "element-plus";
import {
  Search,
  Refresh,
  Grid,
  Timer,
  Cpu,
  Memo,
  User,
} from "@element-plus/icons-vue";
import * as echarts from "echarts";
import api from "./admin_api";
import { formatDateTime, formatDuration } from "./admin_timezone";

const loading = ref(false);
const items = ref([]);
const total = ref(0);
const currentPage = ref(1);
const pageSize = ref(20);
const employees = ref([]);
const barChartRef = ref(null);
const trendChartRef = ref(null);
let barChart = null;
let trendChart = null;
const trendType = ref("hourly");

const stats = ref({
  totalApps: 0,
  totalDuration: 0,
  avgCpu: 0,
  avgMemory: 0,
});

const filters = ref({
  employeeId: "",
  appName: "",
  dateRange: [],
  foregroundOnly: false,
});

// 加载员工列表
const loadEmployees = async () => {
  try {
    const response = await api.get("/employees", { params: { limit: 1000 } });
    employees.value = response.items || [];
  } catch (error) {
    console.error("加载员工失败:", error);
  }
};

// 加载数据
const loadData = async () => {
  loading.value = true;
  try {
    const params = {
      skip: (currentPage.value - 1) * pageSize.value,
      limit: pageSize.value,
    };

    if (filters.value.employeeId) {
      params.employee_id = filters.value.employeeId;
    }

    if (filters.value.appName) {
      params.app_name = filters.value.appName;
    }

    if (filters.value.dateRange && filters.value.dateRange.length === 2) {
      params.start_date = filters.value.dateRange[0];
      params.end_date = filters.value.dateRange[1];
    }

    if (filters.value.foregroundOnly) {
      params.foreground_only = true;
    }

    const response = await api.get("/apps/usage", { params });
    items.value = response.items || [];
    total.value = response.total || 0;

    // 加载统计
    await loadStats();

    // 渲染图表
    renderCharts();
  } catch (error) {
    console.error("加载软件使用失败:", error);
    ElMessage.error("加载失败");
  } finally {
    loading.value = false;
  }
};

// 加载统计
const loadStats = async () => {
  const uniqueApps = new Set(items.value.map((i) => i.app_name));
  stats.value.totalApps = uniqueApps.size;
  stats.value.totalDuration = items.value.reduce(
    (sum, item) => sum + (item.duration || 0),
    0,
  );

  const cpuSum = items.value.reduce(
    (sum, item) => sum + (item.cpu_avg || 0),
    0,
  );
  stats.value.avgCpu = items.value.length
    ? Math.round(cpuSum / items.value.length)
    : 0;

  const memorySum = items.value.reduce(
    (sum, item) => sum + (item.memory_avg || 0),
    0,
  );
  stats.value.avgMemory = items.value.length
    ? Math.round(memorySum / items.value.length)
    : 0;
};

// 渲染图表
const renderCharts = () => {
  if (!barChartRef.value || !trendChartRef.value) return;

  // 软件使用TOP10柱状图
  if (!barChart) {
    barChart = echarts.init(barChartRef.value);
  }

  const appDuration = {};
  items.value.forEach((item) => {
    const app = item.app_name;
    appDuration[app] = (appDuration[app] || 0) + (item.duration || 0);
  });

  const sortedApps = Object.entries(appDuration)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10);

  const barOption = {
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      formatter: (params) => {
        const data = params[0];
        return `${data.name}<br/>使用时长: ${formatDuration(data.value)}`;
      },
    },
    grid: { left: "3%", right: "4%", bottom: "3%", containLabel: true },
    xAxis: {
      type: "value",
      name: "使用时长(分钟)",
      axisLabel: {
        formatter: (value) => Math.round(value / 60) + "分钟",
      },
    },
    yAxis: {
      type: "category",
      data: sortedApps.map(([name]) =>
        name.length > 15 ? name.substring(0, 15) + "..." : name,
      ),
    },
    series: [
      {
        name: "使用时长",
        type: "bar",
        data: sortedApps.map(([, value]) => Math.round(value / 60)),
        itemStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
            { offset: 0, color: "#667eea" },
            { offset: 1, color: "#764ba2" },
          ]),
          borderRadius: [0, 4, 4, 0],
        },
        label: {
          show: true,
          position: "right",
          formatter: (params) => formatDuration(params.value * 60),
        },
      },
    ],
  };
  barChart.setOption(barOption);

  // 趋势图
  if (!trendChart) {
    trendChart = echarts.init(trendChartRef.value);
  }

  const hours = Array.from({ length: 24 }, (_, i) => `${i}时`);
  const hourlyDuration = new Array(24).fill(0);

  items.value.forEach((item) => {
    if (item.start_time) {
      const hour = new Date(item.start_time).getHours();
      hourlyDuration[hour] += (item.duration || 0) / 60; // 转换为分钟
    }
  });

  const trendOption = {
    tooltip: {
      trigger: "axis",
      formatter: (params) => {
        return `${params[0].name}<br/>使用时长: ${formatDuration(params[0].value * 60)}`;
      },
    },
    grid: { left: "3%", right: "4%", bottom: "3%", containLabel: true },
    xAxis: {
      type: "category",
      data: trendType.value === "hourly" ? hours : ["近7天"],
      axisLabel: { rotate: 45 },
    },
    yAxis: {
      type: "value",
      name: "使用时长(分钟)",
      axisLabel: {
        formatter: (value) => Math.round(value) + "分钟",
      },
    },
    series: [
      {
        name: "使用时长",
        type: "line",
        data:
          trendType.value === "hourly"
            ? hourlyDuration
            : [stats.value.totalDuration / 60],
        smooth: true,
        lineStyle: { color: "#667eea", width: 3 },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: "rgba(102, 126, 234, 0.3)" },
            { offset: 1, color: "rgba(102, 126, 234, 0.1)" },
          ]),
        },
      },
    ],
  };
  trendChart.setOption(trendOption);
};

// 筛选变化
const handleFilterChange = () => {
  currentPage.value = 1;
  loadData();
};

// 搜索（防抖）
let searchTimer;
const handleSearch = () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    currentPage.value = 1;
    loadData();
  }, 300);
};

// 重置筛选
const resetFilters = () => {
  filters.value = {
    employeeId: "",
    appName: "",
    dateRange: [],
    foregroundOnly: false,
  };
  currentPage.value = 1;
  loadData();
};

// 分页
const handleSizeChange = (val) => {
  pageSize.value = val;
  currentPage.value = 1;
  loadData();
};

const handleCurrentChange = (val) => {
  currentPage.value = val;
  loadData();
};

// 窗口大小变化
const handleResize = () => {
  barChart?.resize();
  trendChart?.resize();
};

onMounted(() => {
  loadEmployees();
  loadData();
  window.addEventListener("resize", handleResize);
});

onUnmounted(() => {
  window.removeEventListener("resize", handleResize);
  barChart?.dispose();
  trendChart?.dispose();
});
</script>

<style scoped>
.apps-monitor {
  padding: 20px;
}

.filter-bar {
  margin-bottom: 20px;
}

.stats-row {
  margin-bottom: 20px;
}

.stat-card {
  height: 100%;
}

.stat-content {
  display: flex;
  align-items: center;
  gap: 16px;
}

.stat-icon {
  width: 56px;
  height: 56px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.stat-icon .el-icon {
  font-size: 24px;
}

.stat-info {
  flex: 1;
}

.stat-value {
  font-size: 24px;
  font-weight: bold;
  color: #333;
  line-height: 1.2;
  margin-bottom: 4px;
}

.stat-label {
  font-size: 14px;
  color: #999;
}

.chart-row {
  margin-bottom: 20px;
}

.chart-card {
  height: 100%;
}

.chart-container {
  height: 300px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.table-card {
  margin-top: 20px;
}

.employee-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.duration-badge {
  background: #f0f9ff;
  color: #1890ff;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
}

.pagination {
  margin-top: 20px;
  text-align: right;
}

.text-right {
  text-align: right;
}
</style>
