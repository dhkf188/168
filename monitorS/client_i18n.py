#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
员工监控系统 - 国际化模块（优化版）
支持中文、越南语、英语
功能：
- 自动检测系统语言
- 完整的文本字典
- 键存在性验证
- 动态语言切换
- 类型提示完善
"""

import locale
import logging
from typing import Dict, Optional, List, Set
from pathlib import Path
import json


class I18nManager:
    """国际化管理器 - 优化版"""

    # 语言代码常量
    LANG_ZH = "zh"
    LANG_VI = "vi"
    LANG_EN = "en"
    SUPPORTED_LANGS = [LANG_ZH, LANG_VI, LANG_EN]

    def __init__(self, auto_detect: bool = True):
        self.logger = logging.getLogger(__name__)
        
        # 当前语言
        if auto_detect:
            self.current_lang = self.detect_language()
        else:
            self.current_lang = self.LANG_EN
            
        self.logger.info(f"🌐 系统语言: {self.current_lang}")
        
        # 加载文本字典
        self._texts = self._load_texts()
        
        # 缓存
        self._cache: Dict[str, str] = {}
        
        # 统计信息
        self.stats = {
            "total_keys": len(self._texts),
            "missing_keys": 0,
            "last_access": None,
        }

    def _load_texts(self) -> Dict:
        """加载所有文本（优化组织结构）"""
        return {
            # ==================== 通用 ====================
            "yes": {
                "zh": "是",
                "vi": "Có",
                "en": "Yes",
            },
            "no": {
                "zh": "否",
                "vi": "Không",
                "en": "No",
            },
            "ok": {
                "zh": "确定",
                "vi": "Xác nhận",
                "en": "OK",
            },
            "cancel": {
                "zh": "取消",
                "vi": "Hủy",
                "en": "Cancel",
            },
            "close": {
                "zh": "关闭",
                "vi": "Đóng",
                "en": "Close",
            },
            "save": {
                "zh": "保存",
                "vi": "Lưu",
                "en": "Save",
            },
            "confirm": {
                "zh": "确认",
                "vi": "Xác nhận",
                "en": "Confirm",
            },
            
            # ==================== 时间单位 ====================
            "second": {
                "zh": "秒",
                "vi": "giây",
                "en": "s",
            },
            "seconds": {
                "zh": "秒",
                "vi": "giây",
                "en": "s",
            },
            "minute": {
                "zh": "分钟",
                "vi": "phút",
                "en": "m",
            },
            "minutes": {
                "zh": "分钟",
                "vi": "phút",
                "en": "m",
            },
            "hour": {
                "zh": "小时",
                "vi": "giờ",
                "en": "h",
            },
            "hours": {
                "zh": "小时",
                "vi": "giờ",
                "en": "h",
            },
            "day": {
                "zh": "天",
                "vi": "ngày",
                "en": "d",
            },
            "days": {
                "zh": "天",
                "vi": "ngày",
                "en": "d",
            },
            
            # ==================== 状态 ====================
            "running": {
                "zh": "运行中",
                "vi": "Đang chạy",
                "en": "Running",
            },
            "stopped": {
                "zh": "已停止",
                "vi": "Đã dừng",
                "en": "Stopped",
            },
            "paused": {
                "zh": "已暂停",
                "vi": "Đã tạm dừng",
                "en": "Paused",
            },
            "online": {
                "zh": "在线",
                "vi": "Trực tuyến",
                "en": "Online",
            },
            "offline": {
                "zh": "离线",
                "vi": "Ngoại tuyến",
                "en": "Offline",
            },
            "enabled": {
                "zh": "已启用",
                "vi": "Đã bật",
                "en": "Enabled",
            },
            "disabled": {
                "zh": "已禁用",
                "vi": "Đã tắt",
                "en": "Disabled",
            },
            
            # ==================== 健康状态 ====================
            "healthy": {
                "zh": "健康",
                "vi": "Khỏe mạnh",
                "en": "Healthy",
            },
            "degraded": {
                "zh": "降级",
                "vi": "Suy giảm",
                "en": "Degraded",
            },
            "unhealthy": {
                "zh": "异常",
                "vi": "Bất thường",
                "en": "Unhealthy",
            },
            "unknown": {
                "zh": "未知",
                "vi": "Không xác định",
                "en": "Unknown",
            },
            
            # ==================== 托盘菜单 ====================
            "show_status": {
                "zh": "📊 显示状态",
                "vi": "📊 Hiển thị trạng thái",
                "en": "📊 Show Status",
            },
            "health_status": {
                "zh": "❤️ 健康状态",
                "vi": "❤️ Trạng thái sức khỏe",
                "en": "❤️ Health Status",
            },
            "watchdog_status": {
                "zh": "🐕 看门狗状态",
                "vi": "🐕 Trạng thái Watchdog",
                "en": "🐕 Watchdog Status",
            },
            "pause_monitor": {
                "zh": "⏸️ 暂停监控",
                "vi": "⏸️ Tạm dừng giám sát",
                "en": "⏸️ Pause Monitoring",
            },
            "resume_monitor": {
                "zh": "▶️ 恢复监控",
                "vi": "▶️ Tiếp tục giám sát",
                "en": "▶️ Resume Monitoring",
            },
            "screenshot_now": {
                "zh": "🔄 立即截图",
                "vi": "🔄 Chụp màn hình ngay",
                "en": "🔄 Screenshot Now",
            },
            "upload_queue": {
                "zh": "📦 上传队列",
                "vi": "📦 Hàng đợi tải lên",
                "en": "📦 Upload Queue",
            },
            "cleanup_cache": {
                "zh": "🧹 清理缓存",
                "vi": "🧹 Dọn bộ nhớ đệm",
                "en": "🧹 Cleanup Cache",
            },
            "network_diagnostic": {
                "zh": "🌐 网络诊断",
                "vi": "🌐 Chẩn đoán mạng",
                "en": "🌐 Network Diagnostic",
            },
            "reconfigure": {
                "zh": "✏️ 重新配置",
                "vi": "✏️ Cấu hình lại",
                "en": "✏️ Reconfigure",
            },
            "autostart": {
                "zh": "⚡ 开机自启",
                "vi": "⚡ Tự động khởi động",
                "en": "⚡ Auto Start",
            },
            "view_log": {
                "zh": "📝 查看日志",
                "vi": "📝 Xem nhật ký",
                "en": "📝 View Log",
            },
            "exit": {
                "zh": "❌ 退出",
                "vi": "❌ Thoát",
                "en": "❌ Exit",
            },
            
            # ==================== 通知标题 ====================
            "notification_monitor": {
                "zh": "监控",
                "vi": "Giám sát",
                "en": "Monitor",
            },
            "notification_health": {
                "zh": "健康监控",
                "vi": "Sức khỏe",
                "en": "Health",
            },
            "notification_watchdog": {
                "zh": "看门狗",
                "vi": "Watchdog",
                "en": "Watchdog",
            },
            "notification_queue": {
                "zh": "上传队列",
                "vi": "Hàng đợi",
                "en": "Queue",
            },
            "notification_screenshot": {
                "zh": "截图",
                "vi": "Chụp màn hình",
                "en": "Screenshot",
            },
            "notification_cache": {
                "zh": "缓存清理",
                "vi": "Dọn cache",
                "en": "Cache",
            },
            "notification_network": {
                "zh": "网络诊断",
                "vi": "Mạng",
                "en": "Network",
            },
            "notification_reconfigure": {
                "zh": "重新配置",
                "vi": "Cấu hình lại",
                "en": "Reconfigure",
            },
            "notification_exit": {
                "zh": "退出",
                "vi": "Thoát",
                "en": "Exit",
            },
            
            # ==================== 通知消息 ====================
            "msg_paused": {
                "zh": "监控已暂停",
                "vi": "Đã tạm dừng giám sát",
                "en": "Monitoring Paused",
            },
            "msg_resumed": {
                "zh": "监控已恢复",
                "vi": "Đã tiếp tục giám sát",
                "en": "Monitoring Resumed",
            },
            "msg_screenshot_triggered": {
                "zh": "已触发立即截图",
                "vi": "Đã kích hoạt chụp màn hình",
                "en": "Screenshot Triggered",
            },
            "msg_cache_cleaned": {
                "zh": "缓存清理完成",
                "vi": "Đã dọn bộ nhớ đệm",
                "en": "Cache Cleanup Complete",
            },
            "msg_exiting": {
                "zh": "正在退出程序...",
                "vi": "Đang thoát chương trình...",
                "en": "Exiting...",
            },
            "msg_health_disabled": {
                "zh": "健康监控未启用",
                "vi": "Sức khỏe chưa bật",
                "en": "Health monitoring disabled",
            },
            "msg_watchdog_disabled": {
                "zh": "看门狗未启用",
                "vi": "Watchdog chưa bật",
                "en": "Watchdog disabled",
            },
            "msg_queue_disabled": {
                "zh": "上传队列未启用",
                "vi": "Hàng đợi chưa bật",
                "en": "Upload queue disabled",
            },
            
            # ==================== 配置对话框 ====================
            "config_title": {
                "zh": "员工监控系统 - 首次配置",
                "vi": "Hệ thống giám sát - Cấu hình lần đầu",
                "en": "Monitor System - First Setup",
            },
            "config_welcome": {
                "zh": "🎉 欢迎使用员工监控系统",
                "vi": "🎉 Chào mừng bạn",
                "en": "🎉 Welcome",
            },
            "config_description": {
                "zh": "首次运行需要配置员工信息",
                "vi": "Cần cấu hình thông tin nhân viên",
                "en": "First run requires employee info",
            },
            "config_employee_info": {
                "zh": "员工信息",
                "vi": "Thông tin nhân viên",
                "en": "Employee Info",
            },
            "config_name": {
                "zh": "您的姓名",
                "vi": "Tên của bạn",
                "en": "Your name",
            },
            "config_name_hint": {
                "zh": "例如：张三",
                "vi": "Ví dụ: Nguyễn Văn A",
                "en": "e.g., John Smith",
            },
            "config_system_info": {
                "zh": "系统信息",
                "vi": "Thông tin hệ thống",
                "en": "System Info",
            },
            "config_computer_name": {
                "zh": "计算机名",
                "vi": "Tên máy tính",
                "en": "Computer name",
            },
            "config_user_name": {
                "zh": "用户名",
                "vi": "Tên người dùng",
                "en": "Username",
            },
            "config_remember": {
                "zh": "记住此姓名",
                "vi": "Ghi nhớ tên này",
                "en": "Remember name",
            },
            "config_warning_title": {
                "zh": "提示",
                "vi": "Thông báo",
                "en": "Warning",
            },
            "config_warning_name_empty": {
                "zh": "请输入姓名",
                "vi": "Vui lòng nhập tên",
                "en": "Please enter name",
            },
            "config_warning_name_short": {
                "zh": "姓名至少2个字符",
                "vi": "Tên ít nhất 2 ký tự",
                "en": "Name min 2 characters",
            },
            "config_confirm_exit": {
                "zh": "是否退出？",
                "vi": "Thoát?",
                "en": "Exit?",
            },
            
            # ==================== 重新配置对话框 ====================
            "reconfigure_title": {
                "zh": "重新配置",
                "vi": "Cấu hình lại",
                "en": "Reconfigure",
            },
            "reconfigure_message": {
                "zh": "是否重新输入员工姓名？",
                "vi": "Nhập lại tên?",
                "en": "Re-enter name?",
            },
            "reconfigure_success": {
                "zh": "配置成功",
                "vi": "Thành công",
                "en": "Success",
            },
            "reconfigure_success_msg": {
                "zh": "员工信息已更新",
                "vi": "Đã cập nhật",
                "en": "Updated",
            },
            "reconfigure_failed": {
                "zh": "配置失败",
                "vi": "Thất bại",
                "en": "Failed",
            },
            "reconfigure_failed_msg": {
                "zh": "请检查网络后重试",
                "vi": "Kiểm tra mạng",
                "en": "Check network",
            },
            
            # ==================== 统计信息 ====================
            "stats_title": {
                "zh": "📊 运行统计",
                "vi": "📊 Thống kê",
                "en": "📊 Statistics",
            },
            "stats_uptime": {
                "zh": "运行时间",
                "vi": "Thời gian chạy",
                "en": "Uptime",
            },
            "stats_screenshots": {
                "zh": "截图数量",
                "vi": "Số ảnh",
                "en": "Screenshots",
            },
            "stats_skipped": {
                "zh": "跳过相似",
                "vi": "Bỏ qua",
                "en": "Skipped",
            },
            "stats_uploaded": {
                "zh": "上传成功",
                "vi": "Đã tải lên",
                "en": "Uploaded",
            },
            "stats_failed": {
                "zh": "上传失败",
                "vi": "Thất bại",
                "en": "Failed",
            },
            "stats_power_saved": {
                "zh": "节电时间",
                "vi": "Tiết kiệm điện",
                "en": "Power saved",
            },
        }

    def detect_language(self) -> str:
        """检测系统语言"""
        try:
            lang, _ = locale.getdefaultlocale()
            if lang:
                if lang.startswith("zh"):
                    return self.LANG_ZH
                elif lang.startswith("vi"):
                    return self.LANG_VI
                elif lang.startswith("en"):
                    return self.LANG_EN
        except Exception as e:
            self.logger.debug(f"语言检测失败: {e}")
        return self.LANG_EN

    def set_language(self, lang: str) -> bool:
        """设置语言"""
        if lang in self.SUPPORTED_LANGS:
            self.current_lang = lang
            self._cache.clear()  # 清除缓存
            self.logger.info(f"🌐 语言已切换: {lang}")
            return True
        self.logger.warning(f"不支持的语言: {lang}")
        return False

    def get_text(self, key: str, default: Optional[str] = None, **kwargs) -> str:
        """获取文本（支持格式化）"""
        # 检查缓存
        cache_key = f"{self.current_lang}:{key}"
        if cache_key in self._cache:
            text = self._cache[cache_key]
        else:
            # 获取文本
            if key in self._texts:
                text = self._texts[key].get(
                    self.current_lang,
                    self._texts[key][self.LANG_EN]
                )
            else:
                self.stats["missing_keys"] += 1
                self.logger.debug(f"缺少国际化键: {key}")
                text = default or key
            
            # 存入缓存
            self._cache[cache_key] = text
        
        self.stats["last_access"] = time.time()
        
        # 格式化
        if kwargs:
            try:
                return text.format(**kwargs)
            except KeyError as e:
                self.logger.error(f"格式化失败 {key}: {e}")
                return text
        
        return text

    def get_all_texts(self) -> Dict[str, str]:
        """获取所有当前语言的文本"""
        return {key: self.get_text(key) for key in self._texts}

    def validate_keys(self, required_keys: List[str]) -> Dict[str, List[str]]:
        """验证必需的键是否存在"""
        missing = [k for k in required_keys if k not in self._texts]
        return {
            "missing": missing,
            "total": len(required_keys),
            "present": len(required_keys) - len(missing),
        }

    def export_to_json(self, filepath: Optional[str] = None) -> Optional[str]:
        """导出当前语言到JSON文件"""
        data = {
            "language": self.current_lang,
            "texts": self.get_all_texts(),
            "timestamp": time.time(),
        }
        
        if filepath:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return filepath
        
        return json.dumps(data, ensure_ascii=False, indent=2)

    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            **self.stats,
            "current_lang": self.current_lang,
            "cache_size": len(self._cache),
        }


# ==================== 全局实例 ====================
import time  # 添加time导入

_i18n = I18nManager()


def get_text(key: str, default: Optional[str] = None, **kwargs) -> str:
    """获取文本的快捷函数"""
    return _i18n.get_text(key, default, **kwargs)


def set_language(lang: str) -> bool:
    """设置语言的快捷函数"""
    return _i18n.set_language(lang)


def get_current_language() -> str:
    """获取当前语言"""
    return _i18n.current_lang


def validate_keys(required_keys: List[str]) -> Dict:
    """验证键的快捷函数"""
    return _i18n.validate_keys(required_keys)


# ==================== 使用示例 ====================
if __name__ == "__main__":
    # 测试
    i18n = I18nManager()
    print(f"当前语言: {i18n.current_lang}")
    print(f"确定: {i18n.get_text('ok')}")
    print(f"取消: {i18n.get_text('cancel')}")
    print(f"运行时间: {i18n.get_text('stats_uptime')}")
    
    # 测试格式化
    print(i18n.get_text("title_normal", count=42))
    
    # 验证必需的键
    required = ["ok", "cancel", "yes", "no", "running", "stopped"]
    result = i18n.validate_keys(required)
    print(f"键验证: {result}")