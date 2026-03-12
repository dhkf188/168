// admin_response.js
/**
 * 统一的API响应处理工具
 * 确保所有列表接口返回格式一致：{ items, total, skip, limit, has_more }
 */

/**
 * 统一处理列表响应
 * @param {any} response - API原始响应
 * @returns {Object} 标准化的响应对象
 */
export const normalizeListResponse = (response) => {
  // 如果已经是标准格式 { items, total }
  if (response && typeof response === "object") {
    // 新格式：{ items: [], total: 100, skip: 0, limit: 10, has_more: true }
    if (response.items !== undefined) {
      return {
        items: response.items || [],
        total: response.total || 0,
        skip: response.skip || 0,
        limit: response.limit || response.items?.length || 0,
        has_more:
          response.has_more !== undefined
            ? response.has_more
            : (response.items?.length || 0) < (response.total || 0),
        // 保留原始数据中的其他字段
        ...response,
      };
    }

    // 如果是数组（旧格式）
    if (Array.isArray(response)) {
      return {
        items: response,
        total: response.length,
        skip: 0,
        limit: response.length,
        has_more: false,
      };
    }

    // 特殊格式：{ dates: [...] } 或类似
    if (response.dates && Array.isArray(response.dates)) {
      return {
        items: response.dates,
        total: response.total || response.dates.length,
        skip: 0,
        limit: response.dates.length,
        has_more: false,
        ...response,
      };
    }
  }

  // 默认空响应
  return {
    items: [],
    total: 0,
    skip: 0,
    limit: 0,
    has_more: false,
  };
};

/**
 * 统一处理单个对象响应
 * @param {any} response - API原始响应
 * @param {any} defaultValue - 默认值
 * @returns {any} 标准化的对象
 */
export const normalizeObjectResponse = (response, defaultValue = null) => {
  if (response === null || response === undefined) return defaultValue;
  if (typeof response === "object" && response._isListResponse) {
    delete response._isListResponse;
  }
  return response;
};

/**
 * 从列表响应中提取数据项
 * @param {Object} response - 标准化后的响应
 * @returns {Array} 数据项数组
 */
export const extractItems = (response) => {
  if (!response) return [];
  if (Array.isArray(response)) return response;
  if (response.items) return response.items;
  return [];
};

/**
 * 从列表响应中提取总数
 * @param {Object} response - 标准化后的响应
 * @returns {number} 总数
 */
export const extractTotal = (response) => {
  if (!response) return 0;
  if (response.total !== undefined) return response.total;
  if (Array.isArray(response)) return response.length;
  if (response.items) return response.items.length;
  return 0;
};

/**
 * 统一处理错误响应
 * @param {Error} error - 错误对象
 * @returns {Object} 标准化的错误信息
 */
export const normalizeError = (error) => {
  const detail = error.response?.data?.detail || error.message || "未知错误";
  return {
    success: false,
    detail: detail,
    status: error.response?.status || 500,
    data: error.response?.data || null,
  };
};

export default {
  normalizeListResponse,
  normalizeObjectResponse,
  extractItems,
  extractTotal,
  normalizeError,
};
