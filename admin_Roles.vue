<!-- admin_Roles.vue - 修复版 -->
<template>
  <div class="roles-management">
    <!-- 工具栏 -->
    <el-card class="toolbar" shadow="hover">
      <el-row :gutter="20" align="middle">
        <el-col :span="6">
          <el-input
            v-model="searchKeyword"
            placeholder="搜索角色名称"
            :prefix-icon="Search"
            clearable
            @input="handleSearch"
          />
        </el-col>
        <el-col :span="14" class="text-right">
          <el-button type="primary" @click="showAddDialog">
            <el-icon><Plus /></el-icon>创建角色
          </el-button>
          <el-button @click="loadRoles">
            <el-icon><Refresh /></el-icon>刷新
          </el-button>
        </el-col>
      </el-row>
    </el-card>

    <!-- 角色列表 -->
    <el-card class="table-card" shadow="hover">
      <el-table v-loading="loading" :data="roles" stripe style="width: 100%">
        <el-table-column type="index" width="50" />

        <el-table-column prop="name" label="角色标识" width="150">
          <template #default="{ row }">
            <el-tag :type="row.is_system ? 'danger' : 'primary'">
              {{ row.name }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="display_name" label="角色名称" width="150" />

        <el-table-column
          prop="description"
          label="描述"
          min-width="200"
          show-overflow-tooltip
        />

        <el-table-column label="用户数" width="80" align="center">
          <template #default="{ row }">
            {{ row.user_count || 0 }}
          </template>
        </el-table-column>

        <el-table-column label="类型" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="row.is_system ? 'danger' : 'info'" size="small">
              {{ row.is_system ? "系统" : "自定义" }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="editRole(row)">
              <el-icon><Edit /></el-icon>编辑
            </el-button>
            <el-button
              v-if="!row.is_system"
              link
              type="danger"
              @click="deleteRole(row)"
            >
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

    <!-- 添加/编辑角色对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogTitle"
      width="700px"
      @close="resetForm"
    >
      <el-form
        ref="formRef"
        :model="formData"
        :rules="formRules"
        label-width="80px"
      >
        <el-form-item label="角色标识" prop="name">
          <el-input
            v-model="formData.name"
            :disabled="dialogType === 'edit' && isEditingSystemRole"
            placeholder="请输入角色标识（如：custom_role）"
          />
          <span class="help-text"
            >角色标识用于代码中判断，建议使用小写字母和下划线</span
          >
        </el-form-item>

        <el-form-item label="角色名称" prop="display_name">
          <el-input
            v-model="formData.display_name"
            placeholder="请输入角色名称"
          />
        </el-form-item>

        <el-form-item label="描述" prop="description">
          <el-input
            v-model="formData.description"
            type="textarea"
            :rows="2"
            placeholder="请输入角色描述"
          />
        </el-form-item>

        <el-form-item label="权限配置" prop="permissions">
          <div class="permission-tree">
            <div
              v-for="group in permissionGroups"
              :key="group.name"
              class="permission-group"
            >
              <div class="group-header">
                <el-checkbox
                  :model-value="isGroupAllSelected(group)"
                  :indeterminate="isGroupIndeterminate(group)"
                  @change="toggleGroup(group)"
                >
                  <strong>{{ group.name }}</strong>
                </el-checkbox>
              </div>
              <div class="group-permissions">
                <el-checkbox
                  v-for="perm in group.permissions"
                  :key="perm.code"
                  v-model="selectedPermissions[perm.code]"
                >
                  {{ perm.name }}
                </el-checkbox>
              </div>
            </div>
          </div>
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
import { ref, reactive, onMounted } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Search, Plus, Refresh, Edit, Delete } from "@element-plus/icons-vue";
import api from "./admin_api";

const loading = ref(false);
const roles = ref([]);
const total = ref(0);
const currentPage = ref(1);
const pageSize = ref(10);
const searchKeyword = ref("");

const dialogVisible = ref(false);
const dialogType = ref("add");
const dialogTitle = ref("创建角色");
const submitting = ref(false);
const formRef = ref(null);
const isEditingSystemRole = ref(false);
const currentRoleId = ref(null);

const permissionGroups = ref([]);
const selectedPermissions = ref({});

const formData = reactive({
  name: "",
  display_name: "",
  description: "",
  permissions: { type: "none" },
});

const formRules = {
  name: [
    { required: true, message: "请输入角色标识", trigger: "blur" },
    {
      pattern: /^[a-z_][a-z0-9_]*$/,
      message: "角色标识只能包含小写字母、数字和下划线，且不能以数字开头",
      trigger: "blur",
    },
  ],
  display_name: [
    { required: true, message: "请输入角色名称", trigger: "blur" },
  ],
};

// 加载权限列表
let permissionsLoaded = false; // ✅ 在文件顶部添加这个变量

const loadPermissions = async () => {
  if (permissionsLoaded) return; // ✅ 已加载则跳过

  try {
    const response = await api.get("/permissions");
    permissionGroups.value = Object.entries(response.groups || {}).map(
      ([key, value]) => ({
        name: value.name,
        permissions: value.permissions,
      }),
    );
    permissionsLoaded = true; // ✅ 标记已加载
  } catch (error) {
    console.error("加载权限列表失败:", error);
  }
};

// 加载角色列表
const loadRoles = async () => {
  loading.value = true;
  try {
    const params = {
      skip: (currentPage.value - 1) * pageSize.value,
      limit: pageSize.value,
    };

    if (searchKeyword.value) {
      params.search = searchKeyword.value;
    }

    const response = await api.get("/roles", { params });
    roles.value = response.items || [];
    total.value = response.total || 0;
  } catch (error) {
    console.error("加载角色失败:", error);
    ElMessage.error("加载角色失败");
  } finally {
    loading.value = false;
  }
};

// 搜索
let searchTimer;
const handleSearch = () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    currentPage.value = 1;
    loadRoles();
  }, 300);
};

// 分页
const handleSizeChange = (val) => {
  pageSize.value = val;
  currentPage.value = 1;
  loadRoles();
};

const handleCurrentChange = (val) => {
  currentPage.value = val;
  loadRoles();
};

// 检查组是否全选
const isGroupAllSelected = (group) => {
  return group.permissions.every(
    (perm) => selectedPermissions.value[perm.code],
  );
};

// 检查组是否部分选中
const isGroupIndeterminate = (group) => {
  const selected = group.permissions.filter(
    (perm) => selectedPermissions.value[perm.code],
  );
  return selected.length > 0 && selected.length < group.permissions.length;
};

// 切换组全选
const toggleGroup = (group) => {
  const allSelected = isGroupAllSelected(group);
  group.permissions.forEach((perm) => {
    selectedPermissions.value[perm.code] = !allSelected;
  });
};

// 显示添加对话框
const showAddDialog = () => {
  dialogType.value = "add";
  dialogTitle.value = "创建角色";
  isEditingSystemRole.value = false;
  currentRoleId.value = null;
  resetForm();
  dialogVisible.value = true;
};

// admin_Roles.vue
const editRole = async (row) => {
  currentRoleId.value = row.id;
  dialogType.value = "edit";
  dialogTitle.value = "编辑角色";
  isEditingSystemRole.value = row.is_system;

  formData.name = row.name;
  formData.display_name = row.display_name;
  formData.description = row.description || "";

  // ✅ 关键修复：先完全清空 selectedPermissions
  // 方法1：重新赋值为新对象
  selectedPermissions.value = {};

  // 解析权限
  let perms = row.permissions;

  // ✅ 处理字符串格式（如果后端返回的是字符串）
  if (typeof perms === "string") {
    try {
      perms = JSON.parse(perms);
    } catch (e) {
      console.error("解析权限失败:", e);
      perms = { type: "none" };
    }
  }

  // ✅ 根据权限类型设置选中状态
  if (perms && perms.type === "all") {
    // 全选所有权限
    permissionGroups.value.forEach((group) => {
      group.permissions.forEach((perm) => {
        selectedPermissions.value[perm.code] = true;
      });
    });
  } else if (perms && perms.type === "custom") {
    // 只选中角色拥有的权限
    (perms.permissions || []).forEach((code) => {
      selectedPermissions.value[code] = true;
    });
  }
  // 如果是 "none"，selectedPermissions 保持为空对象

  dialogVisible.value = true;
};

// 删除角色
const deleteRole = (row) => {
  ElMessageBox.confirm(
    `确定要删除角色 "${row.display_name}" 吗？使用此角色的用户将失去权限！`,
    "警告",
    {
      confirmButtonText: "确定",
      cancelButtonText: "取消",
      type: "warning",
    },
  ).then(async () => {
    try {
      await api.delete(`/roles/${row.id}`);
      ElMessage.success("删除成功");
      if (roles.value.length === 1 && currentPage.value > 1) {
        currentPage.value--;
      }
      loadRoles();
    } catch (error) {
      console.error("删除失败:", error);
      ElMessage.error(error.response?.data?.detail || "删除失败");
    }
  });
};

// 重置表单
const resetForm = () => {
  formData.name = "";
  formData.display_name = "";
  formData.description = "";
  selectedPermissions.value = {};
  formRef.value?.clearValidate();
};

// 提交表单
const submitForm = async () => {
  if (!formRef.value) return;

  await formRef.value.validate(async (valid) => {
    if (valid) {
      submitting.value = true;
      try {
        // 构建权限对象
        const selectedList = Object.entries(selectedPermissions.value)
          .filter(([_, selected]) => selected)
          .map(([code]) => code);

        let permissions;
        const totalPermissions = permissionGroups.value.reduce(
          (sum, g) => sum + g.permissions.length,
          0,
        );

        if (selectedList.length === totalPermissions && totalPermissions > 0) {
          permissions = { type: "all" };
        } else if (selectedList.length > 0) {
          permissions = { type: "custom", permissions: selectedList };
        } else {
          permissions = { type: "none" };
        }

        const data = {
          name: formData.name,
          display_name: formData.display_name,
          description: formData.description,
          permissions: permissions,
        };

        if (dialogType.value === "add") {
          await api.post("/roles", data);
          ElMessage.success("角色创建成功");
        } else {
          await api.put(`/roles/${currentRoleId.value}`, data);
          ElMessage.success("角色更新成功");
        }

        dialogVisible.value = false;
        loadRoles();
      } catch (error) {
        console.error("提交失败:", error);
        ElMessage.error(error.response?.data?.detail || "提交失败");
      } finally {
        submitting.value = false;
      }
    }
  });
};

onMounted(() => {
  loadPermissions();
  loadRoles();
});
</script>

<style scoped>
.roles-management {
  padding: 20px;
}

.toolbar {
  margin-bottom: 20px;
}

.table-card {
  min-height: 400px;
}

.pagination {
  margin-top: 20px;
  text-align: right;
}

.text-right {
  text-align: right;
}

.help-text {
  font-size: 12px;
  color: #999;
  margin-left: 8px;
}

.permission-tree {
  max-height: 400px;
  overflow-y: auto;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  padding: 8px;
}

.permission-group {
  margin-bottom: 16px;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  overflow: hidden;
}

.group-header {
  padding: 8px 12px;
  background-color: #f5f7fa;
  border-bottom: 1px solid #ebeef5;
}

.group-permissions {
  padding: 8px 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
}
</style>
