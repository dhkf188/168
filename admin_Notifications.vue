<template>
    <div class="notifications">
      <el-card shadow="hover">
        <template #header>
          <div class="card-header">
            <span>通知中心</span>
            <div class="header-actions">
              <el-button 
                v-if="notifications.length > 0"
                type="primary" 
                size="small"
                @click="markAllAsRead"
              >
                全部已读
              </el-button>
              <el-button 
                v-if="notifications.length > 0"
                type="danger" 
                size="small"
                @click="clearAllNotifications"
              >
                清空全部
              </el-button>
              <el-button @click="refresh" :loading="loading">
                刷新
              </el-button>
            </div>
          </div>
        </template>
  
        <el-timeline>
          <el-timeline-item
            v-for="notif in notifications"
            :key="notif.id"
            :type="getTimelineType(notif.type)"
            :color="notif.read ? '#909399' : undefined"
            :hollow="notif.read"
            :timestamp="formatFullDateTime(notif.created_at)"
          >
            <div class="timeline-content" :class="{ 'is-unread': !notif.read }">
              <div class="timeline-title">
                <strong>{{ notif.title }}</strong>
                <el-tag 
                  v-if="!notif.read" 
                  size="small" 
                  type="danger"
                  effect="light"
                >
                  未读
                </el-tag>
              </div>
              <div class="timeline-desc" v-if="notif.description">
                {{ notif.description }}
              </div>
              <div class="timeline-actions">
                <el-button 
                  v-if="!notif.read"
                  link 
                  type="primary" 
                  size="small"
                  @click="markAsRead(notif.id)"
                >
                  标记已读
                </el-button>
                <el-button 
                  link 
                  type="danger" 
                  size="small"
                  @click="deleteNotification(notif.id)"
                >
                  删除
                </el-button>
              </div>
            </div>
          </el-timeline-item>
        </el-timeline>
  
        <el-empty v-if="notifications.length === 0" description="暂无通知" />
  
        <div class="pagination" v-if="total > 0">
          <el-pagination
            v-model:current-page="currentPage"
            v-model:page-size="pageSize"
            :total="total"
            :page-sizes="[10, 20, 50, 100]"
            layout="total, sizes, prev, pager, next"
            @size-change="loadNotifications"
            @current-change="loadNotifications"
          />
        </div>
      </el-card>
    </div>
  </template>
  
  <script setup>
  import { ref, onMounted } from "vue";
  import { ElMessage, ElMessageBox } from "element-plus";
  import { notificationApi } from "./admin_notification";
  import { formatFullDateTime } from "./admin_timezone";
  
  const loading = ref(false);
  const notifications = ref([]);
  const total = ref(0);
  const currentPage = ref(1);
  const pageSize = ref(20);
  
  const loadNotifications = async () => {
    loading.value = true;
    try {
      const response = await notificationApi.getNotifications({
        skip: (currentPage.value - 1) * pageSize.value,
        limit: pageSize.value,
      });
      notifications.value = response.items || [];
      total.value = response.total || 0;
    } catch (error) {
      console.error("加载通知失败:", error);
      ElMessage.error("加载通知失败");
    } finally {
      loading.value = false;
    }
  };
  
  const refresh = () => {
    currentPage.value = 1;
    loadNotifications();
  };
  
  const markAsRead = async (id) => {
    try {
      await notificationApi.markAsRead(id);
      await loadNotifications();
    } catch (error) {
      console.error("标记已读失败:", error);
      ElMessage.error("操作失败");
    }
  };
  
  const markAllAsRead = async () => {
    try {
      await notificationApi.markAllAsRead();
      await loadNotifications();
      ElMessage.success("已全部标记为已读");
    } catch (error) {
      console.error("全部标记已读失败:", error);
      ElMessage.error("操作失败");
    }
  };
  
  const deleteNotification = async (id) => {
    try {
      await notificationApi.deleteNotification(id);
      await loadNotifications();
      ElMessage.success("通知已删除");
    } catch (error) {
      console.error("删除通知失败:", error);
      ElMessage.error("操作失败");
    }
  };
  
  const clearAllNotifications = () => {
    ElMessageBox.confirm("确定要清空所有通知吗？", "提示", {
      confirmButtonText: "确定",
      cancelButtonText: "取消",
      type: "warning",
    }).then(async () => {
      try {
        await notificationApi.clearAll();
        notifications.value = [];
        total.value = 0;
        ElMessage.success("通知已清空");
      } catch (error) {
        console.error("清空通知失败:", error);
        ElMessage.error("操作失败");
      }
    });
  };
  
  const getTimelineType = (type) => {
    const typeMap = {
      'info': 'info',
      'success': 'success',
      'warning': 'warning',
      'error': 'danger',
      '新客户端注册': 'success',
      '存储空间不足': 'danger',
      '备份完成': 'info'
    };
    return typeMap[type] || 'info';
  };
  
  onMounted(() => {
    loadNotifications();
  });
  </script>
  
  <style scoped>
  .notifications {
    padding: 20px;
  }
  
  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  
  .header-actions {
    display: flex;
    gap: 10px;
  }
  
  .timeline-content {
    padding: 8px;
    border-radius: 4px;
    transition: background-color 0.3s;
  }
  
  .timeline-content.is-unread {
    background-color: #ecf5ff;
  }
  
  .timeline-title {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 4px;
  }
  
  .timeline-desc {
    color: #666;
    margin-bottom: 8px;
    line-height: 1.6;
  }
  
  .timeline-actions {
    display: flex;
    gap: 8px;
  }
  
  .pagination {
    margin-top: 20px;
    text-align: right;
  }
  </style>