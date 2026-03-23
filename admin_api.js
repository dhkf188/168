import axios from "axios";
import { ElMessage } from "element-plus";
import router from "./admin_router";
import {
  normalizeListResponse,
  normalizeObjectResponse,
} from "./admin_response";

// 创建axios实例
const api = axios.create({
  baseURL: "/api",
  timeout: 30000,
});

// 请求拦截器
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem("token");
    if (token) {
      // 检查是否已经存在 Authorization 头
      const existingAuth = config.headers.Authorization;
      if (!existingAuth) {
        // 如果没有，才添加
        config.headers.Authorization = `Bearer ${token}`;
        console.log(
          `📡 请求: ${config.method.toUpperCase()} ${config.url}`,
          "已添加token",
        );
      } else {
        console.log(
          `📡 请求: ${config.method.toUpperCase()} ${config.url}`,
          "已有token，跳过",
        );
      }
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  },
);

// 响应拦截器 - 统一处理
api.interceptors.response.use(
  (response) => {
    // 对于列表请求，保留原始数据以便后续标准化处理
    // 判断是否为列表请求（通过URL和HTTP方法）
    const isListRequest =
      response.config.method.toLowerCase() === "get" &&
      ((response.config.url.includes("/employees") &&
        !response.config.url.match(/\/employees\/[^\/]+\/?$/)) ||
        response.config.url.includes("/clients") ||
        response.config.url.includes("/screenshots") ||
        response.config.url.includes("/activities") ||
        response.config.url.includes("/dates"));

    if (isListRequest) {
      // 为列表响应添加标记，但不修改数据结构
      return {
        ...response.data,
        _isListResponse: true,
      };
    }

    return response.data;
  },
  (error) => {
    if (error.response) {
      switch (error.response.status) {
        case 401:
          ElMessage.error("登录已过期，请重新登录");
          localStorage.removeItem("token");
          localStorage.removeItem("user");
          router.push("/login");
          break;
        case 403:
          ElMessage.error("没有权限执行此操作");
          break;
        case 404:
          ElMessage.error("请求的资源不存在");
          break;
        case 422:
          ElMessage.error("数据验证失败");
          break;
        case 500:
          ElMessage.error("服务器内部错误");
          break;
        default:
          ElMessage.error(error.response.data?.detail || "请求失败");
      }
    } else if (error.request) {
      ElMessage.error("网络连接失败，请检查网络");
    } else {
      ElMessage.error("请求配置错误");
    }
    return Promise.reject(error);
  },
);

// ==================== 认证相关API（保持不变）====================
export const authApi = {
  login(username, password) {
    const formData = new FormData();
    formData.append("username", username);
    formData.append("password", password);
    return api.post("/auth/login", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },

  register(userData) {
    return api.post("/auth/register", userData);
  },

  getCurrentUser() {
    return api.get("/auth/me");
  },
};

// ==================== 员工相关API（统一处理）====================
export const employeeApi = {
  // ✅ 统一处理列表响应
  async getEmployees(params) {
    const response = await api.get("/employees", { params });
    return normalizeListResponse(response);
  },

  // ✅ 统一处理单个对象
  async getEmployee(id) {
    const encodedId = encodeURIComponent(id);
    const response = await api.get(`/employees/${encodedId}`);
    return normalizeObjectResponse(response, null);
  },

  createEmployee(data) {
    return api.post("/employees", data);
  },

  updateEmployee(id, data) {
    const encodedId = encodeURIComponent(id);
    console.log("原始ID:", id);
    console.log("编码后:", encodedId);
    return api.put(`/employees/${encodedId}`, data);
  },

  deleteEmployee(id) {
    const encodedId = encodeURIComponent(id);
    return api.delete(`/employees/${encodedId}`);
  },

  // ✅ 统一处理日期列表响应
  async getEmployeeDates(id) {
    const encodedId = encodeURIComponent(id);
    const response = await api.get(`/employees/${encodedId}/dates`);
    return normalizeListResponse(response);
  },
};

// ==================== 截图相关API（统一处理）====================
export const screenshotApi = {
  // ✅ 统一处理列表响应
  async getScreenshots(params) {
    const response = await api.get("/screenshots", { params });
    return normalizeListResponse(response);
  },

  // ✅ 统一处理列表响应
  async getScreenshotsByDate(employeeId, date) {
    const response = await api.get(`/screenshots/${employeeId}/${date}`);
    return normalizeListResponse(response);
  },

  // ✅ 统一处理列表响应
  async getRecentScreenshots(limit = 20) {
    const response = await api.get("/screenshots/recent", {
      params: { limit },
    });
    return normalizeListResponse(response);
  },
};

// ==================== 客户端相关API（统一处理）====================
export const clientApi = {
  // ✅ 统一处理列表响应
  async getClients(params) {
    const response = await api.get("/clients", { params });
    return normalizeListResponse(response);
  },

  // ✅ 统一处理列表响应
  async getOnlineClients() {
    const response = await api.get("/clients/online");
    return normalizeListResponse(response);
  },

  deleteClient(id) {
    return api.delete(`/clients/${id}`);
  },
};

// ==================== 统计相关API（统一处理）====================
export const statsApi = {
  getStats() {
    return api.get("/stats");
  },

  // ✅ 统一处理列表响应
  async getActivities(limit = 50) {
    const response = await api.get("/activities", { params: { limit } });
    return normalizeListResponse(response);
  },
};

// ==================== 清理相关API（保持不变）====================
export const cleanupApi = {
  manualCleanup() {
    return api.post("/cleanup");
  },

  getCleanupStatus() {
    return api.get("/cleanup/status");
  },
};

// ==================== 通知相关API（新增）====================
export const notificationApi = {
  async getNotifications(params = {}) {
    const response = await api.get("/notifications", { params });
    return normalizeListResponse(response);
  },

  async getUnreadCount() {
    const response = await api.get("/notifications/unread/count");
    return response;
  },

  async markAsRead(id) {
    return api.put(`/notifications/${id}/read`);
  },

  async markAllAsRead() {
    return api.put("/notifications/read-all");
  },

  async deleteNotification(id) {
    return api.delete(`/notifications/${id}`);
  },

  async clearAll() {
    return api.delete("/notifications/clear-all");
  },

  async batchDelete(ids) {
    return api.post("/notifications/batch-delete", { ids });
  },

  async batchMarkAsRead(ids) {
    return api.post("/notifications/batch-read", { ids });
  },
};
// ==================== 浏览器历史API ====================
export const browserApi = {
  // 上传浏览器历史（客户端用）
  async uploadHistory(data) {
    return api.post("/browser/history", data);
  },

  // 获取浏览器历史
  async getHistory(params = {}) {
    const response = await api.get("/browser/history", { params });
    return normalizeListResponse(response);
  },

  // 获取浏览器统计
  async getStats(params = {}) {
    const response = await api.get("/browser/stats", { params });
    return response;
  },
};

// ==================== 软件使用API ====================
export const appApi = {
  // 上传软件使用（客户端用）
  async uploadUsage(data) {
    return api.post("/apps/usage", data);
  },

  // 获取软件使用记录
  async getUsage(params = {}) {
    const response = await api.get("/apps/usage", { params });
    return normalizeListResponse(response);
  },

  // 获取软件统计
  async getStats(params = {}) {
    const response = await api.get("/apps/stats", { params });
    return response;
  },
};

// ==================== 文件操作API ====================
export const fileApi = {
  // 上传文件操作（客户端用）
  async uploadOperations(data) {
    return api.post("/files/operations", data);
  },

  // 获取文件操作记录
  async getOperations(params = {}) {
    const response = await api.get("/files/operations", { params });
    return normalizeListResponse(response);
  },

  // 获取文件统计
  async getStats(params = {}) {
    const response = await api.get("/files/stats", { params });
    return response;
  },
};

export default api;
