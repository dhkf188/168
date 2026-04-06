<!-- admin_Files.vue -->
<template>
  <div class="files-monitor">
    <!-- 筛选栏 -->
    <el-card class="filter-bar" shadow="hover">
      <el-row :gutter="20" align="middle">
        <el-col :span="4">
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

        <el-col :span="3">
          <el-select
            v-model="filters.operation"
            placeholder="操作类型"
            clearable
            @change="handleFilterChange"
          >
            <el-option label="创建" value="create" />
            <el-option label="修改" value="modify" />
            <el-option label="删除" value="delete" />
            <el-option label="重命名" value="rename" />
            <el-option label="移动" value="move" />
          </el-select>
        </el-col>

        <el-col :span="4">
          <el-select
            v-model="filters.fileType"
            placeholder="文件类型"
            clearable
            filterable
            allow-create
            @change="handleFilterChange"
          >
            <el-option label="文档" value=".doc,.docx,.txt,.pdf" />
            <el-option label="图片" value=".jpg,.png,.gif,.bmp" />
            <el-option label="压缩包" value=".zip,.rar,.7z" />
            <el-option label="可执行文件" value=".exe,.msi" />
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
            placeholder="搜索文件路径"
            :prefix-icon="Search"
            clearable
            @input="handleSearch"
          />
        </el-col>

        <el-col :span="2" class="text-right">
          <el-button type="primary" @click="loadData">
            <el-icon><Search /></el-icon>查询
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
              <el-icon><Document /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ stats.totalOperations }}</div>
              <div class="stat-label">总操作数</div>
            </div>
          </div>
        </el-card>
      </el-col>

      <el-col :span="6">
        <el-card class="stat-card" shadow="hover">
          <div class="stat-content">
            <div class="stat-icon" style="background: #f6ffed; color: #52c41a">
              <el-icon><FolderAdd /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ stats.creates }}</div>
              <div class="stat-label">创建</div>
            </div>
          </div>
        </el-card>
      </el-col>

      <el-col :span="6">
        <el-card class="stat-card" shadow="hover">
          <div class="stat-content">
            <div class="stat-icon" style="background: #fff7e6; color: #fa8c16">
              <el-icon><Edit /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ stats.modifies }}</div>
              <div class="stat-label">修改</div>
            </div>
          </div>
        </el-card>
      </el-col>

      <el-col :span="6">
        <el-card class="stat-card" shadow="hover">
          <div class="stat-content">
            <div class="stat-icon" style="background: #fff1f0; color: #ff4d4f">
              <el-icon><Delete /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ stats.deletes }}</div>
              <div class="stat-label">删除</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 操作分布图 -->
    <el-row :gutter="20" class="chart-row">
      <el-col :span="8">
        <el-card class="chart-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <span>操作分布</span>
            </div>
          </template>
          <div class="chart-container" ref="pieChartRef"></div>
        </el-card>
      </el-col>

      <el-col :span="16">
        <el-card class="chart-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <span>文件类型TOP10</span>
            </div>
          </template>
          <div class="chart-container" ref="barChartRef"></div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 文件操作列表 -->
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

        <el-table-column label="操作时间" width="160">
          <template #default="{ row }">
            {{ formatDateTime(row.operation_time) }}
          </template>
        </el-table-column>

        <el-table-column label="操作" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="getOperationType(row.operation)" size="small">
              {{ row.operation_cn }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="文件路径" min-width="400" show-overflow-tooltip>
          <template #default="{ row }">
            <div class="file-path">
              <el-icon><Folder /></el-icon>
              <span>{{ row.file_path }}</span>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="文件名" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            {{ row.file_name || "-" }}
          </template>
        </el-table-column>

        <el-table-column label="文件类型" width="100" align="center">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">
              {{ row.file_type || "-" }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="文件大小" width="100" align="center">
          <template #default="{ row }">
            {{ row.file_size_str || "-" }}
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
import { ref, onMounted, onUnmounted } from "vue";
import { ElMessage } from "element-plus";
import {
  Search,
  Document,
  FolderAdd,
  Edit,
  Delete,
  Folder,
  User,
} from "@element-plus/icons-vue";
import * as echarts from "echarts";
import api from "./admin_api";
import { formatDateTime } from "./admin_timezone";

const loading = ref(false);
const items = ref([]);
const total = ref(0);
const currentPage = ref(1);
const pageSize = ref(20);
const employees = ref([]);
const pieChartRef = ref(null);
const barChartRef = ref(null);
let pieChart = null;
let barChart = null;

const stats = ref({
  totalOperations: 0,
  creates: 0,
  modifies: 0,
  deletes: 0,
});

const filters = ref({
  employeeId: "",
  operation: "",
  fileType: "",
  dateRange: [],
  search: "",
});

// 获取操作类型样式
const getOperationType = (op) => {
  const map = {
    create: "success",
    modify: "warning",
    delete: "danger",
    rename: "info",
  };
  return map[op] || "info";
};

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

    if (filters.value.operation) {
      params.operation = filters.value.operation;
    }

    if (filters.value.fileType) {
      params.file_type = filters.value.fileType;
    }

    if (filters.value.dateRange && filters.value.dateRange.length === 2) {
      params.start_date = filters.value.dateRange[0];
      params.end_date = filters.value.dateRange[1];
    }

    if (filters.value.search) {
      params.search = filters.value.search;
    }

    const response = await api.get("/files/operations", { params });
    items.value = response.items || [];
    total.value = response.total || 0;

    // 加载统计（使用后端接口）
    await loadStats();

    // 渲染图表（使用后端接口）
    await renderCharts();
  } catch (error) {
    console.error("加载文件操作失败:", error);
    ElMessage.error("加载失败");
  } finally {
    loading.value = false;
  }
};

// 加载统计 - 使用后端接口
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

    const response = await api.get("/files/stats", { params });
    const statsData = response || {};

    // 使用后端返回的统计
    stats.value.totalOperations = (statsData.by_operation || []).reduce(
      (sum, item) => sum + (item.count || 0),
      0,
    );

    stats.value.creates =
      (statsData.by_operation || []).find((item) => item.operation === "create")
        ?.count || 0;

    stats.value.modifies =
      (statsData.by_operation || []).find((item) => item.operation === "modify")
        ?.count || 0;

    stats.value.deletes =
      (statsData.by_operation || []).find((item) => item.operation === "delete")
        ?.count || 0;

    console.log("文件统计加载成功:", stats.value);
  } catch (error) {
    console.error("加载文件统计失败:", error);
    // 降级：使用当前页数据
    stats.value.totalOperations = items.value.length;
    stats.value.creates = items.value.filter(
      (i) => i.operation === "create",
    ).length;
    stats.value.modifies = items.value.filter(
      (i) => i.operation === "modify",
    ).length;
    stats.value.deletes = items.value.filter(
      (i) => i.operation === "delete",
    ).length;
  }
};

// 渲染图表 - 使用后端接口
const renderCharts = async () => {
  if (!pieChartRef.value || !barChartRef.value) return;

  // 加载操作分布数据
  await loadOperationDistribution();

  // 加载文件类型TOP10数据
  await loadFileTypeTop10();
};

// 加载操作分布数据
const loadOperationDistribution = async () => {
  try {
    const params = {};
    if (filters.value.employeeId) {
      params.employee_id = filters.value.employeeId;
    }
    if (filters.value.dateRange && filters.value.dateRange.length === 2) {
      params.start_date = filters.value.dateRange[0];
      params.end_date = filters.value.dateRange[1];
    }

    const response = await api.get("/files/stats", { params });
    const statsData = response || {};
    const operations = statsData.by_operation || [];

    if (!pieChart) {
      pieChart = echarts.init(pieChartRef.value);
    }

    // 操作分布数据
    const opMap = {
      create: { name: "创建", color: "#52c41a" },
      modify: { name: "修改", color: "#fa8c16" },
      delete: { name: "删除", color: "#ff4d4f" },
    };

    const pieData = [];
    for (const op of operations) {
      if (opMap[op.operation]) {
        pieData.push({
          value: op.count,
          name: opMap[op.operation].name,
          itemStyle: { color: opMap[op.operation].color },
        });
      } else {
        pieData.push({
          value: op.count,
          name: op.operation_cn || op.operation || "其他",
          itemStyle: { color: "#909399" },
        });
      }
    }

    const pieOption = {
      tooltip: {
        trigger: "item",
        formatter: "{b}: {c} ({d}%)",
      },
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
  } catch (error) {
    console.error("加载操作分布失败:", error);
    // 降级：使用当前页数据
    const opCount = {
      create: items.value.filter((i) => i.operation === "create").length,
      modify: items.value.filter((i) => i.operation === "modify").length,
      delete: items.value.filter((i) => i.operation === "delete").length,
      other: items.value.filter(
        (i) => !["create", "modify", "delete"].includes(i.operation),
      ).length,
    };

    if (!pieChart) {
      pieChart = echarts.init(pieChartRef.value);
    }

    pieChart.setOption({
      series: [
        {
          data: [
            {
              value: opCount.create,
              name: "创建",
              itemStyle: { color: "#52c41a" },
            },
            {
              value: opCount.modify,
              name: "修改",
              itemStyle: { color: "#fa8c16" },
            },
            {
              value: opCount.delete,
              name: "删除",
              itemStyle: { color: "#ff4d4f" },
            },
            {
              value: opCount.other,
              name: "其他",
              itemStyle: { color: "#909399" },
            },
          ],
        },
      ],
    });
  }
};

// 加载文件类型TOP10
const loadFileTypeTop10 = async () => {
  try {
    const params = {};
    if (filters.value.employeeId) {
      params.employee_id = filters.value.employeeId;
    }
    if (filters.value.dateRange && filters.value.dateRange.length === 2) {
      params.start_date = filters.value.dateRange[0];
      params.end_date = filters.value.dateRange[1];
    }

    const response = await api.get("/files/stats", { params });
    const statsData = response || {};
    const fileTypes = statsData.by_file_type || [];

    if (!barChart) {
      barChart = echarts.init(barChartRef.value);
    }

    // 按数量排序取前10
    const sortedTypes = [...fileTypes]
      .sort((a, b) => b.count - a.count)
      .slice(0, 10);

    const barOption = {
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
      grid: { left: "3%", right: "4%", bottom: "3%", containLabel: true },
      xAxis: {
        type: "category",
        data: sortedTypes.map((item) => item.type),
        axisLabel: { rotate: 45 },
      },
      yAxis: { type: "value", name: "操作次数" },
      series: [
        {
          name: "操作次数",
          type: "bar",
          data: sortedTypes.map((item) => item.count),
          itemStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: "#667eea" },
              { offset: 1, color: "#764ba2" },
            ]),
            borderRadius: [4, 4, 0, 0],
          },
        },
      ],
    };
    barChart.setOption(barOption);
  } catch (error) {
    console.error("加载文件类型TOP10失败:", error);
    // 降级：使用当前页数据
    const typeCount = {};
    items.value.forEach((item) => {
      const type = item.file_type || "其他";
      typeCount[type] = (typeCount[type] || 0) + 1;
    });

    const sortedTypes = Object.entries(typeCount)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 10);

    if (!barChart) {
      barChart = echarts.init(barChartRef.value);
    }

    barChart.setOption({
      xAxis: { data: sortedTypes.map(([type]) => type) },
      series: [{ data: sortedTypes.map(([, count]) => count) }],
    });
  }
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
    operation: "",
    fileType: "",
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
  pieChart?.resize();
  barChart?.resize();
};

onMounted(() => {
  loadEmployees();
  loadData();
  window.addEventListener("resize", handleResize);
});

onUnmounted(() => {
  window.removeEventListener("resize", handleResize);
  pieChart?.dispose();
  barChart?.dispose();
});
</script>

<style scoped>
.files-monitor {
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

.file-path {
  display: flex;
  align-items: center;
  gap: 4px;
  color: #409eff;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pagination {
  margin-top: 20px;
  text-align: right;
}

.text-right {
  text-align: right;
}
</style>
