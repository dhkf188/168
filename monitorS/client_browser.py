#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
浏览器监控模块
- Chrome/Edge/Firefox 网页浏览记录
- 基于 Windows API 和浏览器历史数据库
"""

import os
import time
import sqlite3
import logging
import threading
import shutil
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
import json

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


class BrowserMonitor:
    """浏览器监控器"""

    def __init__(self, client):
        self.client = client
        self.logger = logging.getLogger(__name__)

        # 浏览器进程名
        self.browsers = {
            "chrome.exe": "Chrome",
            "msedge.exe": "Edge",
            "firefox.exe": "Firefox",
            "iexplore.exe": "IE",
            "brave.exe": "Brave",
            "opera.exe": "Opera",
        }

        # 使用 Path 处理路径，避免编码问题
        user_home = Path.home()

        self.history_paths = {
            "chrome": [
                user_home
                / "AppData"
                / "Local"
                / "Google"
                / "Chrome"
                / "User Data"
                / "Default"
                / "History",
                user_home
                / "AppData"
                / "Local"
                / "Google"
                / "Chrome"
                / "User Data"
                / "Profile *"
                / "History",
            ],
            "edge": [
                user_home
                / "AppData"
                / "Local"
                / "Microsoft"
                / "Edge"
                / "User Data"
                / "Default"
                / "History"
            ],
            "firefox": [
                user_home
                / "AppData"
                / "Roaming"
                / "Mozilla"
                / "Firefox"
                / "Profiles"
                / "*.default-release"
                / "places.sqlite"
            ],
        }

        # 缓存
        self.last_check_time = time.time()
        self.active_urls = {}  # {pid: {"url": url, "start_time": time}}
        self.history_cache = {}  # 避免重复上传
        self.lock = threading.RLock()

        # 上报间隔
        self.report_interval = 120  # 5分钟上报一次
        self.last_report_time = time.time()

        self.reported_urls = set()
        self.report_history = {}
        self.url_cache_lock = threading.RLock()

    def get_active_browsers(self):
        """获取当前运行的浏览器"""
        browsers = []
        if not PSUTIL_AVAILABLE:
            return browsers

        for proc in psutil.process_iter(["pid", "name", "create_time"]):
            try:
                if proc.info["name"] and proc.info["name"].lower() in self.browsers:
                    browsers.append(
                        {
                            "pid": proc.info["pid"],
                            "name": proc.info["name"],
                            "browser": self.browsers.get(
                                proc.info["name"].lower(), "Unknown"
                            ),
                            "start_time": proc.info["create_time"],
                        }
                    )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        return browsers

    def get_foreground_browser(self):
        """获取当前前台浏览器（Windows）"""
        if not WIN32_AVAILABLE:
            return None

        try:
            hwnd = win32gui.GetForegroundWindow()
            _, pid = win32process.GetWindowThreadProcessId(hwnd)

            proc = psutil.Process(pid)
            proc_name = proc.name().lower()

            if proc_name in self.browsers:
                window_title = win32gui.GetWindowText(hwnd)
                return {
                    "pid": pid,
                    "name": proc.name(),
                    "browser": self.browsers[proc_name],
                    "window_title": window_title,
                    "timestamp": time.time(),
                }
        except Exception as e:
            self.logger.debug(f"获取前台浏览器失败: {e}")

        return None

    def extract_url_from_title(self, title: str) -> Optional[str]:
        """从窗口标题提取URL（简单规则）"""
        # 常见格式: "标题 - 网站名 - Google Chrome"
        # 或 "网站名 - Google Chrome"
        if not title:
            return None

        # 移除浏览器名称
        for browser in [" - Google Chrome", " - Microsoft Edge", " - Firefox"]:
            if browser in title:
                title = title.replace(browser, "")

        # 如果包含 http/https，直接返回
        if "http://" in title or "https://" in title:
            parts = title.split()
            for part in parts:
                if part.startswith(("http://", "https://")):
                    return part

        return None

    def read_chrome_history(self) -> List[Dict]:
        """读取Chrome/Edge历史记录 - 只读最近30分钟，带去重"""
        results = []
        current_time = time.time()

        # ✅ 缩短到30分钟（原来是1小时）
        cutoff_time = current_time - 1800  # 30分钟

        # 临时复制历史数据库（避免文件锁定）
        temp_dir = tempfile.gettempdir()
        temp_db = os.path.join(temp_dir, f"chrome_history_{int(time.time())}.db")

        for browser_type in ["chrome", "edge"]:
            for pattern in self.history_paths.get(browser_type, []):
                pattern_str = str(pattern)
                import glob

                for history_file in glob.glob(pattern_str):
                    history_path = Path(history_file)
                    if not history_path.exists():
                        continue

                    try:
                        # 复制到临时文件
                        shutil.copy2(history_file, temp_db)

                        # 连接数据库
                        conn = sqlite3.connect(temp_db)
                        cursor = conn.cursor()

                        # ✅ 只查询最近30分钟的记录
                        cursor.execute(
                            """
                            SELECT url, title, last_visit_time/1000000-11644473600 as visit_time
                            FROM urls
                            WHERE last_visit_time > ?
                            ORDER BY last_visit_time DESC
                            LIMIT 200
                            """,
                            (int(cutoff_time * 1000000),),
                        )

                        rows = cursor.fetchall()
                        conn.close()

                        for url, title, visit_time in rows:
                            if not url or url.startswith(("chrome://", "edge://")):
                                continue

                            # ✅ 去重：检查是否已上报
                            url_key = f"{url}_{int(visit_time)}"
                            with self.url_cache_lock:
                                if url_key in self.reported_urls:
                                    continue

                                # ✅ 限制上报频率：同一URL 5分钟内不重复上报
                                last_report = self.report_history.get(url, 0)
                                if current_time - last_report < 300:  # 5分钟
                                    continue

                                self.reported_urls.add(url_key)
                                self.report_history[url] = current_time

                                # 清理过期记录（保留最近1小时）
                                self._cleanup_reported_urls(current_time - 3600)

                            results.append(
                                {
                                    "employee_id": self.client.employee_id,
                                    "client_id": self.client.client_id,
                                    "url": url,
                                    "title": title or url,
                                    "browser": browser_type,
                                    "visit_time": datetime.fromtimestamp(
                                        visit_time
                                    ).isoformat(),
                                    "duration": 0,  # 停留时间由实时跟踪计算
                                }
                            )

                        os.unlink(temp_db)
                        break  # 找到一个就行

                    except Exception as e:
                        self.logger.debug(f"读取{browser_type}历史失败: {e}")
                        try:
                            if os.path.exists(temp_db):
                                os.unlink(temp_db)
                        except:
                            pass

        return results

    def _cleanup_reported_urls(self, cutoff_time: float):
        """清理过期的去重记录"""
        with self.url_cache_lock:
            keys_to_remove = []
            for url_key in self.reported_urls:
                # url_key 格式: "url_timestamp"
                try:
                    timestamp = int(url_key.split("_")[-1])
                    if timestamp < cutoff_time:
                        keys_to_remove.append(url_key)
                except:
                    pass
            for key in keys_to_remove:
                self.reported_urls.discard(key)

            # 清理过期的 history
            expired_urls = [
                url
                for url, last_time in self.report_history.items()
                if last_time < cutoff_time
            ]
            for url in expired_urls:
                self.report_history.pop(url, None)

    def track_active_browsers(self):
        """跟踪活跃浏览器"""
        current_time = time.time()
        foreground = self.get_foreground_browser()

        with self.lock:
            # 更新当前活跃的URL
            if foreground:
                pid = foreground["pid"]
                url = self.extract_url_from_title(foreground.get("window_title", ""))

                if pid in self.active_urls:
                    # 更新结束时间
                    self.active_urls[pid]["last_seen"] = current_time
                else:
                    # 新活跃
                    self.active_urls[pid] = {
                        "pid": pid,
                        "browser": foreground["browser"],
                        "url": url or "unknown",
                        "title": foreground.get("window_title", ""),
                        "start_time": current_time,
                        "last_seen": current_time,
                    }

            # 清理不活跃的
            to_remove = []
            for pid, info in self.active_urls.items():
                if current_time - info["last_seen"] > 30:  # 30秒无活动
                    # 计算停留时间
                    duration = int(info["last_seen"] - info["start_time"])
                    if duration >= 10:  # 超过10秒才记录
                        self._save_url_activity(info, duration)
                    to_remove.append(pid)

            for pid in to_remove:
                del self.active_urls[pid]

    def _save_url_activity(self, info: Dict, duration: int):
        """保存URL活动记录"""
        if not self.client.employee_id:
            return

        data = {
            "employee_id": self.client.employee_id,
            "client_id": self.client.client_id,
            "url": info.get("url", "unknown"),
            "title": info.get("title", ""),
            "browser": info.get("browser", "unknown"),
            "duration": duration,
            "visit_time": datetime.fromtimestamp(info["start_time"]).isoformat(),
        }

        # 缓存到本地，等待上报
        cache_file = Path("cache") / f"browser_{info['start_time']}.json"
        cache_file.parent.mkdir(exist_ok=True)
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def collect_and_report(self):
        """收集并上报浏览器历史"""
        current_time = time.time()

        if current_time - self.last_report_time < self.report_interval:
            return

        self.logger.info("开始收集浏览器历史...")

        # 1. 从数据库读取历史记录
        history = self.read_chrome_history()

        # 2. 从缓存读取活跃记录
        cache_files = list(Path("cache").glob("browser_*.json"))
        for cache_file in cache_files:
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # ✅ 确保每个缓存文件是单个字典，而不是列表
                if isinstance(data, dict):
                    history.append(data)
                elif isinstance(data, list):
                    history.extend(data)
                else:
                    self.logger.warning(f"未知的缓存数据格式: {type(data)}")
                cache_file.unlink()
            except Exception as e:
                self.logger.error(f"读取缓存失败 {cache_file}: {e}")

        # ===== ✅ 关键修复：过滤掉带有数字后缀的字段 =====
        valid_history = []
        for item in history:
            # 如果是字典，提取需要的字段
            if isinstance(item, dict):
                # 只保留标准字段
                clean_item = {
                    "employee_id": item.get("employee_id") or self.client.employee_id,
                    "client_id": item.get("client_id") or self.client.client_id,
                    "url": item.get("url", "unknown"),
                    "title": item.get("title", ""),
                    "browser": item.get("browser", "unknown"),
                    "duration": int(item.get("duration", 0)),
                    "visit_time": item.get("visit_time", datetime.now().isoformat()),
                }

                # 确保 visit_time 是字符串
                if isinstance(clean_item["visit_time"], datetime):
                    clean_item["visit_time"] = clean_item["visit_time"].isoformat()

                # 只保留有效记录
                if clean_item["employee_id"] and clean_item["visit_time"]:
                    valid_history.append(clean_item)
                else:
                    self.logger.warning(f"跳过无效记录: {item}")
            else:
                self.logger.warning(f"跳过非字典记录: {item}")

        self.logger.info(f"有效记录: {len(valid_history)}/{len(history)} 条")

        # 3. 上报到服务器
        if valid_history and self.client.api_client and not self.client.offline_mode:
            try:
                # ✅ 打印第一条数据用于调试
                if valid_history:
                    self.logger.info(f"第一条数据: {valid_history[0]}")

                response = self.client.api_client.post(
                    "/api/browser/history", json=valid_history
                )
                if response:
                    self.logger.info(f"✅ 浏览器历史上报成功: {len(valid_history)}条")
                    self.last_report_time = current_time
                else:
                    self.logger.warning("上报失败，保留缓存")
                    for item in valid_history:
                        cache_file = Path("cache") / f"browser_{time.time()}.json"
                        with open(cache_file, "w", encoding="utf-8") as f:
                            json.dump(item, f)
            except Exception as e:
                self.logger.error(f"上报浏览器历史失败: {e}")
                for item in valid_history:
                    cache_file = Path("cache") / f"browser_{time.time()}.json"
                    with open(cache_file, "w", encoding="utf-8") as f:
                        json.dump(item, f)
        else:
            self.logger.debug("离线模式或无数据，保存到缓存")
            for item in valid_history:
                cache_file = Path("cache") / f"browser_{time.time()}.json"
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump(item, f)

    def start_monitoring(self):
        """启动监控线程"""

        def monitor_loop():
            while self.client.running:
                try:
                    self.track_active_browsers()
                    self.collect_and_report()
                    time.sleep(5)
                except Exception as e:
                    self.logger.error(f"浏览器监控异常: {e}")
                    time.sleep(30)

        thread = threading.Thread(target=monitor_loop, daemon=True)
        thread.start()
        self.logger.info("✅ 浏览器监控已启动")
