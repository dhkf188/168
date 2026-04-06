# server_permissions.py
from enum import Enum


class PermissionCode(Enum):
    """权限代码枚举"""

    # 仪表盘
    DASHBOARD_VIEW = "dashboard:view"

    # 员工管理
    EMPLOYEE_VIEW = "employee:view"
    EMPLOYEE_CREATE = "employee:create"
    EMPLOYEE_UPDATE = "employee:update"
    EMPLOYEE_DELETE = "employee:delete"

    # 截图查看
    SCREENSHOT_VIEW = "screenshot:view"
    SCREENSHOT_DOWNLOAD = "screenshot:download"
    SCREENSHOT_DELETE = "screenshot:delete"

    # 客户端管理
    CLIENT_VIEW = "client:view"
    CLIENT_UPDATE = "client:update"
    CLIENT_DELETE = "client:delete"

    # 浏览器历史
    BROWSER_VIEW = "browser:view"
    BROWSER_DELETE = "browser:delete"

    # 软件统计
    APP_VIEW = "app:view"
    APP_EXPORT = "app:export"

    # 文件监控
    FILE_VIEW = "file:view"
    FILE_EXPORT = "file:export"

    # 数据分析
    STATS_VIEW = "stats:view"
    STATS_EXPORT = "stats:export"

    # 远程屏幕
    REMOTE_VIEW = "remote:view"
    REMOTE_CONTROL = "remote:control"

    # 系统设置
    SETTINGS_VIEW = "settings:view"
    SETTINGS_UPDATE = "settings:update"
    SETTINGS_CLEANUP = "settings:cleanup"

    # 通知管理
    NOTIFICATION_VIEW = "notification:view"
    NOTIFICATION_MANAGE = "notification:manage"

    # 用户管理
    USER_VIEW = "user:view"
    USER_CREATE = "user:create"
    USER_UPDATE = "user:update"
    USER_DELETE = "user:delete"
    ROLE_VIEW = "role:view"
    ROLE_CREATE = "role:create"
    ROLE_UPDATE = "role:update"
    ROLE_DELETE = "role:delete"


PERMISSION_GROUPS = {
    "dashboard": {
        "name": "仪表盘",
        "permissions": [{"code": "dashboard:view", "name": "查看仪表盘"}],
    },
    "employee": {
        "name": "员工管理",
        "permissions": [
            {"code": "employee:view", "name": "查看员工"},
            {"code": "employee:create", "name": "创建员工"},
            {"code": "employee:update", "name": "编辑员工"},
            {"code": "employee:delete", "name": "删除员工"},
        ],
    },
    "screenshot": {
        "name": "截图查看",
        "permissions": [
            {"code": "screenshot:view", "name": "查看截图"},
            {"code": "screenshot:download", "name": "下载截图"},
            {"code": "screenshot:delete", "name": "删除截图"},
        ],
    },
    "client": {
        "name": "客户端管理",
        "permissions": [
            {"code": "client:view", "name": "查看客户端"},
            {"code": "client:update", "name": "编辑客户端"},
            {"code": "client:delete", "name": "删除客户端"},
        ],
    },
    "browser": {
        "name": "浏览器历史",
        "permissions": [
            {"code": "browser:view", "name": "查看浏览器历史"},
            {"code": "browser:delete", "name": "删除浏览器历史"},
        ],
    },
    "app": {
        "name": "软件统计",
        "permissions": [
            {"code": "app:view", "name": "查看软件统计"},
            {"code": "app:export", "name": "导出软件统计"},
        ],
    },
    "file": {
        "name": "文件监控",
        "permissions": [
            {"code": "file:view", "name": "查看文件操作"},
            {"code": "file:export", "name": "导出文件记录"},
        ],
    },
    "stats": {
        "name": "数据分析",
        "permissions": [
            {"code": "stats:view", "name": "查看数据分析"},
            {"code": "stats:export", "name": "导出分析报告"},
        ],
    },
    "remote": {
        "name": "远程屏幕",
        "permissions": [
            {"code": "remote:view", "name": "远程查看屏幕"},
            {"code": "remote:control", "name": "远程控制屏幕"},
        ],
    },
    "settings": {
        "name": "系统设置",
        "permissions": [
            {"code": "settings:view", "name": "查看系统设置"},
            {"code": "settings:update", "name": "修改系统设置"},
            {"code": "settings:cleanup", "name": "执行数据清理"},
        ],
    },
    "notification": {
        "name": "通知管理",
        "permissions": [
            {"code": "notification:view", "name": "查看通知"},
            {"code": "notification:manage", "name": "管理通知"},
        ],
    },
    "user": {
        "name": "用户管理",
        "permissions": [
            {"code": "user:view", "name": "查看用户"},
            {"code": "user:create", "name": "创建用户"},
            {"code": "user:update", "name": "编辑用户"},
            {"code": "user:delete", "name": "删除用户"},
            {"code": "role:view", "name": "查看角色"},
            {"code": "role:create", "name": "创建角色"},
            {"code": "role:update", "name": "编辑角色"},
            {"code": "role:delete", "name": "删除角色"},
        ],
    },
}
