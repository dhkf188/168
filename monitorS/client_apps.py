#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
软件使用监控模块
- 统计各软件使用时长
- 前台应用识别
"""

import time
import logging
import threading
from datetime import datetime
from typing import Dict, List, Optional
import json
from pathlib import Path

try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

try:
    import win32gui
    import win32process

    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False


class AppMonitor:
    """软件使用监控器"""

    # 忽略的系统进程
    IGNORE_PROCESSES = [
        # Windows 核心进程
        "System",
        "Registry",
        "smss.exe",
        "csrss.exe",
        "wininit.exe",
        "services.exe",
        "lsass.exe",
        "lsm.exe",
        "svchost.exe",
        "conhost.exe",
        "fontdrvhost.exe",
        "dwm.exe",
        "Idle",
        # 后台服务进程
        "dllhost.exe",
        "RuntimeBroker.exe",
        "backgroundTaskHost.exe",
        "sihost.exe",
        "taskhostw.exe",
        "ShellExperienceHost.exe",
        "SearchUI.exe",
        "SearchIndexer.exe",
        "WmiPrvSE.exe",
        "spoolsv.exe",
        # 数据库服务
        "postgres.exe",
        "mysqld.exe",
        "sqlservr.exe",
        "mongod.exe",
        "redis-server.exe",
        # 开发工具后台
        "node.exe",
        "python.exe",
        "java.exe",
        "javaw.exe",
        "git.exe",
        # 系统工具
        "cmd.exe",
        "powershell.exe",
        "powershell_ise.exe",
        "explorer.exe",
        "taskmgr.exe",
        "regedit.exe",
        "msconfig.exe",
        # 驱动程序
        "audiodg.exe",
        "rundll32.exe",
        "CompatTelRunner.exe",
        # 更新程序
        "wuauclt.exe",
        "TrustedInstaller.exe",
        "TiWorker.exe",
        # 杀毒软件
        "MsMpEng.exe",
        "NisSrv.exe",
        "SecurityHealthService.exe",
        "SecurityHealthSystray.exe",
    ]

    def __init__(self, client):
        self.client = client
        self.logger = logging.getLogger(__name__)

        # 活跃应用 {pid: {"name": name, "start": time, "last_seen": time}}
        self.active_apps = {}
        self.lock = threading.RLock()

        # 上报间隔
        self.report_interval = 300  # 5分钟
        self.last_report_time = time.time()

        # 缓存
        self.stats_cache = []

    def get_all_processes(self) -> List[Dict]:
        """获取所有进程"""
        processes = []
        if not PSUTIL_AVAILABLE:
            return processes

        for proc in psutil.process_iter(
            ["pid", "name", "exe", "create_time", "cpu_percent", "memory_info"]
        ):
            try:
                pinfo = proc.info
                if pinfo["name"] and pinfo["name"] not in self.IGNORE_PROCESSES:
                    processes.append(
                        {
                            "pid": pinfo["pid"],
                            "name": pinfo["name"],
                            "exe": pinfo["exe"] or "",
                            "create_time": pinfo["create_time"],
                            "cpu_percent": proc.cpu_percent(),
                            "memory_mb": (
                                pinfo["memory_info"].rss / 1024 / 1024
                                if pinfo["memory_info"]
                                else 0
                            ),
                        }
                    )
            except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError):
                continue

        return processes

    def get_foreground_app(self) -> Optional[Dict]:
        """获取当前前台应用"""
        if not WIN32_AVAILABLE or not PSUTIL_AVAILABLE:
            return None

        try:
            hwnd = win32gui.GetForegroundWindow()
            _, pid = win32process.GetWindowThreadProcessId(hwnd)

            proc = psutil.Process(pid)
            proc_name = proc.name()

            if proc_name not in self.IGNORE_PROCESSES:
                return {
                    "pid": pid,
                    "name": proc_name,
                    "exe": proc.exe(),
                    "window_title": win32gui.GetWindowText(hwnd),
                    "cpu_percent": proc.cpu_percent(),
                    "memory_mb": proc.memory_info().rss / 1024 / 1024,
                    "timestamp": time.time(),
                }
        except Exception as e:
            self.logger.debug(f"获取前台应用失败: {e}")

        return None

    def track_app_usage(self):
        """跟踪软件使用 - 智能识别（只记录真实用户软件）"""
        current_time = time.time()
        foreground = self.get_foreground_app()

        # 将忽略列表转为小写，便于比较
        ignore_lower = [p.lower() for p in self.IGNORE_PROCESSES]

        with self.lock:
            # ===== 1. 先记录所有应用（但过滤系统进程）=====
            for proc in self.get_all_processes():
                pid = proc["pid"]
                proc_name = proc["name"].lower()

                # 过滤系统进程
                if proc_name in ignore_lower:
                    continue

                # 忽略空名称
                if not proc_name:
                    continue

                if pid in self.active_apps:
                    # 更新最后活跃时间
                    self.active_apps[pid]["last_seen"] = current_time
                    # 更新资源使用（每秒采样）
                    self.active_apps[pid]["cpu_samples"] = self.active_apps[pid].get(
                        "cpu_samples", []
                    ) + [proc["cpu_percent"]]
                    self.active_apps[pid]["memory_samples"] = self.active_apps[pid].get(
                        "memory_samples", []
                    ) + [proc["memory_mb"]]
                else:
                    # 新应用
                    self.active_apps[pid] = {
                        "pid": pid,
                        "name": proc["name"],
                        "exe": proc["exe"],
                        "first_seen": current_time,
                        "last_seen": current_time,
                        "foreground_time": 0,
                        "total_time": 0,
                        "cpu_samples": [proc["cpu_percent"]],
                        "memory_samples": [proc["memory_mb"]],
                    }

            # ===== 2. 标记前台应用（增加权重）=====
            if foreground and foreground["pid"]:
                pid = foreground["pid"]
                app_name = foreground["name"].lower()

                # 如果前台应用是系统进程，忽略
                if app_name in ignore_lower:
                    pass  # 不记录系统进程
                elif pid in self.active_apps:
                    # 已有记录，增加前台时间
                    self.active_apps[pid]["foreground_time"] += 5
                    self.active_apps[pid]["last_seen"] = current_time
                    # 更新窗口标题（前台应用才有）
                    self.active_apps[pid]["window_title"] = foreground.get(
                        "window_title", ""
                    )
                    self.active_apps[pid]["cpu_percent"] = foreground.get(
                        "cpu_percent", 0
                    )
                    self.active_apps[pid]["memory_mb"] = foreground.get("memory_mb", 0)
                else:
                    # 新前台应用（虽然被过滤了，但还是记录一下）
                    self.active_apps[pid] = {
                        "pid": pid,
                        "name": foreground["name"],
                        "exe": foreground["exe"],
                        "first_seen": current_time,
                        "last_seen": current_time,
                        "foreground_time": 5,
                        "total_time": 0,
                        "window_title": foreground.get("window_title", ""),
                        "cpu_percent": foreground.get("cpu_percent", 0),
                        "memory_mb": foreground.get("memory_mb", 0),
                        "cpu_samples": [foreground.get("cpu_percent", 0)],
                        "memory_samples": [foreground.get("memory_mb", 0)],
                    }

            # ===== 3. 清理不活跃应用（30秒无活动）=====
            to_remove = []
            for pid, info in self.active_apps.items():
                if current_time - info["last_seen"] > 30:
                    # 计算使用时长
                    total_duration = int(current_time - info["first_seen"])

                    # 智能判断：满足以下任一条件才记录
                    should_save = False

                    # 条件1：运行时间超过30秒
                    if total_duration >= 30:
                        should_save = True

                    # 条件2：前台时间超过10秒
                    if info.get("foreground_time", 0) >= 10:
                        should_save = True

                    # 条件3：是浏览器或办公软件（通过名称判断）
                    user_apps = [
                        "chrome",
                        "firefox",
                        "edge",
                        "brave",
                        "vivaldi",
                        "navicat",
                        "notepad",
                        "code",
                        "word",
                        "excel",
                        "powerpnt",
                        "wechat",
                        "qq",
                        "dingtalk",
                    ]
                    if any(app in info["name"].lower() for app in user_apps):
                        should_save = True

                    if should_save:
                        self._save_app_usage(info, total_duration)

                    to_remove.append(pid)

            # 删除已处理的进程
            for pid in to_remove:
                del self.active_apps[pid]

    def _save_app_usage(self, info: Dict, duration: int):
        """保存软件使用记录 - 只记录前台应用"""
        if not self.client.employee_id:
            return

        # ✅ 只记录前台应用（前台时间占比>30%）
        foreground_ratio = info.get("foreground_time", 0) / max(duration, 1)
        if foreground_ratio < 0.3:
            self.logger.debug(
                f"跳过后台应用: {info['name']} (前台占比{foreground_ratio:.1%})"
            )
            return

        # 计算平均值
        cpu_samples = info.get("cpu_samples", [0])
        memory_samples = info.get("memory_samples", [0])

        cpu_avg = int(sum(cpu_samples) / len(cpu_samples) if cpu_samples else 0)
        memory_avg = int(
            sum(memory_samples) / len(memory_samples) if memory_samples else 0
        )

        data = {
            "employee_id": self.client.employee_id,
            "client_id": self.client.client_id,
            "app_name": info["name"],
            "app_path": info.get("exe", ""),
            "window_title": info.get("window_title", ""),
            "start_time": datetime.fromtimestamp(info["first_seen"]),
            "end_time": datetime.fromtimestamp(info["last_seen"]),
            "duration": duration,
            "is_foreground": True,  # ✅ 始终为 True
            "cpu_avg": cpu_avg,
            "memory_avg": memory_avg,
        }

        # 添加到缓存
        self.stats_cache.append(data)

        # 保存到文件（备份）
        cache_file = Path("cache") / f"app_{info['first_seen']}.json"
        cache_file.parent.mkdir(exist_ok=True)

        data_for_file = data.copy()
        data_for_file["start_time"] = data["start_time"].isoformat()
        data_for_file["end_time"] = data["end_time"].isoformat()

        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(data_for_file, f)

        # 调试日志
        self.logger.debug(
            f"📝 记录前台应用: {info['name']} - {duration}秒 (前台占比{foreground_ratio:.1%})"
        )

    def collect_and_report(self):
        """收集并上报软件使用统计"""
        current_time = time.time()

        if current_time - self.last_report_time < self.report_interval:
            return

        if not self.stats_cache:
            return

        foreground_count = sum(
            1 for item in self.stats_cache if item.get("is_foreground")
        )
        background_count = len(self.stats_cache) - foreground_count
        self.logger.info(
            f"开始上报软件使用统计: 共{len(self.stats_cache)}条 "
            f"(前台:{foreground_count}, 后台:{background_count})"
        )

        top_apps = [item["app_name"] for item in self.stats_cache[:5]]
        self.logger.info(f"应用示例: {', '.join(top_apps)}")

        # ✅ 关键修复：确保所有 datetime 对象都转为字符串
        serializable_cache = []
        for item in self.stats_cache:
            serializable_item = item.copy()
            if isinstance(serializable_item.get("start_time"), datetime):
                serializable_item["start_time"] = serializable_item[
                    "start_time"
                ].isoformat()
            if isinstance(serializable_item.get("end_time"), datetime):
                serializable_item["end_time"] = serializable_item[
                    "end_time"
                ].isoformat()
            serializable_cache.append(serializable_item)

        if self.client.api_client and not self.client.offline_mode:
            try:
                response = self.client.api_client.post(
                    "/api/apps/usage", json=serializable_cache  # ✅ 使用转换后的数据
                )
                if response:
                    self.logger.info(
                        f"✅ 软件使用上报成功: {len(serializable_cache)}条"
                    )
                    # 删除已上报的缓存文件
                    for item in self.stats_cache:
                        # 确保从对象获取时间戳用于定位文件名
                        if isinstance(item["start_time"], datetime):
                            start = item["start_time"].timestamp()
                        else:
                            start = datetime.fromisoformat(
                                item["start_time"]
                            ).timestamp()

                        cache_file = Path("cache") / f"app_{start}.json"
                        if cache_file.exists():
                            cache_file.unlink()
                    self.stats_cache.clear()
                    self.last_report_time = current_time
                else:
                    self.logger.warning("上报失败，保留缓存")
            except Exception as e:
                self.logger.error(f"上报软件使用失败: {e}")
        else:
            self.logger.debug("离线模式，软件使用数据已缓存")

    def start_monitoring(self):
        """启动监控线程"""

        def monitor_loop():
            while self.client.running:
                try:
                    self.track_app_usage()
                    self.collect_and_report()
                    time.sleep(5)
                except Exception as e:
                    self.logger.error(f"软件监控异常: {e}")
                    time.sleep(30)

        thread = threading.Thread(target=monitor_loop, daemon=True)
        thread.start()
        self.logger.info("✅ 软件使用监控已启动")
