<!-- admin_Users.vue - 新建文件 -->
<template>
  <div class="users-management">
    <!-- 工具栏 -->
    <el-card class="toolbar" shadow="hover">
      <el-row :gutter="20" align="middle">
        <el-col :span="6">
          <el-input
            v-model="searchKeyword"
            placeholder="搜索用户名/部门/邮箱"
            :prefix-icon="Search"
            clearable
            @input="handleSearch"
          />
        </el-col>
        <el-col :span="4">
          <el-select
            v-model="filters.roleId"
            placeholder="角色筛选"
            clearable
            @change="loadUsers"
          >
            <el-option
              v-for="role in roles"
              :key="role.id"
              :label="role.display_name"
              :value="role.id"
            />
          </el-select>
        </el-col>
        <el-col :span="4">
          <el-select
            v-model="filters.status"
            placeholder="状态筛选"
            clearable
            @change="loadUsers"
          >
            <el-option label="启用" value="active" />
            <el-option label="禁用" value="inactive" />
          </el-select>
        </el-col>
        <el-col :span="10" class="text-right">
          <el-button type="primary" @click="showAddDialog">
            <el-icon><Plus /></el-icon>创建子账号
          </el-button>
          <el-button @click="loadUsers">
            <el-icon><Refresh /></el-icon>刷新
          </el-button>
        </el-col>
      </el-row>
    </el-card>

    <!-- 用户列表 -->
    <el-card class="table-card" shadow="hover">
      <el-table v-loading="loading" :data="users" stripe style="width: 100%">
        <el-table-column type="index" width="50" />

        <el-table-column prop="username" label="用户名" min-width="120" />

        <el-table-column label="角色" width="120">
          <template #default="{ row }">
            <el-tag :type="row.role === 'admin' ? 'danger' : 'primary'">
              {{ row.role_name || row.role }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="department" label="部门" width="120">
          <template #default="{ row }">
            {{ row.department || "-" }}
          </template>
        </el-table-column>

        <el-table-column prop="email" label="邮箱" min-width="150">
          <template #default="{ row }">
            {{ row.email || "-" }}
          </template>
        </el-table-column>

        <el-table-column prop="phone" label="电话" width="120">
          <template #default="{ row }">
            {{ row.phone || "-" }}
          </template>
        </el-table-column>

        <el-table-column label="状态" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
              {{ row.is_active ? "启用" : "禁用" }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="最后登录" width="160">
          <template #default="{ row }">
            {{ formatDateTime(row.last_login) }}
          </template>
        </el-table-column>

        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="editUser(row)">
              <el-icon><Edit /></el-icon>编辑
            </el-button>
            <el-button link type="primary" @click="managePermissions(row)">
              <el-icon><Lock /></el-icon>权限
            </el-button>
            <el-button
              v-if="row.id !== currentUserId"
              link
              type="danger"
              @click="deleteUser(row)"
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

    <!-- 添加/编辑用户对话框 -->
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
        <el-form-item label="用户名" prop="username">
          <el-input
            v-model="formData.username"
            :disabled="dialogType === 'edit'"
            placeholder="请输入用户名"
          />
        </el-form-item>

        <el-form-item label="密码" prop="password" v-if="dialogType === 'add'">
          <el-input
            v-model="formData.password"
            type="password"
            show-password
            placeholder="请输入密码（至少6位）"
          />
        </el-form-item>

        <el-form-item
          label="重置密码"
          prop="reset_password"
          v-if="dialogType === 'edit'"
        >
          <el-input
            v-model="formData.reset_password"
            type="password"
            show-password
            placeholder="留空则不修改密码"
          />
        </el-form-item>

        <el-form-item label="角色" prop="role_id">
          <el-select v-model="formData.role_id" placeholder="请选择角色">
            <el-option
              v-for="role in roles"
              :key="role.id"
              :label="role.display_name"
              :value="role.id"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="部门" prop="department">
          <el-input v-model="formData.department" placeholder="请输入部门" />
        </el-form-item>

        <el-form-item label="邮箱" prop="email">
          <el-input v-model="formData.email" placeholder="请输入邮箱" />
        </el-form-item>

        <el-form-item label="电话" prop="phone">
          <el-input v-model="formData.phone" placeholder="请输入电话" />
        </el-form-item>

        <el-form-item label="状态" prop="is_active">
          <el-switch
            v-model="formData.is_active"
            active-text="启用"
            inactive-text="禁用"
          />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitForm" :loading="submitting">
          确定
        </el-button>
      </template>
    </el-dialog>

    <!-- 权限管理对话框 -->
    <el-dialog v-model="permissionDialogVisible" title="权限管理" width="800px">
      <div class="permission-container">
        <el-alert
          title="提示：用户可以拥有独立的权限设置，如果不设置则使用角色的默认权限"
          type="info"
          :closable="false"
          show-icon
          class="permission-alert"
        />

        <div class="permission-mode">
          <el-radio-group v-model="permissionMode">
            <el-radio label="inherit">继承角色权限</el-radio>
            <el-radio label="custom">自定义权限</el-radio>
          </el-radio-group>
        </div>

        <div v-if="permissionMode === 'custom'" class="permission-tree">
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
                @change="handlePermissionChange"
              >
                {{ perm.name }}
              </el-checkbox>
            </div>
          </div>
        </div>

        <div v-else class="inherit-info">
          <el-tag type="info" size="large">
            当前用户将使用角色「{{ currentRoleName }}」的权限
          </el-tag>
        </div>
      </div>

      <template #footer>
        <el-button @click="permissionDialogVisible = false">取消</el-button>
        <el-button
          type="primary"
          @click="savePermissions"
          :loading="savingPermissions"
        >
          保存权限
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  Search,
  Plus,
  Refresh,
  Edit,
  Delete,
  Lock,
} from "@element-plus/icons-vue";
import api from "./admin_api";
import { useUserStore } from "./admin_stores";
import { formatDateTime } from "./admin_timezone";

const userStore = useUserStore();
const currentUserId = computed(() => userStore.userInfo?.id);

const loading = ref(false);
const users = ref([]);
const roles = ref([]);
const total = ref(0);
const currentPage = ref(1);
const pageSize = ref(10);
const searchKeyword = ref("");
const filters = reactive({
  roleId: "",
  status: "",
});

const dialogVisible = ref(false);
const dialogType = ref("add");
const dialogTitle = ref("创建子账号");
const submitting = ref(false);
const formRef = ref(null);

const formData = reactive({
  username: "",
  password: "",
  reset_password: "",
  role_id: null,
  department: "",
  email: "",
  phone: "",
  is_active: true,
});

const formRules = {
  username: [
    { required: true, message: "请输入用户名", trigger: "blur" },
    { min: 3, max: 50, message: "用户名长度3-50字符", trigger: "blur" },
  ],
  password: [
    { required: true, message: "请输入密码", trigger: "blur" },
    { min: 6, message: "密码至少6位", trigger: "blur" },
  ],
  role_id: [{ required: true, message: "请选择角色", trigger: "change" }],
  email: [{ type: "email", message: "请输入正确的邮箱地址", trigger: "blur" }],
};

// 权限管理
const permissionDialogVisible = ref(false);
const savingPermissions = ref(false);
const currentUserForPermission = ref(null);
const permissionMode = ref("inherit");
const selectedPermissions = ref({});
const permissionGroups = ref([]);
const currentRoleName = ref("");

// 加载角色列表
const loadRoles = async () => {
  try {
    const response = await api.get("/roles");
    roles.value = response.items || [];
  } catch (error) {
    console.error("加载角色失败:", error);
  }
};

// 加载权限列表
const loadPermissions = async () => {
  try {
    const response = await api.get("/permissions");
    permissionGroups.value = Object.entries(response.groups || {}).map(
      ([key, value]) => ({
        name: value.name,
        permissions: value.permissions,
      }),
    );
  } catch (error) {
    console.error("加载权限列表失败:", error);
  }
};

// 加载用户列表
const loadUsers = async () => {
  loading.value = true;
  try {
    const params = {
      skip: (currentPage.value - 1) * pageSize.value,
      limit: pageSize.value,
    };

    if (searchKeyword.value) {
      params.search = searchKeyword.value;
    }
    if (filters.roleId) {
      params.role_id = filters.roleId;
    }
    if (filters.status === "active") {
      params.is_active = true;
    } else if (filters.status === "inactive") {
      params.is_active = false;
    }

    const response = await api.get("/users", { params });
    users.value = response.items || [];
    total.value = response.total || 0;
  } catch (error) {
    console.error("加载用户失败:", error);
    ElMessage.error("加载用户失败");
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
    loadUsers();
  }, 300);
};

// 分页
const handleSizeChange = (val) => {
  pageSize.value = val;
  currentPage.value = 1;
  loadUsers();
};

const handleCurrentChange = (val) => {
  currentPage.value = val;
  loadUsers();
};

// 显示添加对话框
const showAddDialog = () => {
  dialogType.value = "add";
  dialogTitle.value = "创建子账号";
  resetForm();
  dialogVisible.value = true;
};

// 编辑用户
const editUser = (row) => {
  dialogType.value = "edit";
  dialogTitle.value = "编辑用户";
  currentUserForPermission.value = row;
  formData.username = row.username;
  formData.role_id = row.role_id;
  formData.department = row.department || "";
  formData.email = row.email || "";
  formData.phone = row.phone || "";
  formData.is_active = row.is_active;
  formData.reset_password = "";
  dialogVisible.value = true;
};

// 权限管理
const managePermissions = async (row) => {
  currentUserForPermission.value = row;
  currentRoleName.value = row.role_name || row.role;

  try {
    const response = await api.get(`/users/${row.id}/permissions`);

    // ✅ 关键：使用 custom_permissions 来判断用户是否设置了自定义权限
    const customPerms = response.custom_permissions;
    const effectivePerms = response.effective_permissions;

    console.log("custom_permissions:", customPerms);
    console.log("effective_permissions:", effectivePerms);

    // 清空之前的选择
    selectedPermissions.value = {};

    // ✅ 判断用户是否设置了自定义权限
    if (
      customPerms &&
      customPerms.type === "custom" &&
      customPerms.permissions &&
      customPerms.permissions.length > 0
    ) {
      // 用户有自定义权限
      permissionMode.value = "custom";
      customPerms.permissions.forEach((code) => {
        selectedPermissions.value[code] = true;
      });
    } else {
      // 用户没有自定义权限，应该继承角色
      permissionMode.value = "inherit";
      // 不选中任何权限
    }

    permissionDialogVisible.value = true;
  } catch (error) {
    console.error("加载用户权限失败:", error);
    ElMessage.error("加载权限失败");
  }
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

// 权限变化
const handlePermissionChange = () => {
  // 触发视图更新
};

// 保存权限
const savePermissions = async () => {
  savingPermissions.value = true;
  try {
    console.log("permissionMode.value:", permissionMode.value);
    console.log("selectedPermissions:", selectedPermissions.value);
    let permissions = { type: "none" };

    if (permissionMode.value === "custom") {
      const selectedList = Object.entries(selectedPermissions.value)
        .filter(([_, selected]) => selected)
        .map(([code]) => code);
      console.log("selectedList:", selectedList);

      if (selectedList.length > 0) {
        permissions = { type: "custom", permissions: selectedList };
      }
    }

    console.log("最终发送的 permissions:", permissions);

    await api.put(
      `/users/${currentUserForPermission.value.id}/permissions`,
      permissions,
    );
    ElMessage.success("权限已保存");
    permissionDialogVisible.value = false;
  } catch (error) {
    console.error("保存权限失败:", error);
    ElMessage.error("保存失败");
  } finally {
    savingPermissions.value = false;
  }
};

// 删除用户
const deleteUser = (row) => {
  ElMessageBox.confirm(
    `确定要删除用户 "${row.username}" 吗？此操作不可恢复！`,
    "警告",
    {
      confirmButtonText: "确定",
      cancelButtonText: "取消",
      type: "warning",
    },
  ).then(async () => {
    try {
      await api.delete(`/users/${row.id}`);
      ElMessage.success("删除成功");
      if (users.value.length === 1 && currentPage.value > 1) {
        currentPage.value--;
      }
      loadUsers();
    } catch (error) {
      console.error("删除失败:", error);
      ElMessage.error(error.response?.data?.detail || "删除失败");
    }
  });
};

// 重置表单
const resetForm = () => {
  formData.username = "";
  formData.password = "";
  formData.reset_password = "";
  formData.role_id = null;
  formData.department = "";
  formData.email = "";
  formData.phone = "";
  formData.is_active = true;
  formRef.value?.clearValidate();
};

// 提交表单
// admin_Users.vue 中的 submitForm 函数
const submitForm = async () => {
  if (!formRef.value) return;

  await formRef.value.validate(async (valid) => {
    if (valid) {
      submitting.value = true;
      try {
        if (dialogType.value === "add") {
          // ✅ 确保发送的数据格式正确
          const userData = {
            username: formData.username,
            password: formData.password,
            role_id: formData.role_id ? Number(formData.role_id) : null, // ✅ 转为整数
            department: formData.department || null,
            email: formData.email || null,
            phone: formData.phone || null,
            is_active: formData.is_active,
            permissions: { type: "none" }, // ✅ 添加默认权限
          };

          console.log("发送数据:", userData); // ✅ 调试日志

          await api.post("/users", userData);
          ElMessage.success("用户创建成功");
        } else {
          // 编辑用户
          const updateData = {
            username: formData.username,
            role_id: formData.role_id ? Number(formData.role_id) : null,
            department: formData.department || null,
            email: formData.email || null,
            phone: formData.phone || null,
            is_active: formData.is_active,
          };
          if (formData.reset_password) {
            updateData.password = formData.reset_password;
          }

          await api.put(
            `/users/${currentUserForPermission.value?.id}`,
            updateData,
          );
          ElMessage.success("用户更新成功");
        }

        dialogVisible.value = false;
        loadUsers();
      } catch (error) {
        console.error("提交失败:", error);
        // ✅ 显示更详细的错误信息
        const errorMsg =
          error.response?.data?.detail || error.message || "提交失败";
        ElMessage.error(errorMsg);
      } finally {
        submitting.value = false;
      }
    }
  });
};

onMounted(() => {
  loadRoles();
  loadPermissions();
  loadUsers();
});
</script>

<style scoped>
.users-management {
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

.permission-container {
  max-height: 500px;
  overflow-y: auto;
}

.permission-alert {
  margin-bottom: 16px;
}

.permission-mode {
  margin-bottom: 20px;
  padding-bottom: 12px;
  border-bottom: 1px solid #ebeef5;
}

.permission-group {
  margin-bottom: 20px;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  overflow: hidden;
}

.group-header {
  padding: 12px 16px;
  background-color: #f5f7fa;
  border-bottom: 1px solid #ebeef5;
}

.group-permissions {
  padding: 12px 16px;
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
}

.inherit-info {
  text-align: center;
  padding: 40px;
}
</style>
