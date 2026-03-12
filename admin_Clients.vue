<template>
  <div class="clients">
    <!-- 统计卡片 -->
    <el-row :gutter="20" class="stats-row">
      <el-col :span="8">
        <el-card class="stat-card" shadow="hover">
          <div class="stat-content">
            <div class="stat-icon" style="background: #e6f7ff; color: #1890ff">
              <el-icon :size="24"><Monitor /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ totalClients }}</div>
              <div class="stat-label">总客户端数</div>
            </div>
          </div>
        </el-card>
      </el-col>

      <el-col :span="8">
        <el-card class="stat-card" shadow="hover">
          <div class="stat-content">
            <div class="stat-icon" style="background: #f6ffed; color: #52c41a">
              <el-icon :size="24"><Connection /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ onlineClients }}</div>
              <div class="stat-label">在线客户端</div>
            </div>
          </div>
        </el-card>
      </el-col>

      <el-col :span="8">
        <el-card class="stat-card" shadow="hover">
          <div class="stat-content">
            <div class="stat-icon" style="background: #fff7e6; color: #fa8c16">
              <el-icon :size="24"><Clock /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ offlineClients }}</div>
              <div class="stat-label">离线客户端</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 客户端列表 -->
    <el-card class="table-card" shadow="hover">
      <template #header>
        <div class="card-header">
          <span>客户端列表</span>
          <el-switch
            v-model="showOnlineOnly"
            active-text="仅显示在线"
            inactive-text="全部"
            @change="loadClients"
          />
        </div>
      </template>

      <el-table v-loading="loading" :data="clients" stripe style="width: 100%">
        <el-table-column type="index" width="50" />

        <el-table-column label="客户端ID" min-width="200">
          <template #default="{ row }">
            <div class="client-info">
              <el-tag
                :type="row.is_online ? 'success' : 'info'"
                size="small"
                effect="dark"
                circle
              >
                ●
              </el-tag>
              <span class="client-id">{{ row.client_id }}</span>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="计算机名" width="150">
          <template #default="{ row }">
            {{ row.computer_name || "-" }}
          </template>
        </el-table-column>

        <el-table-column label="Windows用户" width="150">
          <template #default="{ row }">
            {{ row.windows_user || "-" }}
          </template>
        </el-table-column>

        <el-table-column label="IP地址" width="150">
          <template #default="{ row }">
            {{ row.ip_address || "-" }}
          </template>
        </el-table-column>

        <el-table-column label="操作系统" width="150">
          <template #default="{ row }">
            {{ row.os_version || "-" }}
          </template>
        </el-table-column>

        <el-table-column label="最后在线" width="180">
          <template #default="{ row }">
            <span :class="{ 'text-danger': !row.is_online }">
              {{ formatRelativeTime(row.last_seen) }}
            </span>
          </template>
        </el-table-column>

        <el-table-column label="客户端版本" width="120">
          <template #default="{ row }">
            <el-tag size="small">{{ row.client_version || "未知" }}</el-tag>
          </template>
        </el-table-column>

        <el-table-column label="配置" width="100" align="center">
          <template #default="{ row }">
            <el-button link type="primary" @click="showConfig(row)">
              <el-icon><Setting /></el-icon>
            </el-button>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button
              link
              type="primary"
              @click="viewScreenshots(row.client_id)"
            >
              <el-icon><Picture /></el-icon>截图
            </el-button>
            <el-button link type="danger" @click="deleteClient(row)">
              <el-icon><Delete /></el-icon>删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 - 修复后的版本 -->
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

    <!-- 客户端配置对话框 -->
    <el-dialog v-model="configVisible" title="客户端配置" width="500px">
      <el-form :model="currentConfig" label-width="100px">
        <el-form-item label="截图间隔">
          <el-input-number
            v-model="currentConfig.interval"
            :min="10"
            :max="3600"
          />
          <span class="unit">秒</span>
        </el-form-item>

        <el-form-item label="图片质量">
          <el-slider
            v-model="currentConfig.quality"
            :min="10"
            :max="100"
            show-input
          />
        </el-form-item>

        <el-form-item label="图片格式">
          <el-radio-group v-model="currentConfig.format">
            <el-radio label="webp">WebP</el-radio>
            <el-radio label="jpg">JPEG</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="心跳保活">
          <el-switch v-model="currentConfig.enable_heartbeat" />
        </el-form-item>

        <el-form-item label="批量上传">
          <el-switch v-model="currentConfig.enable_batch_upload" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="configVisible = false">取消</el-button>
        <el-button type="primary" @click="saveConfig" :loading="savingConfig">
          保存配置
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
// ===== 导入统一的时间工具 =====
import {
  formatRelativeTime,
  formatDateTime as formatDateTimeUtil,
} from "./admin_timezone";
// ============================

import { ref, computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  Monitor,
  Connection,
  Clock,
  Setting,
  Picture,
  Delete,
} from "@element-plus/icons-vue";
import { clientApi } from "./admin_api";

const router = useRouter();
const loading = ref(false);
const clients = ref([]);
const total = ref(0);
const currentPage = ref(1);
const pageSize = ref(10);
const showOnlineOnly = ref(false);

const configVisible = ref(false);
const savingConfig = ref(false);
const currentClient = ref(null);
const currentConfig = ref({
  interval: 300,
  quality: 80,
  format: "webp",
  enable_heartbeat: true,
  enable_batch_upload: true,
});

// 统计（这些computed属性基于当前显示的数据，保持不变）
const totalClients = computed(() => clients.value.length);
const onlineClients = computed(
  () => clients.value.filter((c) => c.is_online).length,
);
const offlineClients = computed(
  () => clients.value.filter((c) => !c.is_online).length,
);

// ===== 修复：分页处理函数 =====
const handleSizeChange = (val) => {
  pageSize.value = val;
  currentPage.value = 1; // 改变每页数量时，回到第一页
  loadClients();
};

const handleCurrentChange = (val) => {
  currentPage.value = val;
  loadClients();
};
// ============================

// ===== 修复：加载客户端列表，正确处理总记录数 =====
// ===== 加载客户端列表（使用统一响应处理）=====
const loadClients = async () => {
  loading.value = true;
  try {
    const params = {
      skip: (currentPage.value - 1) * pageSize.value,
      limit: pageSize.value,
    };

    if (showOnlineOnly.value) {
      params.online_only = true;
    }

    // ✅ 调用修改后的API，返回统一格式
    const response = await clientApi.getClients(params);

    // ✅ 直接使用标准化的响应
    // response 已经是 { items: [], total: 100, skip: 0, limit: 10, has_more: true } 格式
    clients.value = response.items || [];
    total.value = response.total || 0;

    console.log(`客户端列表加载成功: ${clients.value.length}/${total.value}`);
  } catch (error) {
    console.error("加载客户端列表失败:", error);
    ElMessage.error(
      "加载客户端列表失败: " + (error.response?.data?.detail || error.message),
    );
    clients.value = [];
    total.value = 0;
  } finally {
    loading.value = false;
  }
};
// ============================

// 显示配置
const showConfig = (client) => {
  currentClient.value = client;
  currentConfig.value = { ...client.config };
  configVisible.value = true;
};

// 保存配置
const saveConfig = async () => {
  savingConfig.value = true;
  try {
    // TODO: 调用更新配置API
    ElMessage.success("配置已保存");
    configVisible.value = false;
  } catch (error) {
    console.error("保存配置失败:", error);
  } finally {
    savingConfig.value = false;
  }
};

// 查看截图
const viewScreenshots = (clientId) => {
  router.push(`/screenshots?client_id=${clientId}`);
};

// 删除客户端
const deleteClient = (client) => {
  ElMessageBox.confirm(`确定要删除客户端 "${client.client_id}" 吗？`, "警告", {
    confirmButtonText: "确定",
    cancelButtonText: "取消",
    type: "warning",
  }).then(async () => {
    try {
      await clientApi.deleteClient(client.client_id);
      ElMessage.success("删除成功");
      // 删除后重新加载当前页
      loadClients();
    } catch (error) {
      console.error("删除失败:", error);
    }
  });
};

onMounted(() => {
  loadClients();
});
</script>

<style scoped>
.clients {
  padding: 20px;
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

.table-card {
  margin-top: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.client-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.client-id {
  font-family: monospace;
  font-size: 13px;
}

.pagination {
  margin-top: 20px;
  text-align: right;
}

.text-danger {
  color: #ff4d4f;
}

.unit {
  margin-left: 8px;
  color: #999;
}
</style>
