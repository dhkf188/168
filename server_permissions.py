# server_permissions.py - 完整无遗漏版

from enum import Enum


class PermissionCode(Enum):
    """权限代码枚举 - 所有可管理的权限"""

    # ===== 仪表盘 =====
    DASHBOARD_VIEW = "dashboard:view"

    # ===== 员工管理 =====
    EMPLOYEE_VIEW = "employee:view"
    EMPLOYEE_CREATE = "employee:create"
    EMPLOYEE_UPDATE = "employee:update"
    EMPLOYEE_DELETE = "employee:delete"

    # ===== 截图查看 =====
    SCREENSHOT_VIEW = "screenshot:view"
    SCREENSHOT_DOWNLOAD = "screenshot:download"
    SCREENSHOT_DELETE = "screenshot:delete"

    # ===== 客户端管理 =====
    CLIENT_VIEW = "client:view"
    CLIENT_UPDATE = "client:update"
    CLIENT_DELETE = "client:delete"

    # ===== 浏览器历史 =====
    BROWSER_VIEW = "browser:view"
    BROWSER_DELETE = "browser:delete"

    # ===== 软件统计 =====
    APP_VIEW = "app:view"
    APP_EXPORT = "app:export"

    # ===== 文件监控 =====
    FILE_VIEW = "file:view"
    FILE_EXPORT = "file:export"

    # ===== 数据分析 =====
    STATS_VIEW = "stats:view"
    STATS_EXPORT = "stats:export"

    # ===== 远程屏幕 =====
    REMOTE_VIEW = "remote:view"
    REMOTE_CONTROL = "remote:control"

    # ===== 考勤管理 =====
    ATTENDANCE_VIEW = "attendance:view"
    ATTENDANCE_EDIT = "attendance:edit"

    # ===== 站点管理（出款）=====
    SITE_VIEW = "site:view"
    SITE_EDIT = "site:edit"
    SITE_STATS_VIEW = "site:stats:view"
    SITE_STATS_EXPORT = "site:stats:export"
    SITE_SUMMARY_VIEW = "site:summary:view"
    SITE_SUMMARY_EXPORT = "site:summary:export"
    SITE_SYNC = "site:sync"

    # ===== 系统设置 =====
    SETTINGS_VIEW = "settings:view"
    SETTINGS_UPDATE = "settings:update"
    SETTINGS_CLEANUP = "settings:cleanup"

    # ===== 通知管理 =====
    NOTIFICATION_VIEW = "notification:view"
    NOTIFICATION_MANAGE = "notification:manage"

    # ===== 用户管理 =====
    USER_VIEW = "user:view"
    USER_CREATE = "user:create"
    USER_UPDATE = "user:update"
    USER_DELETE = "user:delete"

    # ===== 角色管理 =====
    ROLE_VIEW = "role:view"
    ROLE_CREATE = "role:create"
    ROLE_UPDATE = "role:update"
    ROLE_DELETE = "role:delete"


# 完整权限分组（用于前端展示）
PERMISSION_GROUPS = {
    "dashboard": {
        "name": "仪表盘",
        "permissions": [
            {"code": PermissionCode.DASHBOARD_VIEW.value, "name": "查看仪表盘"}
        ],
    },
    "employee": {
        "name": "员工管理",
        "permissions": [
            {"code": PermissionCode.EMPLOYEE_VIEW.value, "name": "查看员工"},
            {"code": PermissionCode.EMPLOYEE_CREATE.value, "name": "创建员工"},
            {"code": PermissionCode.EMPLOYEE_UPDATE.value, "name": "编辑员工"},
            {"code": PermissionCode.EMPLOYEE_DELETE.value, "name": "删除员工"},
        ],
    },
    "screenshot": {
        "name": "截图查看",
        "permissions": [
            {"code": PermissionCode.SCREENSHOT_VIEW.value, "name": "查看截图"},
            {"code": PermissionCode.SCREENSHOT_DOWNLOAD.value, "name": "下载截图"},
            {"code": PermissionCode.SCREENSHOT_DELETE.value, "name": "删除截图"},
        ],
    },
    "client": {
        "name": "客户端管理",
        "permissions": [
            {"code": PermissionCode.CLIENT_VIEW.value, "name": "查看客户端"},
            {"code": PermissionCode.CLIENT_UPDATE.value, "name": "编辑客户端"},
            {"code": PermissionCode.CLIENT_DELETE.value, "name": "删除客户端"},
        ],
    },
    "browser": {
        "name": "浏览器历史",
        "permissions": [
            {"code": PermissionCode.BROWSER_VIEW.value, "name": "查看浏览器历史"},
            {"code": PermissionCode.BROWSER_DELETE.value, "name": "删除浏览器历史"},
        ],
    },
    "app": {
        "name": "软件统计",
        "permissions": [
            {"code": PermissionCode.APP_VIEW.value, "name": "查看软件统计"},
            {"code": PermissionCode.APP_EXPORT.value, "name": "导出软件统计"},
        ],
    },
    "file": {
        "name": "文件监控",
        "permissions": [
            {"code": PermissionCode.FILE_VIEW.value, "name": "查看文件操作"},
            {"code": PermissionCode.FILE_EXPORT.value, "name": "导出文件记录"},
        ],
    },
    "stats": {
        "name": "数据分析",
        "permissions": [
            {"code": PermissionCode.STATS_VIEW.value, "name": "查看数据分析"},
            {"code": PermissionCode.STATS_EXPORT.value, "name": "导出分析报告"},
        ],
    },
    "remote": {
        "name": "远程屏幕",
        "permissions": [
            {"code": PermissionCode.REMOTE_VIEW.value, "name": "远程查看屏幕"},
            {"code": PermissionCode.REMOTE_CONTROL.value, "name": "远程控制屏幕"},
        ],
    },
    "attendance": {
        "name": "考勤管理",
        "permissions": [
            {"code": PermissionCode.ATTENDANCE_VIEW.value, "name": "查看考勤"},
            {"code": PermissionCode.ATTENDANCE_EDIT.value, "name": "编辑考勤"},
        ],
    },
    "site": {
        "name": "出款管理",
        "permissions": [
            {
                "code": PermissionCode.SITE_VIEW.value,
                "name": "查看出款管理（站点配置）",
            },
            {"code": PermissionCode.SITE_EDIT.value, "name": "编辑出款管理"},
            {"code": PermissionCode.SITE_STATS_VIEW.value, "name": "查看出款统计"},
            {"code": PermissionCode.SITE_STATS_EXPORT.value, "name": "导出发款统计"},
            {"code": PermissionCode.SITE_SUMMARY_VIEW.value, "name": "查看出款汇总"},
            {"code": PermissionCode.SITE_SUMMARY_EXPORT.value, "name": "导出发款汇总"},
            {"code": PermissionCode.SITE_SYNC.value, "name": "出款同步"},
        ],
    },
    "settings": {
        "name": "系统设置",
        "permissions": [
            {"code": PermissionCode.SETTINGS_VIEW.value, "name": "查看系统设置"},
            {"code": PermissionCode.SETTINGS_UPDATE.value, "name": "修改系统设置"},
            {"code": PermissionCode.SETTINGS_CLEANUP.value, "name": "执行数据清理"},
        ],
    },
    "notification": {
        "name": "通知管理",
        "permissions": [
            {"code": PermissionCode.NOTIFICATION_VIEW.value, "name": "查看通知"},
            {"code": PermissionCode.NOTIFICATION_MANAGE.value, "name": "管理通知"},
        ],
    },
    "user": {
        "name": "用户管理",
        "permissions": [
            {"code": PermissionCode.USER_VIEW.value, "name": "查看用户"},
            {"code": PermissionCode.USER_CREATE.value, "name": "创建用户"},
            {"code": PermissionCode.USER_UPDATE.value, "name": "编辑用户"},
            {"code": PermissionCode.USER_DELETE.value, "name": "删除用户"},
        ],
    },
    "role": {
        "name": "角色管理",
        "permissions": [
            {"code": PermissionCode.ROLE_VIEW.value, "name": "查看角色"},
            {"code": PermissionCode.ROLE_CREATE.value, "name": "创建角色"},
            {"code": PermissionCode.ROLE_UPDATE.value, "name": "编辑角色"},
            {"code": PermissionCode.ROLE_DELETE.value, "name": "删除角色"},
        ],
    },
}


# 预定义角色（用于初始化数据库）
PREDEFINED_ROLES = [
    {
        "name": "admin",
        "display_name": "超级管理员",
        "description": "拥有所有权限",
        "permissions": {"type": "all"},
        "is_system": True,
    },
    {
        "name": "manager",
        "display_name": "管理员",
        "description": "可以管理员工、查看截图和统计，管理出款和考勤",
        "permissions": {
            "type": "custom",
            "permissions": [
                PermissionCode.DASHBOARD_VIEW.value,
                PermissionCode.EMPLOYEE_VIEW.value,
                PermissionCode.EMPLOYEE_CREATE.value,
                PermissionCode.EMPLOYEE_UPDATE.value,
                PermissionCode.SCREENSHOT_VIEW.value,
                PermissionCode.SCREENSHOT_DOWNLOAD.value,
                PermissionCode.CLIENT_VIEW.value,
                PermissionCode.BROWSER_VIEW.value,
                PermissionCode.APP_VIEW.value,
                PermissionCode.FILE_VIEW.value,
                PermissionCode.STATS_VIEW.value,
                PermissionCode.REMOTE_VIEW.value,
                PermissionCode.ATTENDANCE_VIEW.value,
                PermissionCode.ATTENDANCE_EDIT.value,
                PermissionCode.SITE_VIEW.value,
                PermissionCode.SITE_EDIT.value,
                PermissionCode.SETTINGS_VIEW.value,
                PermissionCode.NOTIFICATION_VIEW.value,
                PermissionCode.NOTIFICATION_MANAGE.value,
                PermissionCode.SITE_STATS_VIEW.value,
                PermissionCode.SITE_STATS_EXPORT.value,
                PermissionCode.SITE_SUMMARY_VIEW.value,
                PermissionCode.SITE_SUMMARY_EXPORT.value,
                PermissionCode.SITE_SYNC.value,
            ],
        },
        "is_system": True,
    },
    {
        "name": "viewer",
        "display_name": "查看员",
        "description": "只能查看数据和截图，不能修改",
        "permissions": {
            "type": "custom",
            "permissions": [
                PermissionCode.DASHBOARD_VIEW.value,
                PermissionCode.EMPLOYEE_VIEW.value,
                PermissionCode.SCREENSHOT_VIEW.value,
                PermissionCode.CLIENT_VIEW.value,
                PermissionCode.BROWSER_VIEW.value,
                PermissionCode.APP_VIEW.value,
                PermissionCode.FILE_VIEW.value,
                PermissionCode.STATS_VIEW.value,
                PermissionCode.REMOTE_VIEW.value,
                PermissionCode.ATTENDANCE_VIEW.value,
                PermissionCode.SITE_VIEW.value,
                PermissionCode.NOTIFICATION_VIEW.value,
                PermissionCode.SITE_STATS_VIEW.value,
                PermissionCode.SITE_SUMMARY_VIEW.value,
            ],
        },
        "is_system": True,
    },
    {
        "name": "site_manager",
        "display_name": "出款管理员",
        "description": "管理出款统计、汇总和同步",
        "permissions": {
            "type": "custom",
            "permissions": [
                PermissionCode.DASHBOARD_VIEW.value,
                PermissionCode.SITE_VIEW.value,
                PermissionCode.SITE_EDIT.value,
                PermissionCode.SITE_STATS_VIEW.value,
                PermissionCode.SITE_STATS_EXPORT.value,
                PermissionCode.SITE_SUMMARY_VIEW.value,
                PermissionCode.SITE_SUMMARY_EXPORT.value,
                PermissionCode.SITE_SYNC.value,
            ],
        },
        "is_system": True,
    },
    {
        "name": "attendance_manager",
        "display_name": "考勤管理员",
        "description": "管理员工考勤",
        "permissions": {
            "type": "custom",
            "permissions": [
                PermissionCode.DASHBOARD_VIEW.value,
                PermissionCode.EMPLOYEE_VIEW.value,
                PermissionCode.ATTENDANCE_VIEW.value,
                PermissionCode.ATTENDANCE_EDIT.value,
            ],
        },
        "is_system": True,
    },
]


def has_permission(user_permissions: dict, required_permission: str) -> bool:
    """检查用户是否有指定权限"""
    if not user_permissions:
        return False

    if user_permissions.get("type") == "all":
        return True

    permissions = user_permissions.get("permissions", [])
    return required_permission in permissions


def get_permission_codes(permissions) -> list:
    """获取权限代码列表"""
    if not permissions:
        return []

    if isinstance(permissions, dict):
        if permissions.get("type") == "all":
            return [p.value for p in PermissionCode]
        return permissions.get("permissions", [])

    if isinstance(permissions, list):
        return permissions

    return []
