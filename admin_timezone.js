// admin_timezone.js - 最终优化版
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
 * 获取当前北京时间
 */
function getNow() {
  return dayjs().tz(DEFAULT_TIMEZONE);
}

/**
 * 解析时间（后端返回的已经是北京时间）
 */
export function toBeijingTime(time) {
  if (!time) return null;
  return dayjs(time); // dayjs 会自动处理 ISO 字符串中的时区
}

/**
 * 格式化日期时间
 */
export function formatDateTime(datetime, format = "YYYY-MM-DD HH:mm") {
  if (!datetime) return "未知";
  return toBeijingTime(datetime).format(format);
}

/**
 * 格式化时间（仅时分）- 复用 formatDateTime
 */
export function formatTime(datetime) {
  return formatDateTime(datetime, "HH:mm");
}

/**
 * 格式化完整日期时间（带时区标识）
 */
export function formatFullDateTime(datetime) {
  if (!datetime) return "未知";
  return `${formatDateTime(datetime, "YYYY-MM-DD HH:mm:ss")} (北京时间)`;
}

/**
 * 获取相对时间描述
 */
export function formatRelativeTime(datetime) {
  if (!datetime) return "从未";

  const beijingTime = toBeijingTime(datetime);
  const now = getNow();
  const diffMinutes = now.diff(beijingTime, "minute");

  if (diffMinutes < 1) return "刚刚";
  if (diffMinutes < 60) return `${diffMinutes}分钟前`;
  if (diffMinutes < 1440) return `${Math.floor(diffMinutes / 60)}小时前`;
  return formatDateTime(datetime); // 复用 formatDateTime
}

/**
 * 获取在线状态
 */
export function getOnlineStatus(lastActive, thresholdMinutes = 10) {
  if (!lastActive) return { type: "danger", text: "离线" };

  const now = getNow();
  const last = toBeijingTime(lastActive);
  const diffMinutes = now.diff(last, "minute");

  return {
    type: diffMinutes < thresholdMinutes ? "success" : "danger",
    text: diffMinutes < thresholdMinutes ? "在线" : "离线",
  };
}

/**
 * 获取时间的小时数
 */
export function getHour(datetime) {
  if (!datetime) return 0;
  return toBeijingTime(datetime).hour();
}

/**
 * 格式化文件大小（优化版）
 */
export function formatFileSize(size) {
  if (!size || size < 0) return "0 B";

  const units = ["B", "KB", "MB", "GB"];
  let index = 0;
  let fileSize = size;

  while (fileSize >= 1024 && index < units.length - 1) {
    fileSize /= 1024;
    index++;
  }

  return `${fileSize.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

export function formatDuration(seconds) {
  if (!seconds || seconds < 0) return "0秒";

  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;

  const parts = [];
  if (hours > 0) parts.push(`${hours}小时`);
  if (minutes > 0) parts.push(`${minutes}分钟`);
  if (secs > 0 && hours === 0) parts.push(`${secs}秒`);

  return parts.join("") || "0秒";
}

/**
 * 获取当前北京时间（调试用）
 */
export function getCurrentBeijingTime() {
  return getNow().format("YYYY-MM-DD HH:mm:ss");
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
  formatDuration,
};
