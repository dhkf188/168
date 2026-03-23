#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
员工监控系统 - 托盘图标模块（多语言版）- 修复版
"""

import os
import sys
import time
import threading
import logging
import webbrowser
from pathlib import Path

# 尝试导入托盘图标依赖
try:
    from PIL import Image, ImageDraw
    import pystray

    PYSTRAY_AVAILABLE = True
except ImportError:
    PYSTRAY_AVAILABLE = False

try:
    from plyer import notification

    PLYER_AVAILABLE = True
except ImportError:
    PLYER_AVAILABLE = False

try:
    import winreg

    WINREG_AVAILABLE = True
except ImportError:
    WINREG_AVAILABLE = False

from client_i18n import get_text


class EnhancedTrayIcon:
    """增强的托盘图标类（多语言版）"""

    def __init__(self, client):
        self.client = client
        self.logger = logging.getLogger(__name__)

        # 通知冷却
        self.last_notification = {}
        self.notification_cooldown = 60

        # 依赖检查
        self.pystray_available = PYSTRAY_AVAILABLE
        self.plyer_available = PLYER_AVAILABLE

        self.icon = None

        if self.pystray_available:
            self.create_icon()
        else:
            self.logger.warning("⚠️ pystray未安装，托盘图标不可用")

    def create_icon(self):
        """创建托盘图标"""
        if not self.pystray_available:
            return

        # 创建图标图像
        image = self._create_icon_image()

        # 创建菜单
        menu = (
            pystray.MenuItem(get_text("show_status"), self.show_status),
            pystray.MenuItem(get_text("health_status"), self.show_health_status),
            pystray.MenuItem(get_text("watchdog_status"), self.show_watchdog_status),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                get_text("pause_monitor"),
                self.pause_monitor,
                enabled=lambda item: not self.client.paused,
            ),
            pystray.MenuItem(
                get_text("resume_monitor"),
                self.resume_monitor,
                enabled=lambda item: self.client.paused,
            ),
            pystray.MenuItem(get_text("screenshot_now"), self.take_screenshot_now),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(get_text("upload_queue"), self.show_queue_status),
            pystray.MenuItem(get_text("cleanup_cache"), self.cleanup_cache),
            pystray.MenuItem(get_text("network_diagnostic"), self.network_diagnostic),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(get_text("reconfigure"), self.reconfigure),
            pystray.MenuItem(
                get_text("autostart"),
                self.toggle_autostart,
                checked=lambda item: self.is_autostart_enabled(),
            ),
            pystray.MenuItem(get_text("view_log"), self.open_log),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(get_text("exit"), self.exit_app),
        )

        self.icon = pystray.Icon("employee_monitor", image, "员工监控系统", menu)

    def _create_icon_image(self):
        """创建图标图像"""
        image = Image.new("RGB", (64, 64), color=(102, 126, 234))
        draw = ImageDraw.Draw(image)

        # 绘制相机图标
        draw.rectangle([16, 20, 48, 44], outline=(255, 255, 255), width=2)
        draw.ellipse([28, 28, 36, 36], fill=(255, 255, 255))
        draw.line([40, 28, 44, 24], fill=(255, 255, 255), width=2)

        # 状态指示
        if self.client.paused:
            draw.ellipse([48, 8, 56, 16], fill=(255, 255, 0), outline=(0, 0, 0))
        elif self.client.offline_mode:
            draw.ellipse([48, 8, 56, 16], fill=(255, 0, 0), outline=(0, 0, 0))
        else:
            draw.ellipse([48, 8, 56, 16], fill=(0, 255, 0), outline=(0, 0, 0))

        return image

    def show_status(self):
        """显示基本状态"""
        stats = self.client.get_stats()
        uptime = stats.get("uptime", 0)
        hours = int(uptime // 3600)
        minutes = int((uptime % 3600) // 60)

        # 修复1：使用硬编码文本，避免缺少国际化键
        message = (
            f"员工ID: {self.client.employee_id}\n"
            f"服务器: {self.client.current_server}\n"
            f"运行时间: {hours}小时{minutes}分钟\n"
            f"截图数量: {stats['screenshots_taken']}\n"
            f"上传成功: {stats['screenshots_uploaded']}\n"
            f"跳过相似: {stats.get('skipped_similar', 0)}\n"
            f"截图间隔: {self.client.interval}秒"
        )

        self._show_notification(get_text("show_status"), message)

    def show_health_status(self):
        """显示健康状态"""
        if not hasattr(self.client, "health_monitor"):
            self._show_notification(get_text("health_status"), "健康监控未启用")
            return

        summary = self.client.health_monitor.get_summary()

        message = (
            f"{get_text('health_status')}:\n"
            f"健康: {summary['healthy']}\n"
            f"降级: {summary['degraded']}\n"
            f"异常: {summary['unhealthy']}\n"
            f"未知: {summary['unknown']}\n"
            f"健康率: {summary['health_rate']*100:.1f}%\n"
            f"恢复次数: {summary['total_recoveries']}"
        )

        self._show_notification(get_text("health_status"), message)

    def show_watchdog_status(self):
        """显示看门狗状态"""
        if not hasattr(self.client, "watchdog"):
            self._show_notification(get_text("watchdog_status"), "看门狗未启用")
            return

        status = self.client.watchdog.get_status()

        # 修复2：使用硬编码文本
        running_text = "运行中" if status["running"] else "已停止"

        message = (
            f"{get_text('watchdog_status')}:\n"
            f"{running_text}\n"
            f"总重启: {status['stats']['total_restarts']}\n"
            f"失败重启: {status['stats']['failed_restarts']}\n\n"
            f"监控进程:\n"
        )

        for name, proc in status["processes"].items():
            icon = "✅" if proc["alive"] else "❌"
            message += f"{icon} {name}: {proc['status']}"
            if proc["restart_count"] > 0:
                message += f" (重启:{proc['restart_count']})"
            message += "\n"

        self._show_notification(get_text("watchdog_status"), message)

    def show_queue_status(self):
        """显示队列状态"""
        if not hasattr(self.client, "upload_queue"):
            self._show_notification(get_text("upload_queue"), "上传队列未启用")
            return

        stats = self.client.upload_queue.get_stats()
        queue_percent = (stats["queue_size"] / stats["queue_maxsize"]) * 100

        message = (
            f"队列大小: {stats['queue_size']}/{stats['queue_maxsize']} ({queue_percent:.1f}%)\n"
            f"已处理: {stats['processed']}\n"
            f"失败: {stats['failed']}\n"
            f"重试: {stats['retried']}\n"
            f"缓存文件: {stats['cache_count']}\n"
            f"缓存大小: {stats['cache_size']/1024/1024:.1f}MB"
        )

        self._show_notification(get_text("upload_queue"), message)

    def pause_monitor(self):
        """暂停监控"""
        self.client.paused = True
        self._show_notification(
            get_text("notification_monitor"), get_text("msg_paused")
        )
        self.update_icon_title()

    def resume_monitor(self):
        """恢复监控"""
        self.client.paused = False
        self._show_notification(
            get_text("notification_monitor"), get_text("msg_resumed")
        )
        self.update_icon_title()

    def take_screenshot_now(self):
        """立即截图"""
        self.client.take_screenshot_now = True
        self._show_notification(
            get_text("notification_screenshot"), get_text("msg_screenshot_triggered")
        )

    def cleanup_cache(self):
        """清理缓存"""
        if hasattr(self.client, "upload_queue"):
            self.client.upload_queue._cleanup_cache()
            self._show_notification(
                get_text("notification_cache"), get_text("msg_cache_cleaned")
            )

    def network_diagnostic(self):
        """网络诊断"""
        # 修复3：使用硬编码文本
        mode_text = "在线" if not self.client.offline_mode else "离线"
        heartbeat_text = "已启用" if self.client.enable_heartbeat else "已禁用"

        message = (
            f"当前服务器: {self.client.current_server}\n"
            f"Client ID: {self.client.client_id}\n"
            f"模式: {mode_text}\n"
            f"心跳: {heartbeat_text}\n\n"
        )

        # 测试连接
        try:
            import requests

            start = time.time()
            response = requests.get(
                f"{self.client.current_server}/health", timeout=5, verify=False
            )
            elapsed = (time.time() - start) * 1000

            if response.status_code == 200:
                message += f"✅ 服务器连接正常 (延迟: {elapsed:.0f}ms)"
            else:
                message += f"⚠️ 服务器状态码: {response.status_code}"
        except Exception as e:
            message += f"❌ 连接失败: {e}"

        self._show_notification(get_text("network_diagnostic"), message)

    def reconfigure(self):
        """重新配置"""
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()

        result = messagebox.askyesno(
            get_text("reconfigure_title"),
            get_text("reconfigure_message"),
            parent=root,
        )

        if result:
            self.logger.info("✏️ 用户请求重新配置")
            self.client.config_manager.set("employee_name", "")
            self.client.config_manager.set("client_id", "")
            self.client.config_manager.set("employee_id", "")
            self.client._force_reconfigure = True
            self.client.first_run = True

            success = self.client.register_with_server(silent_mode=False)

            if success:
                self._show_notification(
                    get_text("reconfigure_success"), get_text("reconfigure_success_msg")
                )
            else:
                self._show_notification(
                    get_text("reconfigure_failed"), get_text("reconfigure_failed_msg")
                )

        root.destroy()

    def toggle_autostart(self):
        """切换开机自启"""
        if self.is_autostart_enabled():
            self.disable_autostart()
        else:
            self.enable_autostart()

    def is_autostart_enabled(self) -> bool:
        """检查开机自启"""
        if not WINREG_AVAILABLE or sys.platform != "win32":
            return False

        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_READ,
            )
            winreg.QueryValueEx(key, "EmployeeMonitor")
            winreg.CloseKey(key)
            return True
        except:
            return False

    def enable_autostart(self):
        """启用开机自启"""
        if not WINREG_AVAILABLE or sys.platform != "win32":
            return

        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_SET_VALUE,
            )

            if getattr(sys, "frozen", False):
                exe_path = sys.executable
            else:
                exe_path = f'"{sys.executable}" "{__file__}"'

            winreg.SetValueEx(key, "EmployeeMonitor", 0, winreg.REG_SZ, exe_path)
            winreg.CloseKey(key)
        except Exception as e:
            self.logger.error(f"设置开机自启失败: {e}")

    def disable_autostart(self):
        """禁用开机自启"""
        if not WINREG_AVAILABLE or sys.platform != "win32":
            return

        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_SET_VALUE,
            )
            winreg.DeleteValue(key, "EmployeeMonitor")
            winreg.CloseKey(key)
        except:
            pass

    def open_log(self):
        """打开日志"""
        log_file = "monitor.log"
        if os.path.exists(log_file):
            if sys.platform == "win32":
                os.startfile(log_file)
            elif sys.platform == "darwin":
                import subprocess

                subprocess.run(["open", log_file])

    def exit_app(self):
        """退出程序"""
        self._show_notification(get_text("notification_exit"), get_text("msg_exiting"))
        self.client.stop()
        if self.icon:
            self.icon.stop()

    def _show_notification(self, title: str, message: str):
        """显示通知"""
        now = time.time()
        key = f"{title}_{message[:50]}"

        if key in self.last_notification:
            if now - self.last_notification[key] < self.notification_cooldown:
                return

        self.last_notification[key] = now

        if self.plyer_available:
            try:
                notification.notify(
                    title=f"员工监控系统 - {title}", message=message, timeout=5
                )
            except Exception as e:
                self.logger.error(f"通知失败: {e}")
                print(f"{title}: {message}")
        else:
            print(f"{title}: {message}")

    def update_icon_title(self):
        """更新图标标题"""
        if self.icon:
            if self.client.paused:
                self.icon.title = "员工监控系统 - 已暂停"
            elif self.client.offline_mode:
                self.icon.title = "员工监控系统 - 离线模式"
            else:
                stats = self.client.get_stats()
                self.icon.title = (
                    f"员工监控系统 - {stats.get('screenshots_taken', 0)}张截图"
                )

    def run(self):
        """运行托盘图标"""
        if self.icon:
            self.icon.run()
