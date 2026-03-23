<!-- admin_Browser.vue -->
<template>
  <div class="browser-monitor">
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

        <!-- admin_Browser.vue - 优化浏览器筛选选项 -->
        <el-col :span="4">
          <el-select
            v-model="filters.browser"
            placeholder="浏览器"
            clearable
            @change="handleFilterChange"
          >
            <el-option label="Chrome" value="chrome" />
            <el-option label="Edge" value="edge" />
            <el-option label="Firefox" value="firefox" />
            <el-option label="Brave" value="brave" />
            <el-option label="Opera" value="opera" />
            <el-option label="Safari" value="safari" />
            <el-option label="其他" value="other" />
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
            @change="handleFilterChange"
          />
        </el-col>

        <el-col :span="5">
          <el-input
            v-model="filters.search"
            placeholder="搜索网址/标题"
            :prefix-icon="Search"
            clearable
            @input="handleSearch"
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
              <el-icon><Monitor /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ stats.totalVisits }}</div>
              <div class="stat-label">总访问次数</div>
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
              <div class="stat-label">总浏览时长</div>
            </div>
          </div>
        </el-card>
      </el-col>

      <el-col :span="6">
        <el-card class="stat-card" shadow="hover">
          <div class="stat-content">
            <div class="stat-icon" style="background: #fff7e6; color: #fa8c16">
              <el-icon><Platform /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ stats.avgPerVisit }}秒</div>
              <div class="stat-label">平均停留</div>
            </div>
          </div>
        </el-card>
      </el-col>

      <el-col :span="6">
        <el-card class="stat-card" shadow="hover">
          <div class="stat-content">
            <div class="stat-icon" style="background: #f9f0ff; color: #722ed1">
              <el-icon><ChromeFilled /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ stats.activeBrowsers }}</div>
              <div class="stat-label">活跃浏览器</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 浏览器分布图 -->
    <el-row :gutter="20" class="chart-row">
      <el-col :span="16">
        <el-card class="chart-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <span>访问趋势</span>
              <el-radio-group v-model="trendType" size="small">
                <el-radio-button label="hourly">按小时</el-radio-button>
                <el-radio-button label="daily">按天</el-radio-button>
              </el-radio-group>
            </div>
          </template>
          <div class="chart-container" ref="trendChartRef"></div>
        </el-card>
      </el-col>

      <el-col :span="8">
        <el-card class="chart-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <span>浏览器占比</span>
            </div>
          </template>
          <div class="chart-container" ref="pieChartRef"></div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 访问列表 -->
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

        <el-table-column label="访问时间" width="160">
          <template #default="{ row }">
            {{ formatDateTime(row.visit_time) }}
          </template>
        </el-table-column>

        <el-table-column label="浏览器" width="100">
          <template #default="{ row }">
            <el-tag :type="getBrowserType(row.browser)" size="small">
              {{ row.browser }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="标题" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            {{ row.title || "-" }}
          </template>
        </el-table-column>

        <el-table-column label="网址" min-width="300" show-overflow-tooltip>
          <template #default="{ row }">
            <a :href="row.url" target="_blank" class="url-link">
              <el-icon><Link /></el-icon>
              {{ truncateUrl(row.url) }}
            </a>
          </template>
        </el-table-column>

        <el-table-column label="停留时长" width="120" align="center">
          <template #default="{ row }">
            <span class="duration-badge">
              {{ formatDuration(row.duration) }}
            </span>
          </template>
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
import { ref, onMounted, onUnmounted, watch, computed } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import {
  Search,
  Refresh,
  Monitor,
  Timer,
  Platform,
  ChromeFilled,
  User,
  Link,
} from "@element-plus/icons-vue";
import * as echarts from "echarts";
import api from "./admin_api";
import { formatDateTime, formatDuration } from "./admin_timezone";

const router = useRouter();
const loading = ref(false);
const items = ref([]);
const total = ref(0);
const currentPage = ref(1);
const pageSize = ref(20);
const employees = ref([]);
const trendChartRef = ref(null);
const pieChartRef = ref(null);
let trendChart = null;
let pieChart = null;
const trendType = ref("hourly");

const stats = ref({
  totalVisits: 0,
  totalDuration: 0,
  avgPerVisit: 0,
  activeBrowsers: 0,
});

const filters = ref({
  employeeId: "",
  browser: "",
  dateRange: [],
  search: "",
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

// 获取浏览器类型样式
const getBrowserType = (browser) => {
  const map = {
    chrome: "primary",
    edge: "success",
    firefox: "warning",
  };
  return map[browser?.toLowerCase()] || "info";
};

// 截断URL
const truncateUrl = (url) => {
  if (!url) return "-";
  if (url.length > 60) {
    return url.substring(0, 40) + "..." + url.substring(url.length - 20);
  }
  return url;
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

    if (filters.value.browser) {
      params.browser = filters.value.browser;
    }

    if (filters.value.dateRange && filters.value.dateRange.length === 2) {
      params.start_date = filters.value.dateRange[0];
      params.end_date = filters.value.dateRange[1];
    }

    if (filters.value.search) {
      params.search = filters.value.search;
    }

    const response = await api.get("/browser/history", { params });
    items.value = response.items || [];
    total.value = response.total || 0;

    // 加载统计
    await loadStats();

    // 渲染图表
    renderCharts();
  } catch (error) {
    console.error("加载浏览器历史失败:", error);
    ElMessage.error("加载失败");
  } finally {
    loading.value = false;
  }
};

// 加载统计
const loadStats = async () => {
  try {
    const params = {};
    if (filters.value.employeeId) {
      params.employee_id = filters.value.employeeId;
    }
    if (filters.value.dateRange && filters.value.dateRange.length === 2) {
      params.start_date = filters.value.dateRange[0];
      params.end_date = filters.value.dateRange[1];
    }

    const response = await api.get("/browser/stats", { params });

    stats.value.totalVisits = items.value.length;
    stats.value.totalDuration = items.value.reduce(
      (sum, item) => sum + (item.duration || 0),
      0,
    );
    stats.value.avgPerVisit = items.value.length
      ? Math.round(stats.value.totalDuration / items.value.length)
      : 0;

    const browsers = new Set(items.value.map((i) => i.browser));
    stats.value.activeBrowsers = browsers.size;
  } catch (error) {
    console.error("加载统计失败:", error);
  }
};

// 渲染图表
const renderCharts = () => {
  if (!trendChartRef.value || !pieChartRef.value) return;

  // 趋势图
  if (!trendChart) {
    trendChart = echarts.init(trendChartRef.value);
  }

  const hours = Array.from({ length: 24 }, (_, i) => `${i}时`);
  const hourlyData = new Array(24).fill(0);

  items.value.forEach((item) => {
    if (item.visit_time) {
      const hour = new Date(item.visit_time).getHours();
      hourlyData[hour]++;
    }
  });

  const trendOption = {
    tooltip: { trigger: "axis" },
    grid: { left: "3%", right: "4%", bottom: "3%", containLabel: true },
    xAxis: {
      type: "category",
      data: trendType.value === "hourly" ? hours : ["近7天"],
      axisLabel: { rotate: 45 },
    },
    yAxis: { type: "value", name: "访问次数" },
    series: [
      {
        name: "访问次数",
        type: "bar",
        data: trendType.value === "hourly" ? hourlyData : [items.value.length],
        itemStyle: { color: "#667eea", borderRadius: [4, 4, 0, 0] },
      },
    ],
  };
  trendChart.setOption(trendOption);

  // 饼图
  if (!pieChart) {
    pieChart = echarts.init(pieChartRef.value);
  }

  const browserCount = {};
  items.value.forEach((item) => {
    const browser = item.browser || "unknown";
    browserCount[browser] = (browserCount[browser] || 0) + 1;
  });

  const pieData = Object.entries(browserCount).map(([name, value]) => ({
    name,
    value,
  }));

  const pieOption = {
    tooltip: { trigger: "item", formatter: "{b}: {c} ({d}%)" },
    legend: { orient: "vertical", left: "left" },
    series: [
      {
        type: "pie",
        radius: ["50%", "70%"],
        avoidLabelOverlap: false,
        label: { show: false },
        emphasis: { label: { show: true } },
        data: pieData,
      },
    ],
  };
  pieChart.setOption(pieOption);
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
    browser: "",
    dateRange: [],
    search: "",
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
  trendChart?.resize();
  pieChart?.resize();
};

onMounted(() => {
  loadEmployees();
  loadData();
  window.addEventListener("resize", handleResize);
});

onUnmounted(() => {
  window.removeEventListener("resize", handleResize);
  trendChart?.dispose();
  pieChart?.dispose();
});
</script>

<style scoped>
.browser-monitor {
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

.url-link {
  display: flex;
  align-items: center;
  gap: 4px;
  color: #409eff;
  text-decoration: none;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.url-link:hover {
  text-decoration: underline;
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
