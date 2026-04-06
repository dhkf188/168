<!-- admin_SiteManagement.vue -->
<template>
  <div class="site-management">
    <el-tabs v-model="activeTab">
      <el-tab-pane label="出款管理" name="sites">
        <div class="site-tab">
          <el-card class="toolbar" shadow="hover">
            <el-row :gutter="20" align="middle">
              <el-col :span="12">
                <el-switch
                  v-model="filterActive"
                  active-text="显示启用"
                  inactive-text="全部"
                  @change="loadSites"
                />
              </el-col>
              <el-col :span="12" class="text-right">
                <el-button type="primary" @click="showAddSiteDialog">
                  <el-icon><Plus /></el-icon>新增站点
                </el-button>
                <el-button @click="loadSites">
                  <el-icon><Refresh /></el-icon>刷新
                </el-button>
              </el-col>
            </el-row>
          </el-card>

          <el-card class="table-card" shadow="hover">
            <el-table
              v-loading="siteLoading"
              :data="sites"
              stripe
              style="width: 100%"
            >
              <el-table-column type="index" width="50" />
              <el-table-column prop="code" label="站点代码" width="120">
                <template #default="{ row }">
                  <el-tag :type="row.is_active ? 'success' : 'info'">{{
                    row.code
                  }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="name" label="站点名称" min-width="150" />
              <el-table-column label="员工数" width="100" align="center">
                <template #default="{ row }">
                  <el-tag type="info" size="small">{{
                    row.account_count || 0
                  }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="数据条数" width="100" align="center">
                <template #default="{ row }">
                  <el-tag type="primary" size="small">{{
                    row.data_count || 0
                  }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column
                prop="sort_order"
                label="排序"
                width="80"
                align="center"
              />
              <el-table-column label="状态" width="80" align="center">
                <template #default="{ row }">
                  <el-tag
                    :type="row.is_active ? 'success' : 'info'"
                    size="small"
                  >
                    {{ row.is_active ? "启用" : "禁用" }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="150" fixed="right">
                <template #default="{ row }">
                  <el-button link type="primary" @click="editSite(row)">
                    <el-icon><Edit /></el-icon>编辑
                  </el-button>
                  <el-button link type="danger" @click="deleteSite(row)">
                    <el-icon><Delete /></el-icon>删除
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-card>
        </div>
      </el-tab-pane>

      <el-tab-pane label="员工账号" name="accounts">
        <div class="accounts-tab">
          <el-card class="toolbar" shadow="hover">
            <el-row :gutter="20" align="middle">
              <!-- 站点选择 -->
              <el-col :span="6">
                <el-select
                  v-model="filterSiteId"
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

              <!-- 搜索框 -->
              <el-col :span="6">
                <el-input
                  v-model="filterAccountName"
                  placeholder="搜索账号"
                  clearable
                  @input="handleSearch"
                />
              </el-col>

              <!-- 班次筛选 -->
              <el-col :span="4">
                <el-select
                  v-model="filterShift"
                  placeholder="班次筛选"
                  clearable
                  @change="handleFilterChange"
                >
                  <el-option label="A班" value="day" />
                  <el-option label="B班" value="night" />
                </el-select>
              </el-col>

              <!-- 按钮区域 - 右对齐 -->
              <el-col :span="8" class="text-right">
                <el-button type="primary" @click="showAddAccountDialog">
                  <el-icon><Plus /></el-icon>添加员工
                </el-button>
                <el-button @click="loadAccounts">
                  <el-icon><Refresh /></el-icon>刷新
                </el-button>
              </el-col>
            </el-row>
          </el-card>

          <el-card class="table-card" shadow="hover">
            <el-table
              v-loading="accountLoading"
              :data="accounts"
              stripe
              style="width: 100%"
            >
              <el-table-column type="index" width="50" />
              <el-table-column prop="site_code" label="站点" width="120">
                <template #default="{ row }">
                  <el-tag size="small">{{ row.site_code }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="name" label="员工姓名" min-width="120" />
              <el-table-column
                prop="account_name"
                label="后台账号"
                min-width="150"
              >
                <template #default="{ row }">
                  <el-tag type="primary">{{ row.account_name }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="班次" width="80" align="center">
                <template #default="{ row }">
                  <el-tag
                    :type="row.shift === 'day' ? 'success' : 'warning'"
                    size="small"
                  >
                    {{ row.shift === "day" ? "A班" : "B班" }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="数据条数" width="100" align="center">
                <template #default="{ row }">
                  <el-tag type="info" size="small">{{
                    row.data_count || 0
                  }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="状态" width="80" align="center">
                <template #default="{ row }">
                  <el-tag
                    :type="row.is_active ? 'success' : 'info'"
                    size="small"
                  >
                    {{ row.is_active ? "启用" : "禁用" }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="150" fixed="right">
                <template #default="{ row }">
                  <el-button link type="primary" @click="editAccount(row)">
                    <el-icon><Edit /></el-icon>编辑
                  </el-button>
                  <el-button link type="danger" @click="deleteAccount(row)">
                    <el-icon><Delete /></el-icon>删除
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
            <div class="pagination" v-if="accountTotal > 0">
              <el-pagination
                v-model:current-page="accountPage"
                v-model:page-size="accountPageSize"
                :page-sizes="[10, 20, 50, 100]"
                :total="accountTotal"
                layout="total, sizes, prev, pager, next, jumper"
                @size-change="handleAccountSizeChange"
                @current-change="handleAccountCurrentChange"
              />
            </div>
          </el-card>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- 站点对话框 -->
    <el-dialog
      v-model="siteDialogVisible"
      :title="siteDialogTitle"
      width="500px"
    >
      <el-form
        ref="siteFormRef"
        :model="siteFormData"
        :rules="siteFormRules"
        label-width="80px"
      >
        <el-form-item label="站点代码" prop="code">
          <el-input
            v-model="siteFormData.code"
            placeholder="如: 25S"
            :disabled="isEditSite"
          />
        </el-form-item>
        <el-form-item label="站点名称" prop="name">
          <el-input v-model="siteFormData.name" placeholder="如: 25S站点" />
        </el-form-item>
        <el-form-item label="排序" prop="sort_order">
          <el-input-number
            v-model="siteFormData.sort_order"
            :min="0"
            :max="100"
          />
        </el-form-item>
        <el-form-item label="状态" prop="is_active">
          <el-switch
            v-model="siteFormData.is_active"
            active-text="启用"
            inactive-text="禁用"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="siteDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitSite" :loading="siteSubmitting"
          >确定</el-button
        >
      </template>
    </el-dialog>

    <!-- 员工账号对话框 -->
    <el-dialog
      v-model="accountDialogVisible"
      :title="accountDialogTitle"
      width="500px"
    >
      <el-form
        ref="accountFormRef"
        :model="accountFormData"
        :rules="accountFormRules"
        label-width="80px"
      >
        <el-form-item label="站点" prop="site_id">
          <el-select
            v-model="accountFormData.site_id"
            placeholder="请选择站点"
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
        <el-form-item label="员工姓名" prop="name">
          <el-input
            v-model="accountFormData.name"
            placeholder="请输入员工姓名"
          />
        </el-form-item>
        <el-form-item label="后台账号" prop="account_name">
          <el-input
            v-model="accountFormData.account_name"
            placeholder="如: dhcs1919"
          />
        </el-form-item>

        <el-form-item label="班次" prop="shift">
          <el-radio-group v-model="accountFormData.shift">
            <el-radio value="day">🌞 A班 </el-radio>
            <el-radio value="night">🌙 B班</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="状态" prop="is_active">
          <el-switch
            v-model="accountFormData.is_active"
            active-text="启用"
            inactive-text="禁用"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="accountDialogVisible = false">取消</el-button>
        <el-button
          type="primary"
          @click="submitAccount"
          :loading="accountSubmitting"
          >确定</el-button
        >
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Plus, Refresh, Edit, Delete } from "@element-plus/icons-vue";
import api from "./admin_api";

// 选项卡
const activeTab = ref("sites");

// 站点数据
const siteLoading = ref(false);
const sites = ref([]);
const filterActive = ref(true);

// 员工账号数据
const accountLoading = ref(false);
const accounts = ref([]);
const filterSiteId = ref("");
const filterAccountName = ref("");

// 站点对话框
const siteDialogVisible = ref(false);
const siteDialogTitle = ref("新增站点");
const isEditSite = ref(false);
const siteSubmitting = ref(false);
const siteFormRef = ref(null);
const siteFormData = ref({
  id: null,
  code: "",
  name: "",
  sort_order: 0,
  is_active: true,
});
const siteFormRules = {
  code: [{ required: true, message: "请输入站点代码", trigger: "blur" }],
  name: [{ required: true, message: "请输入站点名称", trigger: "blur" }],
};

// 员工账号对话框
const accountDialogVisible = ref(false);
const accountDialogTitle = ref("添加员工");
const isEditAccount = ref(false);
const accountSubmitting = ref(false);
const accountFormRef = ref(null);
const accountFormData = ref({
  id: null,
  site_id: "",
  name: "",
  account_name: "",
  shift: "day",
  is_active: true,
});
const accountFormRules = {
  site_id: [{ required: true, message: "请选择站点", trigger: "change" }],
  name: [{ required: true, message: "请输入员工姓名", trigger: "blur" }],
  account_name: [
    { required: true, message: "请输入后台账号", trigger: "blur" },
    { min: 2, message: "账号至少2个字符", trigger: "blur" },
  ],
  shift: [{ required: true, message: "请选择班次", trigger: "change" }],
};

// 加载站点列表
const loadSites = async () => {
  siteLoading.value = true;
  try {
    const params = {};
    if (filterActive.value) params.is_active = true;
    const response = await api.get("/site-stats/sites", { params });
    sites.value = response.items || [];
  } catch (error) {
    console.error("加载站点失败:", error);
    ElMessage.error("加载站点失败");
  } finally {
    siteLoading.value = false;
  }
};
const filterShift = ref("");

// 加载员工账号列表（支持分页）
const loadAccounts = async () => {
  accountLoading.value = true;
  try {
    const params = {
      skip: (accountPage.value - 1) * accountPageSize.value,
      limit: accountPageSize.value,
    };
    if (filterSiteId.value) params.site_id = filterSiteId.value;
    if (filterAccountName.value) params.account_name = filterAccountName.value;
    if (filterShift.value) params.shift = filterShift.value;

    const response = await api.get("/site-stats/employee-accounts", { params });
    accounts.value = response.items || [];
    accountTotal.value = response.total || 0;
  } catch (error) {
    console.error("加载员工账号失败:", error);
    ElMessage.error("加载员工账号失败");
  } finally {
    accountLoading.value = false;
  }
};

const accountPage = ref(1);
const accountPageSize = ref(20);
const accountTotal = ref(0);

// 分页大小变化
const handleAccountSizeChange = (val) => {
  accountPageSize.value = val;
  accountPage.value = 1;
  loadAccounts();
};

// 当前页变化
const handleAccountCurrentChange = (val) => {
  accountPage.value = val;
  loadAccounts();
};

// 站点筛选变化时重置分页
const handleSiteFilterChange = () => {
  accountPage.value = 1;
  loadAccounts();
};

// 搜索防抖
let searchTimer;
const handleSearch = () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    accountPage.value = 1;
    loadAccounts();
  }, 300);
};
const handleFilterChange = () => {
  accountPage.value = 1;
  loadAccounts();
};

// ==================== 站点操作 ====================
const showAddSiteDialog = () => {
  isEditSite.value = false;
  siteDialogTitle.value = "新增站点";
  siteFormData.value = {
    id: null,
    code: "",
    name: "",
    sort_order: 0,
    is_active: true,
  };
  siteDialogVisible.value = true;
};

const editSite = (row) => {
  isEditSite.value = true;
  siteDialogTitle.value = "编辑站点";
  siteFormData.value = { ...row };
  siteDialogVisible.value = true;
};

const deleteSite = (row) => {
  ElMessageBox.confirm(`确定要删除站点 "${row.code}" 吗？`, "警告", {
    confirmButtonText: "确定",
    cancelButtonText: "取消",
    type: "warning",
  }).then(async () => {
    try {
      await api.delete(`/site-stats/sites/${row.id}`);
      ElMessage.success("删除成功");
      loadSites();
      loadAccounts();
    } catch (error) {
      console.error("删除失败:", error);
      ElMessage.error(error.response?.data?.detail || "删除失败");
    }
  });
};

const submitSite = async () => {
  if (!siteFormRef.value) return;
  await siteFormRef.value.validate(async (valid) => {
    if (valid) {
      siteSubmitting.value = true;
      try {
        if (isEditSite.value) {
          await api.put(
            `/site-stats/sites/${siteFormData.value.id}`,
            siteFormData.value,
          );
          ElMessage.success("站点更新成功");
        } else {
          await api.post("/site-stats/sites", siteFormData.value);
          ElMessage.success("站点创建成功");
        }
        siteDialogVisible.value = false;
        loadSites();
        loadAccounts();
      } catch (error) {
        console.error("提交失败:", error);
        ElMessage.error(error.response?.data?.detail || "提交失败");
      } finally {
        siteSubmitting.value = false;
      }
    }
  });
};

// ==================== 员工账号操作 ====================
const showAddAccountDialog = () => {
  isEditAccount.value = false;
  accountDialogTitle.value = "添加员工";
  accountFormData.value = {
    id: null,
    site_id: "",
    name: "",
    account_name: "",
    shift: "day",
    is_active: true,
  };
  accountDialogVisible.value = true;
};

const editAccount = (row) => {
  isEditAccount.value = true;
  accountDialogTitle.value = "编辑员工";
  accountFormData.value = { ...row };
  accountDialogVisible.value = true;
};

const deleteAccount = (row) => {
  ElMessageBox.confirm(
    `确定要删除员工 "${row.name}" (账号: ${row.account_name}) 吗？`,
    "警告",
    {
      confirmButtonText: "确定",
      cancelButtonText: "取消",
      type: "warning",
    },
  ).then(async () => {
    try {
      await api.delete(`/site-stats/employee-accounts/${row.id}`);
      ElMessage.success("删除成功");
      loadAccounts();
    } catch (error) {
      console.error("删除失败:", error);
      ElMessage.error(error.response?.data?.detail || "删除失败");
    }
  });
};

// admin_SiteManagement.vue - 修改 submitAccount 函数中的提交数据

const submitAccount = async () => {
  if (!accountFormRef.value) return;
  await accountFormRef.value.validate(async (valid) => {
    if (valid) {
      accountSubmitting.value = true;
      try {
        if (isEditAccount.value) {
          await api.put(
            `/site-stats/employee-accounts/${accountFormData.value.id}`,
            {
              name: accountFormData.value.name,
              account_name: accountFormData.value.account_name,
              shift: accountFormData.value.shift, // ===== 新增 =====
              is_active: accountFormData.value.is_active,
            },
          );
          ElMessage.success("员工更新成功");
        } else {
          await api.post("/site-stats/employee-accounts", {
            site_id: accountFormData.value.site_id,
            name: accountFormData.value.name,
            account_name: accountFormData.value.account_name,
            shift: accountFormData.value.shift, // ===== 新增 =====
          });
          ElMessage.success("员工添加成功");
        }
        accountDialogVisible.value = false;
        loadAccounts();
      } catch (error) {
        console.error("提交失败:", error);
        ElMessage.error(error.response?.data?.detail || "提交失败");
      } finally {
        accountSubmitting.value = false;
      }
    }
  });
};

onMounted(() => {
  loadSites();
  loadAccounts();
});
</script>

<style scoped>
.site-management {
  padding: 20px;
}
.toolbar {
  margin-bottom: 20px;
}
.table-card {
  min-height: 400px;
}
.text-right {
  text-align: right;
}
</style>
