<template>
  <div class="stats">
    <!-- 时间范围选择 -->
    <el-card class="filter-bar" shadow="hover">
      <el-row :gutter="20" align="middle">
        <el-col :span="8">
          <el-radio-group v-model="timeRange" @change="loadStats">
            <el-radio-button label="today">今日</el-radio-button>
            <el-radio-button label="week">本周</el-radio-button>
            <el-radio-button label="month">本月</el-radio-button>
            <el-radio-button label="custom">自定义</el-radio-button>
          </el-radio-group>
        </el-col>

        <el-col v-if="timeRange === 'custom'" :span="12">
          <el-date-picker
            v-model="customRange"
            type="daterange"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
            @change="loadStats"
          />
        </el-col>

        <el-col :span="4" class="text-right">
          <el-button @click="exportData">
            <el-icon><Download /></el-icon>导出报表
          </el-button>
        </el-col>
      </el-row>
    </el-card>

    <!-- 关键指标 -->
    <el-row :gutter="20" class="kpi-row">
      <el-col :span="6" v-for="kpi in kpiData" :key="kpi.label">
        <el-card class="kpi-card" shadow="hover">
          <div class="kpi-content">
            <div class="kpi-icon" :style="{ background: kpi.bgColor }">
              <el-icon :size="24" :color="kpi.color"
                ><component :is="kpi.icon"
              /></el-icon>
            </div>
            <div class="kpi-info">
              <div class="kpi-value">{{ kpi.value }}</div>
              <div class="kpi-label">{{ kpi.label }}</div>
              <div class="kpi-trend" :class="kpi.trend">
                {{ kpi.trendValue }}
              </div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 图表区域 -->
    <el-row :gutter="20" class="chart-row">
      <el-col :span="16">
        <el-card class="chart-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <span>截图趋势</span>
              <el-radio-group v-model="trendType" size="small">
                <el-radio-button label="daily">按天</el-radio-button>
                <el-radio-button label="hourly">按小时</el-radio-button>
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
              <span>员工排行</span>
              <el-select
                v-model="rankType"
                size="small"
                @change="loadEmployeeRank"
              >
                <el-option label="今日截图" value="today" />
                <el-option label="总截图" value="total" />
              </el-select>
            </div>
          </template>
          <div class="rank-list" v-loading="rankLoading">
            <div
              v-for="(emp, index) in employeeRank"
              :key="emp.id"
              class="rank-item"
            >
              <div class="rank-number" :class="{ 'top-3': index < 3 }">
                {{ index + 1 }}
              </div>
              <div class="rank-info">
                <div class="rank-name">{{ emp.name }}</div>
                <div class="rank-id">{{ emp.id }}</div>
              </div>
              <div class="rank-value">{{ emp.value }}</div>
            </div>
            <el-empty v-if="employeeRank.length === 0" description="暂无数据" />
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 详细统计表格 -->
    <el-row :gutter="20" class="table-row">
      <el-col :span="12">
        <el-card class="table-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <span>员工统计详情</span>
            </div>
          </template>
          <el-table :data="employeeStats" stripe height="400">
            <el-table-column prop="name" label="员工" min-width="150" />
            <el-table-column
              prop="today"
              label="今日截图"
              width="100"
              align="center"
            />
            <el-table-column
              prop="week"
              label="本周截图"
              width="100"
              align="center"
            />
            <el-table-column
              prop="month"
              label="本月截图"
              width="100"
              align="center"
            />
            <el-table-column
              prop="total"
              label="总计"
              width="100"
              align="center"
            />
          </el-table>
        </el-card>
      </el-col>

      <el-col :span="12">
        <el-card class="table-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <span>客户端统计</span>
            </div>
          </template>
          <el-table :data="clientStats" stripe height="400">
            <el-table-column prop="version" label="版本" width="120" />
            <el-table-column
              prop="total"
              label="总数"
              width="80"
              align="center"
            />
            <el-table-column
              prop="online"
              label="在线"
              width="80"
              align="center"
            />
            <el-table-column
              prop="offline"
              label="离线"
              width="80"
              align="center"
            />
            <el-table-column
              prop="last_seen"
              label="最后活跃"
              min-width="150"
            />
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <!-- 存储分析 -->
    <el-row :gutter="20" class="storage-row">
      <el-col :span="24">
        <el-card class="storage-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <span>存储分析</span>
            </div>
          </template>

          <el-row :gutter="40">
            <el-col :span="8">
              <div class="storage-chart" ref="storageChartRef"></div>
            </el-col>

            <el-col :span="16">
              <el-descriptions :column="3" border>
                <el-descriptions-item label="总存储空间">
                  <span class="storage-value">{{ storageStats.total }} GB</span>
                </el-descriptions-item>
                <el-descriptions-item label="已使用">
                  <span class="storage-value">{{ storageStats.used }} GB</span>
                </el-descriptions-item>
                <el-descriptions-item label="剩余空间">
                  <span class="storage-value">{{ storageStats.free }} GB</span>
                </el-descriptions-item>
                <el-descriptions-item label="今日新增">
                  <span class="storage-value">{{ storageStats.today }} MB</span>
                </el-descriptions-item>
                <el-descriptions-item label="本周新增">
                  <span class="storage-value">{{ storageStats.week }} MB</span>
                </el-descriptions-item>
                <el-descriptions-item label="平均截图大小">
                  <span class="storage-value"
                    >{{ storageStats.avgSize }} KB</span
                  >
                </el-descriptions-item>
              </el-descriptions>
            </el-col>
          </el-row>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch } from "vue";
import { Download } from "@element-plus/icons-vue";
import * as echarts from "echarts";
import { statsApi, employeeApi, clientApi } from "./admin_api";
import { ElMessage } from "element-plus";

const trendChartRef = ref(null);
const storageChartRef = ref(null);
let trendChart = null;
let storageChart = null;

const timeRange = ref("today");
const customRange = ref([]);
const trendType = ref("hourly");
const rankType = ref("today");
const rankLoading = ref(false);

// KPI数据
const kpiData = ref([
  {
    label: "截图总数",
    value: 0,
    icon: "Picture",
    bgColor: "#e6f7ff",
    color: "#1890ff",
    trend: "",
    trendValue: "",
  },
  {
    label: "活跃员工",
    value: 0,
    icon: "User",
    bgColor: "#f6ffed",
    color: "#52c41a",
    trend: "",
    trendValue: "",
  },
  {
    label: "在线客户端",
    value: 0,
    icon: "Monitor",
    bgColor: "#fff7e6",
    color: "#fa8c16",
    trend: "",
    trendValue: "",
  },
  {
    label: "存储使用",
    value: "0 MB",
    icon: "DataLine",
    bgColor: "#f9f0ff",
    color: "#722ed1",
    trend: "",
    trendValue: "",
  },
]);

const employeeRank = ref([]);
const employeeStats = ref([]);
const clientStats = ref([]);
const storageStats = ref({
  total: 0,
  used: 0,
  free: 0,
  today: 0,
  week: 0,
  avgSize: 0,
});

// 加载统计数据
const loadStats = async () => {
  try {
    const data = await statsApi.getStats();

    // 更新KPI
    kpiData.value[0].value = data.total;
    kpiData.value[1].value = data.employees;
    kpiData.value[2].value = data.online;
    kpiData.value[3].value = data.storage_mb + " MB";

    // 渲染图表
    renderTrendChart(data.hourly);
    renderStorageChart(data.image_formats);

    // 更新存储统计
    storageStats.value.used = data.storage_mb / 1024;
    storageStats.value.today = data.today;
    storageStats.value.avgSize = (data.storage_mb / (data.total || 1)) * 1024;
  } catch (error) {
    console.error("加载统计数据失败:", error);
  }
};

// 加载员工排行
// 加载员工排行（使用统一响应处理）
const loadEmployeeRank = async () => {
  rankLoading.value = true;
  try {
    // ✅ 调用修改后的API，返回统一格式
    const response = await employeeApi.getEmployees({ limit: 100 });

    // ✅ 直接使用标准化的 items
    const employees = response.items || [];

    employeeRank.value = employees
      .map((emp) => ({
        id: emp.id || emp.employee_id,
        name: emp.name,
        value:
          rankType.value === "today"
            ? emp.today_screenshots || 0
            : emp.total_screenshots || 0,
      }))
      .sort((a, b) => b.value - a.value)
      .slice(0, 10);
  } catch (error) {
    console.error("加载员工排行失败:", error);
    ElMessage.error(
      "加载员工排行失败: " + (error.response?.data?.detail || error.message),
    );
    employeeRank.value = [];
  } finally {
    rankLoading.value = false;
  }
};

// 加载员工统计
// 加载员工统计
const loadEmployeeStats = async () => {
  try {
    const response = await employeeApi.getEmployees({ limit: 1000 });

    // ✅ 修复：正确处理标准化响应
    const employees = response.items || [];

    employeeStats.value = employees.map((emp) => ({
      name: emp.name,
      today: emp.today_screenshots || 0,
      week: emp.week_screenshots || 0,
      month: emp.month_screenshots || 0,
      total: emp.total_screenshots || 0,
    }));
  } catch (error) {
    console.error("加载员工统计失败:", error);
    employeeStats.value = []; // 设置为空数组避免错误
  }
};

// 加载客户端统计
// 加载客户端统计
const loadClientStats = async () => {
  try {
    const response = await clientApi.getClients({ limit: 1000 });

    // ✅ 修复：正确处理标准化响应
    const clients = response.items || [];

    // 按版本分组
    const versionMap = new Map();
    clients.forEach((c) => {
      const version = c.client_version || "未知";
      if (!versionMap.has(version)) {
        versionMap.set(version, {
          version,
          total: 0,
          online: 0,
          offline: 0,
          last_seen: null,
        });
      }
      const stats = versionMap.get(version);
      stats.total++;
      if (c.is_online) {
        stats.online++;
      } else {
        stats.offline++;
      }
      if (c.last_seen && (!stats.last_seen || c.last_seen > stats.last_seen)) {
        stats.last_seen = c.last_seen;
      }
    });

    clientStats.value = Array.from(versionMap.values());
  } catch (error) {
    console.error("加载客户端统计失败:", error);
    clientStats.value = []; // 设置为空数组避免错误
  }
};

// 渲染趋势图表
const renderTrendChart = (data) => {
  if (!trendChartRef.value) return;

  if (!trendChart) {
    trendChart = echarts.init(trendChartRef.value);
  }

  const option = {
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
    },
    grid: {
      left: "3%",
      right: "4%",
      bottom: "3%",
      containLabel: true,
    },
    xAxis: {
      type: "category",
      data:
        trendType.value === "hourly"
          ? Array.from({ length: 24 }, (_, i) => i + "时")
          : Array.from({ length: 7 }, (_, i) => {
              const d = new Date();
              d.setDate(d.getDate() - i);
              return d.getDate() + "日";
            }).reverse(),
      axisLabel: { rotate: 45 },
    },
    yAxis: {
      type: "value",
      name: "截图数量",
    },
    series: [
      {
        name: "截图数",
        type: "bar",
        data: data,
        itemStyle: {
          color: "#667eea",
          borderRadius: [4, 4, 0, 0],
        },
      },
    ],
  };

  trendChart.setOption(option);
};

// 渲染存储图表
const renderStorageChart = (data) => {
  if (!storageChartRef.value) return;

  if (!storageChart) {
    storageChart = echarts.init(storageChartRef.value);
  }

  const option = {
    tooltip: {
      trigger: "item",
      formatter: "{b}: {c} ({d}%)",
    },
    legend: {
      orient: "vertical",
      left: "left",
    },
    series: [
      {
        name: "存储占比",
        type: "pie",
        radius: ["50%", "70%"],
        avoidLabelOverlap: false,
        label: { show: false },
        emphasis: {
          label: { show: true },
        },
        data: [
          { value: data.webp, name: "WebP" },
          { value: data.jpg, name: "JPG" },
          { value: data.other, name: "其他" },
        ],
      },
    ],
  };

  storageChart.setOption(option);
};

// 导出数据
const exportData = () => {
  ElMessage.success("导出功能开发中...");
};

// 窗口大小变化自适应
const handleResize = () => {
  trendChart?.resize();
  storageChart?.resize();
};

watch(trendType, () => {
  if (trendChart) {
    const data = trendChart.getOption().series[0].data;
    renderTrendChart(data);
  }
});

onMounted(() => {
  loadStats();
  loadEmployeeRank();
  loadEmployeeStats();
  loadClientStats();

  window.addEventListener("resize", handleResize);

  // 定时刷新
  const timer = setInterval(loadStats, 60000);

  onUnmounted(() => {
    clearInterval(timer);
    window.removeEventListener("resize", handleResize);
    trendChart?.dispose();
    storageChart?.dispose();
  });
});
</script>

<style scoped>
.stats {
  padding: 20px;
}

.filter-bar {
  margin-bottom: 20px;
}

.kpi-row {
  margin-bottom: 20px;
}

.kpi-card {
  height: 100%;
}

.kpi-content {
  display: flex;
  align-items: center;
  gap: 16px;
}

.kpi-icon {
  width: 56px;
  height: 56px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.kpi-info {
  flex: 1;
}

.kpi-value {
  font-size: 28px;
  font-weight: bold;
  color: #333;
  line-height: 1.2;
  margin-bottom: 4px;
}

.kpi-label {
  font-size: 14px;
  color: #999;
  margin-bottom: 4px;
}

.kpi-trend {
  font-size: 12px;
}

.kpi-trend.up {
  color: #52c41a;
}

.kpi-trend.down {
  color: #ff4d4f;
}

.chart-row {
  margin-bottom: 20px;
}

.chart-card {
  height: 100%;
}

.chart-container {
  height: 350px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.rank-list {
  height: 350px;
  overflow-y: auto;
  padding: 0 10px;
}

.rank-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px;
  border-bottom: 1px solid #f0f0f0;
  transition: background 0.3s;
}

.rank-item:hover {
  background: #f5f5f5;
}

.rank-number {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: #f0f0f0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 500;
  color: #666;
}

.rank-number.top-3 {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}

.rank-info {
  flex: 1;
}

.rank-name {
  font-weight: 500;
  color: #333;
  margin-bottom: 2px;
}

.rank-id {
  font-size: 12px;
  color: #999;
}

.rank-value {
  font-size: 16px;
  font-weight: 500;
  color: #667eea;
}

.table-row {
  margin-bottom: 20px;
}

.table-card {
  height: 100%;
}

.storage-row {
  margin-top: 20px;
}

.storage-card {
  height: 100%;
}

.storage-chart {
  height: 200px;
}

.storage-value {
  font-size: 16px;
  font-weight: 500;
  color: #333;
}

.text-right {
  text-align: right;
}
</style>
