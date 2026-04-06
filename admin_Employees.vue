<template>
  <div class="employees">
    <!-- 工具栏 -->
    <el-card class="toolbar" shadow="hover">
      <el-row :gutter="20" align="middle">
        <el-col :span="8">
          <el-input
            v-model="searchQuery"
            placeholder="搜索员工姓名、ID、部门..."
            :prefix-icon="Search"
            clearable
            @input="handleSearch"
            @clear="handleSearch"
          />
        </el-col>
        <el-col :span="6">
          <el-select
            v-model="statusFilter"
            placeholder="状态筛选"
            clearable
            @change="handleFilterChange"
          >
            <el-option label="全部" value="" />
            <el-option label="在职" value="active" />
            <el-option label="离职" value="inactive" />
            <el-option label="在线" value="online" />
            <el-option label="离线" value="offline" />
          </el-select>
        </el-col>
        <el-col :span="10" class="text-right">
          <el-button type="primary" @click="showAddDialog">
            <el-icon><Plus /></el-icon>添加员工
          </el-button>
          <el-button @click="refresh">
            <el-icon><Refresh /></el-icon>刷新
          </el-button>
        </el-col>
      </el-row>
    </el-card>

    <!-- 员工列表 -->
    <el-card class="table-card" shadow="hover">
      <el-table
        v-loading="loading"
        :data="employees"
        stripe
        style="width: 100%"
        @row-click="handleRowClick"
      >
        <el-table-column type="index" :index="getIndex" width="50" />

        <el-table-column label="员工" min-width="200">
          <template #default="{ row }">
            <div class="employee-info">
              <el-avatar :size="40" :icon="User" />
              <div class="employee-detail">
                <div class="employee-name">
                  {{ row.name }}
                  <el-tag
                    v-if="row.status === 'inactive'"
                    size="small"
                    type="info"
                    >离职</el-tag
                  >
                </div>
                <div class="employee-id">{{ row.employee_id || row.id }}</div>
              </div>
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="department" label="部门" width="120">
          <template #default="{ row }">
            {{ row.department || "-" }}
          </template>
        </el-table-column>

        <el-table-column prop="position" label="职位" width="120">
          <template #default="{ row }">
            {{ row.position || "-" }}
          </template>
        </el-table-column>

        <el-table-column label="截图统计" width="150" align="center">
          <template #default="{ row }">
            <div class="stat-badge">
              <el-tag size="small" type="primary"
                >今日 {{ row.today_screenshots || 0 }}</el-tag
              >
              <el-tag size="small"
                >总计 {{ row.total_screenshots || 0 }}</el-tag
              >
            </div>
          </template>
        </el-table-column>

        <el-table-column label="最后活跃" width="180">
          <template #default="{ row }">
            {{ formatDateTime(row.last_active) }}
          </template>
        </el-table-column>

        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="getOnlineStatus(row).type" size="small">
              {{ getOnlineStatus(row).text }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button
              link
              type="primary"
              @click.stop="viewScreenshots(row.employee_id || row.id)"
            >
              <el-icon><Picture /></el-icon>截图
            </el-button>
            <el-button link type="primary" @click.stop="editEmployee(row)">
              <el-icon><Edit /></el-icon>编辑
            </el-button>
            <el-button link type="danger" @click.stop="deleteEmployee(row)">
              <el-icon><Delete /></el-icon>删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="pagination">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[10, 20, 50, 100]"
          :total="total"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
        />
      </div>
    </el-card>

    <!-- 添加/编辑员工对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogTitle"
      width="500px"
      @close="resetForm"
    >
      <el-form
        ref="formRef"
        :model="formData"
        :rules="formRules"
        label-width="80px"
      >
        <el-form-item label="员工ID" prop="employee_id">
          <el-input
            v-model="formData.employee_id"
            :disabled="dialogType === 'edit'"
            placeholder="请输入员工ID"
          />
        </el-form-item>

        <el-form-item label="姓名" prop="name">
          <el-input v-model="formData.name" placeholder="请输入姓名" />
        </el-form-item>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="部门" prop="department">
              <el-input
                v-model="formData.department"
                placeholder="请输入部门"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="职位" prop="position">
              <el-input v-model="formData.position" placeholder="请输入职位" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item label="邮箱" prop="email">
          <el-input v-model="formData.email" placeholder="请输入邮箱" />
        </el-form-item>

        <el-form-item label="电话" prop="phone">
          <el-input v-model="formData.phone" placeholder="请输入电话" />
        </el-form-item>

        <el-form-item label="状态" prop="status">
          <el-radio-group v-model="formData.status">
            <el-radio label="active">在职</el-radio>
            <el-radio label="inactive">离职</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitForm" :loading="submitting">
          确定
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
// ===== 导入统一的时间工具 =====
import {
  formatDateTime as formatDateTimeUtil,
  getOnlineStatus as getOnlineStatusUtil,
} from "./admin_timezone";
// ============================

import { ref, onMounted, watch } from "vue";
import { useRouter, useRoute } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  Search,
  Plus,
  Refresh,
  User,
  Picture,
  Edit,
  Delete,
} from "@element-plus/icons-vue";
import { employeeApi } from "./admin_api";

const router = useRouter();
const route = useRoute();
const loading = ref(false);
const employees = ref([]);
const total = ref(0);
const currentPage = ref(1);
const pageSize = ref(10);
const searchQuery = ref("");
const statusFilter = ref("");

const dialogVisible = ref(false);
const dialogType = ref("add");
const dialogTitle = ref("添加员工");
const submitting = ref(false);
const formRef = ref(null);

const formData = ref({
  employee_id: "",
  name: "",
  department: "",
  position: "",
  email: "",
  phone: "",
  status: "active",
});

const formRules = {
  employee_id: [
    { required: true, message: "请输入员工ID", trigger: "blur" },
    { min: 2, message: "员工ID至少2个字符", trigger: "blur" },
  ],
  name: [
    { required: true, message: "请输入姓名", trigger: "blur" },
    { min: 2, message: "姓名至少2个字符", trigger: "blur" },
  ],
  email: [
    { type: "email", message: "请输入正确的邮箱地址", trigger: "blur" },
    { required: false },
  ],
};

// ===== 获取在线状态 =====
const getOnlineStatus = (employee) => {
  if (employee.status !== "active") {
    return { type: "info", text: "离职" };
  }
  return getOnlineStatusUtil(employee.last_active, 10);
};

// ===== 格式化日期时间 =====
const formatDateTime = (datetime) => {
  if (!datetime) return "从未";
  return formatDateTimeUtil(datetime, "YYYY-MM-DD HH:mm");
};

// ===== 计算表格索引 =====
const getIndex = (index) => {
  return (currentPage.value - 1) * pageSize.value + index + 1;
};

// ===== 加载员工列表（支持后端分页和搜索）=====
// ===== 加载员工列表（使用统一响应处理）=====
const loadEmployees = async () => {
  loading.value = true;
  try {
    const params = {
      skip: (currentPage.value - 1) * pageSize.value,
      limit: pageSize.value,
    };

    if (searchQuery.value) {
      params.search = searchQuery.value;
    }

    if (statusFilter.value) {
      if (statusFilter.value === "online") {
        params.online_only = true;
      } else if (statusFilter.value === "offline") {
        params.online_only = false;
      } else {
        params.status = statusFilter.value;
      }
    }

    // ✅ 使用修改后的API，返回统一格式
    const response = await employeeApi.getEmployees(params);

    // ✅ 直接使用标准化的响应
    employees.value = response.items || [];
    total.value = response.total || 0;

    console.log(`员工列表加载成功: ${employees.value.length}/${total.value}`);
  } catch (error) {
    console.error("加载员工列表失败:", error);
    ElMessage.error("加载员工列表失败");
    employees.value = [];
    total.value = 0;
  } finally {
    loading.value = false;
  }
};

// ===== 搜索处理（带防抖）=====
let searchTimer = null;
const handleSearch = () => {
  if (searchTimer) clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    currentPage.value = 1;
    loadEmployees();
  }, 300);
};

// ===== 筛选变化处理 =====
const handleFilterChange = () => {
  currentPage.value = 1;
  loadEmployees();
};

// ===== 分页大小变化 =====
const handleSizeChange = (val) => {
  pageSize.value = val;
  currentPage.value = 1;
  loadEmployees();
};

// ===== 当前页变化 =====
const handleCurrentChange = (val) => {
  currentPage.value = val;
  loadEmployees();
};

// ===== 刷新 =====
const refresh = () => {
  currentPage.value = 1;
  loadEmployees();
};

// ===== 显示添加对话框 =====
const showAddDialog = () => {
  dialogType.value = "add";
  dialogTitle.value = "添加员工";
  resetForm();
  dialogVisible.value = true;
};

// ===== 编辑员工 =====
const editEmployee = (row) => {
  dialogType.value = "edit";
  dialogTitle.value = "编辑员工";
  formData.value = {
    employee_id: row.employee_id || row.id,
    name: row.name,
    department: row.department || "",
    position: row.position || "",
    email: row.email || "",
    phone: row.phone || "",
    status: row.status || "active",
  };
  dialogVisible.value = true;
};

// ===== 查看截图 =====
const viewScreenshots = (employeeId) => {
  router.push(`/screenshots?employee_id=${employeeId}`);
};

// ===== 删除员工 =====
const deleteEmployee = (row) => {
  const employeeId = row.employee_id || row.id;
  ElMessageBox.confirm(
    `确定要删除员工 "${row.name}" 吗？此操作不可恢复！`,
    "警告",
    {
      confirmButtonText: "确定",
      cancelButtonText: "取消",
      type: "warning",
    },
  )
    .then(async () => {
      try {
        await employeeApi.deleteEmployee(employeeId);
        ElMessage.success("删除成功");
        // 如果当前页只有一条数据且不是第一页，则返回上一页
        if (employees.value.length === 1 && currentPage.value > 1) {
          currentPage.value--;
        }
        loadEmployees();
      } catch (error) {
        console.error("删除失败:", error);
        ElMessage.error(error.response?.data?.detail || "删除失败");
      }
    })
    .catch(() => {});
};

// ===== 重置表单 =====
const resetForm = () => {
  formData.value = {
    employee_id: "",
    name: "",
    department: "",
    position: "",
    email: "",
    phone: "",
    status: "active",
  };
  formRef.value?.clearValidate();
};

// ===== 提交表单 =====
const submitForm = async () => {
  if (!formRef.value) return;

  await formRef.value.validate(async (valid) => {
    if (valid) {
      submitting.value = true;
      try {
        if (dialogType.value === "add") {
          await employeeApi.createEmployee(formData.value);
          ElMessage.success("员工添加成功");
        } else {
          await employeeApi.updateEmployee(
            formData.value.employee_id,
            formData.value,
          );
          ElMessage.success("员工信息更新成功");
        }

        dialogVisible.value = false;
        loadEmployees();
      } catch (error) {
        console.error("提交失败:", error);
        ElMessage.error(error.response?.data?.detail || "提交失败");
      } finally {
        submitting.value = false;
      }
    }
  });
};

// ===== 行点击 =====
const handleRowClick = (row) => {
  viewScreenshots(row.employee_id || row.id);
};

// ===== 监听路由参数 =====
onMounted(() => {
  loadEmployees();

  if (route.query.view) {
    viewScreenshots(route.query.view);
  }
});

// ===== 监听分页参数变化 =====
watch([currentPage, pageSize], () => {
  loadEmployees();
});
</script>

<style scoped>
.employees {
  padding: 20px;
}

.toolbar {
  margin-bottom: 20px;
}

.table-card {
  min-height: 400px;
}

.employee-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.employee-detail {
  flex: 1;
}

.employee-name {
  font-weight: 500;
  color: #333;
  margin-bottom: 4px;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
}

.employee-id {
  font-size: 12px;
  color: #999;
}

.stat-badge {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.pagination {
  margin-top: 20px;
  text-align: right;
}

.text-right {
  text-align: right;
}

:deep(.el-table__row) {
  cursor: pointer;
}
</style>
