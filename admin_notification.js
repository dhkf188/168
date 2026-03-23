// admin_notification.js
import api from "./admin_api";
import { normalizeListResponse } from "./admin_response";

export const notificationApi = {
  // 获取通知列表
  async getNotifications(params = {}) {
    const response = await api.get("/notifications", { params });
    return normalizeListResponse(response);
  },

  // 获取未读通知数量
  async getUnreadCount() {
    const response = await api.get("/notifications/unread/count");
    return response;
  },

  // 标记通知为已读
  async markAsRead(id) {
    return api.put(`/notifications/${id}/read`);
  },

  // 标记所有通知为已读
  async markAllAsRead() {
    return api.put("/notifications/read-all");
  },

  // 删除通知
  async deleteNotification(id) {
    return api.delete(`/notifications/${id}`);
  },

  // 清空所有通知
  async clearAll() {
    return api.delete("/notifications/clear-all");
  }
};