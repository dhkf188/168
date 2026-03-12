// admin_timezone.js
// 统一的时间处理工具 - 所有时间都是北京时间

import dayjs from "dayjs";
import utc from "dayjs/plugin/utc";
import timezone from "dayjs/plugin/timezone";
import relativeTime from "dayjs/plugin/relativeTime";
import "dayjs/locale/zh-cn";

// 配置 dayjs
dayjs.extend(utc);
dayjs.extend(timezone);
dayjs.extend(relativeTime);
dayjs.locale("zh-cn");

// 设置默认时区为北京时间
const DEFAULT_TIMEZONE = "Asia/Shanghai";

/**
 * 解析北京时间
 * @param {string|Date} time - 时间（后端返回的北京时间）
 * @returns {dayjs.Dayjs} dayjs对象
 */
export function toBeijingTime(time) {
  if (!time) return null;
  return dayjs(time);
}

/**
 * 格式化日期时间（北京时间）
 * @param {string|Date} datetime - 要格式化的时间
 * @param {string} format - 格式化模式，默认 'YYYY-MM-DD HH:mm'
 * @returns {string} 格式化后的时间字符串
 */
export function formatDateTime(datetime, format = "YYYY-MM-DD HH:mm") {
  if (!datetime) return "未知";
  const beijingTime = toBeijingTime(datetime);
  return beijingTime.format(format);
}

/**
 * 格式化时间（仅时分）
 * @param {string|Date} datetime - 要格式化的时间
 * @returns {string} 格式化后的时间字符串 (HH:mm)
 */
export function formatTime(datetime) {
  if (!datetime) return "未知";
  return toBeijingTime(datetime).format("HH:mm");
}

/**
 * 格式化完整日期时间（带时区标识）
 * @param {string|Date} datetime - 要格式化的时间
 * @returns {string} 格式化后的时间字符串 (YYYY-MM-DD HH:mm:ss)
 */
export function formatFullDateTime(datetime) {
  if (!datetime) return "未知";
  const beijingTime = toBeijingTime(datetime);
  return `${beijingTime.format("YYYY-MM-DD HH:mm:ss")} (北京时间)`;
}

/**
 * 获取相对时间描述（刚刚、X分钟前等）
 * @param {string|Date} datetime - 要计算的时间
 * @returns {string} 相对时间描述
 */
export function formatRelativeTime(datetime) {
  if (!datetime) return "从未";
  const beijingTime = toBeijingTime(datetime);
  const now = dayjs().tz(DEFAULT_TIMEZONE);
  const diffMinutes = now.diff(beijingTime, "minute");

  if (diffMinutes < 1) return "刚刚";
  if (diffMinutes < 60) return `${diffMinutes}分钟前`;
  if (diffMinutes < 1440) return `${Math.floor(diffMinutes / 60)}小时前`;
  return beijingTime.format("YYYY-MM-DD HH:mm");
}

/**
 * 获取在线状态
 * @param {string|Date} lastActive - 最后活跃时间
 * @param {number} thresholdMinutes - 在线阈值（分钟），默认10分钟
 * @returns {Object} 状态对象 { type, text }
 */
export function getOnlineStatus(lastActive, thresholdMinutes = 10) {
  if (!lastActive) return { type: "danger", text: "离线" };

  const now = dayjs().tz(DEFAULT_TIMEZONE);
  const last = toBeijingTime(lastActive);
  const diffMinutes = now.diff(last, "minute");

  if (diffMinutes < thresholdMinutes) {
    return { type: "success", text: "在线" };
  }
  return { type: "danger", text: "离线" };
}

/**
 * 获取时间的小时数（用于筛选）
 * @param {string|Date} datetime - 时间
 * @returns {number} 小时数 (0-23)
 */
export function getHour(datetime) {
  if (!datetime) return 0;
  return toBeijingTime(datetime).hour();
}

/**
 * 格式化文件大小
 * @param {number} size - 文件大小（字节）
 * @returns {string} 格式化后的大小
 */
export function formatFileSize(size) {
  if (!size) return "0 B";
  if (size < 1024) return size + " B";
  if (size < 1024 * 1024) return (size / 1024).toFixed(1) + " KB";
  return (size / (1024 * 1024)).toFixed(1) + " MB";
}

/**
 * 获取当前北京时间（用于调试）
 * @returns {string} 当前北京时间
 */
export function getCurrentBeijingTime() {
  return dayjs().tz(DEFAULT_TIMEZONE).format("YYYY-MM-DD HH:mm:ss");
}

export default {
  formatDateTime,
  formatTime,
  formatFullDateTime,
  formatRelativeTime,
  getOnlineStatus,
  getHour,
  formatFileSize,
  getCurrentBeijingTime,
};
