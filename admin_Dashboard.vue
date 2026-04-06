<template>
  <div class="dashboard">
    <!-- 统计卡片 -->
    <el-row :gutter="20" class="stats-row">
      <el-col :xs="24" :sm="12" :md="6" v-for="stat in stats" :key="stat.label">
        <el-card
          class="stat-card"
          :body-style="{ padding: '20px' }"
          shadow="hover"
        >
          <div class="stat-content">
            <div class="stat-icon" :style="{ background: stat.bgColor }">
              <el-icon :size="24" :color="stat.color"
                ><component :is="stat.icon"
              /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ stat.value }}</div>
              <div class="stat-label">{{ stat.label }}</div>
              <div
                v-if="stat.trend"
                class="stat-trend"
                :class="stat.trend.type"
              >
                <el-icon
                  ><ArrowUp v-if="stat.trend.type === 'up'" /><ArrowDown v-else
                /></el-icon>
                {{ stat.trend.value }} 较昨日
              </div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 图表区域 -->
    <el-row :gutter="20" class="chart-row">
      <el-col :xs="24" :lg="16">
        <el-card class="chart-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <span>每小时活动分布</span>
              <el-radio-group v-model="chartType" size="small">
                <el-radio-button label="bar">柱状图</el-radio-button>
                <el-radio-button label="line">折线图</el-radio-button>
              </el-radio-group>
            </div>
          </template>
          <div class="chart-container" ref="hourlyChartRef"></div>
        </el-card>
      </el-col>

      <el-col :xs="24" :lg="8">
        <el-card class="chart-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <span>图片格式占比</span>
            </div>
          </template>
          <div class="chart-container" ref="formatChartRef"></div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 最近活动和TOP员工 -->
    <el-row :gutter="20" class="activity-row">
      <el-col :xs="24" :lg="12">
        <el-card class="activity-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <span>最近活动</span>
              <el-button link @click="refreshActivities">
                <el-icon><Refresh /></el-icon>
              </el-button>
            </div>
          </template>
          <div class="activity-list" v-loading="activitiesLoading">
            <div
              v-for="act in recentActivities"
              :key="act.time"
              class="activity-item"
            >
              <el-avatar
                :size="32"
                :icon="act.action === 'screenshot' ? Camera : User"
              />
              <div class="activity-content">
                <div class="activity-title">
                  <span class="employee">{{
                    act.employee_name || act.employee_id
                  }}</span>
                  <span class="action">{{ act.action }}</span>
                </div>
                <div class="activity-time">{{ act.time }}</div>
              </div>
            </div>
            <el-empty
              v-if="recentActivities.length === 0"
              description="暂无活动"
            />
          </div>
        </el-card>
      </el-col>

      <el-col :xs="24" :lg="12">
        <el-card class="activity-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <span>活跃员工TOP5</span>
            </div>
          </template>
          <el-table
            :data="topEmployees"
            style="width: 100%"
            :show-header="false"
          >
            <el-table-column width="50">
              <template #default="{ $index }">
                <el-tag :type="$index < 3 ? 'success' : 'info'" size="small">
                  {{ $index + 1 }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="name" label="员工" />
            <el-table-column
              prop="today"
              label="今日"
              width="80"
              align="center"
            />
            <el-table-column
              prop="total"
              label="总计"
              width="80"
              align="center"
            />
            <el-table-column width="100">
              <template #default="{ row }">
                <el-button link type="primary" @click="viewEmployee(row.id)">
                  查看
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <!-- 清理状态卡片 -->
    <el-card v-if="cleanupStatus" class="cleanup-card" shadow="hover">
      <template #header>
        <div class="card-header">
          <span>自动清理状态</span>
          <el-tag
            :type="cleanupStatus.enabled ? 'success' : 'info'"
            size="small"
          >
            {{ cleanupStatus.enabled ? "已启用" : "已禁用" }}
          </el-tag>
        </div>
      </template>
      <el-row :gutter="20">
        <el-col :span="6">
          <div class="cleanup-item">
            <div class="label">保留时间</div>
            <div class="value">{{ cleanupStatus.retention_hours }}小时</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="cleanup-item">
            <div class="label">清理间隔</div>
            <div class="value">{{ cleanupStatus.interval_hours }}小时</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="cleanup-item">
            <div class="label">待清理</div>
            <div class="value">{{ cleanupStatus.pending_cleanup }}张</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="cleanup-item">
            <div class="label">待清理大小</div>
            <div class="value">{{ cleanupStatus.pending_size_mb }}MB</div>
          </div>
        </el-col>
      </el-row>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { useUserStore } from "./admin_stores";
import {
  Camera,
  User,
  ArrowUp,
  ArrowDown,
  Refresh,
  Document,
  Picture,
  Monitor,
  Clock,
} from "@element-plus/icons-vue";
import * as echarts from "echarts";
import { statsApi, cleanupApi } from "./admin_api";

const userStore = useUserStore();
const router = useRouter();
const hourlyChartRef = ref(null);
const formatChartRef = ref(null);
let hourlyChart = null;
let formatChart = null;

const chartType = ref("bar");
const activitiesLoading = ref(false);
const recentActivities = ref([]);
const topEmployees = ref([]);
const cleanupStatus = ref(null);

const stats = ref([
  {
    label: "今日截图",
    value: 0,
    icon: "Document",
    bgColor: "#e6f7ff",
    color: "#1890ff",
    trend: null,
  },
  {
    label: "在线员工",
    value: 0,
    icon: "User",
    bgColor: "#f6ffed",
    color: "#52c41a",
    trend: null,
  },
  {
    label: "累计截图",
    value: 0,
    icon: "Picture",
    bgColor: "#fff7e6",
    color: "#fa8c16",
    trend: null,
  },
  {
    label: "客户端数",
    value: 0,
    icon: "Monitor",
    bgColor: "#f9f0ff",
    color: "#722ed1",
    trend: null,
  },
]);

// 加载统计数据
const loadStats = async () => {
  try {
    const data = await statsApi.getStats();

    stats.value[0].value = data.today;
    stats.value[1].value = data.online;
    stats.value[2].value = data.total;
    stats.value[3].value = data.clients;

    // 添加趋势
    if (data.today > data.yesterday) {
      stats.value[0].trend = { type: "up", value: data.today - data.yesterday };
    } else if (data.today < data.yesterday) {
      stats.value[0].trend = {
        type: "down",
        value: data.yesterday - data.today,
      };
    }

    // 确保数据结构正确
    recentActivities.value = data.recent_activities || [];

    topEmployees.value = data.top_employees || [];

    // 渲染图表
    if (data.hourly) {
      renderHourlyChart(data.hourly);
    }
    if (data.image_formats) {
      renderFormatChart(data.image_formats);
    }
  } catch (error) {
    console.error("加载统计数据失败:", error);
  }
};

// 加载清理状态
const loadCleanupStatus = async () => {
  // ✅ 只有管理员或拥有 settings:view 权限的用户才加载清理状态
  if (!userStore.hasPermission("settings:view")) {
    return;
  }

  try {
    cleanupStatus.value = await cleanupApi.getCleanupStatus();
  } catch (error) {
    console.error("加载清理状态失败:", error);
  }
};

// 渲染每小时图表
const renderHourlyChart = (data) => {
  if (!hourlyChartRef.value) return;

  if (!hourlyChart) {
    hourlyChart = echarts.init(hourlyChartRef.value);
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
      data: Array.from({ length: 24 }, (_, i) => i + "时"),
      axisLabel: { rotate: 45 },
    },
    yAxis: {
      type: "value",
      name: "截图数量",
    },
    series: [
      {
        name: "截图数",
        type: chartType.value,
        data: data,
        itemStyle: {
          color: "#667eea",
          borderRadius: [4, 4, 0, 0],
        },
        lineStyle: { color: "#667eea", width: 3 },
        smooth: true,
        areaStyle:
          chartType.value === "line"
            ? {
                color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                  { offset: 0, color: "rgba(102, 126, 234, 0.3)" },
                  { offset: 1, color: "rgba(102, 126, 234, 0.1)" },
                ]),
              }
            : undefined,
      },
    ],
  };

  hourlyChart.setOption(option);
};

// 渲染格式占比图表
const renderFormatChart = (data) => {
  if (!formatChartRef.value) return;

  if (!formatChart) {
    formatChart = echarts.init(formatChartRef.value);
  }

  const option = {
    tooltip: {
      trigger: "item",
      formatter: "{b}: {c} ({d}%)",
    },
    legend: {
      orient: "vertical",
      left: "left",
      top: "center",
    },
    series: [
      {
        name: "图片格式",
        type: "pie",
        radius: ["50%", "70%"],
        avoidLabelOverlap: false,
        itemStyle: {
          borderRadius: 10,
          borderColor: "#fff",
          borderWidth: 2,
        },
        label: {
          show: false,
        },
        emphasis: {
          label: {
            show: true,
            fontSize: "12",
            fontWeight: "bold",
          },
        },
        data: [
          { value: data.webp, name: "WebP", itemStyle: { color: "#52c41a" } },
          { value: data.jpg, name: "JPG", itemStyle: { color: "#fa8c16" } },
          { value: data.other, name: "其他", itemStyle: { color: "#ff4d4f" } },
        ],
      },
    ],
  };

  formatChart.setOption(option);
};

// 刷新活动
const refreshActivities = async () => {
  activitiesLoading.value = true;
  try {
    const data = await statsApi.getActivities(10);
    recentActivities.value = data;
  } catch (error) {
    console.error("刷新活动失败:", error);
  } finally {
    activitiesLoading.value = false;
  }
};

// 查看员工
const viewEmployee = (id) => {
  router.push(`/employees?view=${id}`);
};

// 监听图表类型变化
watch(chartType, () => {
  if (hourlyChart) {
    const data = hourlyChart.getOption().series[0].data;
    renderHourlyChart(data);
  }
});

// 窗口大小变化自适应
const handleResize = () => {
  hourlyChart?.resize();
  formatChart?.resize();
};

onMounted(() => {
  loadStats();
  loadCleanupStatus();
  window.addEventListener("resize", handleResize);

  // 定时刷新
  const timer = setInterval(loadStats, 30000);
  onUnmounted(() => {
    clearInterval(timer);
    window.removeEventListener("resize", handleResize);
    hourlyChart?.dispose();
    formatChart?.dispose();
  });
});
</script>

<style scoped>
.dashboard {
  padding: 20px;
}

.stats-row {
  margin-bottom: 20px;
}

.stat-card {
  transition: all 0.3s;
  height: 100%;
}

.stat-card:hover {
  transform: translateY(-5px);
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.1);
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

.stat-info {
  flex: 1;
}

.stat-value {
  font-size: 28px;
  font-weight: bold;
  color: #333;
  line-height: 1.2;
  margin-bottom: 4px;
}

.stat-label {
  font-size: 14px;
  color: #999;
}

.stat-trend {
  font-size: 12px;
  margin-top: 4px;
  display: flex;
  align-items: center;
  gap: 2px;
}

.stat-trend.up {
  color: #52c41a;
}

.stat-trend.down {
  color: #ff4d4f;
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

.activity-row {
  margin-bottom: 20px;
}

.activity-card {
  height: 100%;
}

.activity-list {
  max-height: 300px;
  overflow-y: auto;
  padding: 0 10px;
}

.activity-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 0;
  border-bottom: 1px solid #f0f0f0;
}

.activity-item:last-child {
  border-bottom: none;
}

.activity-content {
  flex: 1;
}

.activity-title {
  margin-bottom: 4px;
}

.employee {
  font-weight: 500;
  color: #333;
  margin-right: 8px;
}

.action {
  color: #999;
  font-size: 12px;
}

.activity-time {
  font-size: 12px;
  color: #999;
}

.cleanup-card {
  margin-top: 20px;
}

.cleanup-item {
  text-align: center;
  padding: 10px;
}

.cleanup-item .label {
  font-size: 13px;
  color: #999;
  margin-bottom: 5px;
}

.cleanup-item .value {
  font-size: 18px;
  font-weight: 500;
  color: #333;
}
</style>
