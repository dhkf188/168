import axios from "axios";
import { ElMessage } from "element-plus";
import router from "./admin_router";
import {
  normalizeListResponse,
  normalizeObjectResponse,
} from "./admin_response";

// 创建axios实例
const getApiBaseUrl = () => {
  // 生产环境：使用当前域名
  if (import.meta.env.PROD) {
    return "/api"; // 使用相对路径，配合 Nginx 代理
  }
  // 开发环境：使用本地后端
  return "http://localhost:8000/api";
};

const api = axios.create({
  baseURL: getApiBaseUrl(),
  timeout: 30000,
});

// 请求拦截器
// 请求拦截器
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem("token");

    if (token) {
      // 确保 Authorization 头被正确设置
      config.headers.Authorization = `Bearer ${token}`;
    } else {
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

  updateCleanupPolicy(id, data) {
    return api.put(`/cleanup/policies/${id}`, data);
  },

  // ✅ 新增：手动全面清理
  manualCleanupAll() {
    return api.post("/cleanup/now");
  },

  // ✅ 新增：获取清理建议
  getCleanupRecommendations() {
    return api.get("/cleanup/recommendations");
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

  async getTrend(params = {}) {
    const response = await api.get("/browser/trend", { params });
    return response;
  },

  // ✅ 新增：获取浏览器分布
  async getDistribution(params = {}) {
    const response = await api.get("/browser/distribution", { params });
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
  async getTrend(params = {}) {
    const response = await api.get("/apps/trend", { params });
    return response;
  },
};

// ==================== 考勤管理API ====================
export const attendanceApi = {
  // 员工管理
  async getEmployees(params) {
    const response = await api.get("/attendance/employees", { params });
    return normalizeListResponse(response);
  },

  async createEmployee(data) {
    return api.post("/attendance/employees", data);
  },

  async updateEmployee(id, data) {
    return api.put(`/attendance/employees/${id}`, data);
  },

  async deleteEmployee(id) {
    return api.delete(`/attendance/employees/${id}`);
  },

  // 考勤记录
  async getRecords(params) {
    const response = await api.get("/attendance/records/batch", { params });
    return response;
  },

  async getRecordsByEmployees(yearMonth, employeeIds) {
    const response = await api.post("/attendance/records/batch-by-employees", {
      year_month: yearMonth,
      employee_ids: employeeIds,
    });
    return response;
  },

  async saveRecords(data) {
    return api.post("/attendance/records/batch", data);
  },

  // 考勤汇总
  async getSummary(params) {
    const response = await api.get("/attendance/summary", { params });
    return response;
  },

  // admin_api.js - 修改 getPerformance
  async getPerformance(params) {
    console.log("🔵 getPerformance 被调用，URL:", `/attendance/performance`);
    console.log("🔵 参数:", params);

    // 直接使用 api 实例
    const response = await api.get("/attendance/performance", { params });

    console.log("🔵 getPerformance 原始响应:", response);
    console.log("🔵 响应类型:", typeof response);
    console.log(
      "🔵 是否是 HTML?",
      typeof response === "string" && response.includes("<!doctype"),
    );

    // 如果返回的是 HTML，说明有问题
    if (typeof response === "string" && response.includes("<!doctype")) {
      console.error("❌ API 返回了 HTML，请检查后端路由");
      return { items: [], total: 0 };
    }

    return response;
  },

  async savePerformance(data) {
    return api.post("/attendance/performance/batch", data);
  },

  // 罚款管理
  async getPenaltyRecords(params) {
    const response = await api.get("/attendance/penalty/records", { params });
    return response;
  },

  async createPenaltyRecord(data) {
    return api.post("/attendance/penalty/record", data);
  },

  async deletePenaltyRecord(id) {
    return api.delete(`/attendance/penalty/records/${id}`);
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
