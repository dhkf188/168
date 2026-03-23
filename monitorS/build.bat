@echo off
chcp 65001 >nul
title 员工监控系统打包工具 v4.1（含远程屏幕）
color 0A

:: ===== 参数处理 =====
set "CLEAN_MODE=0"
if "%1"=="--clean" set "CLEAN_MODE=1"
if "%1"=="-c" set "CLEAN_MODE=1"

echo ========================================
echo   员工监控系统客户端打包工具 v4.1
echo   包含：远程屏幕、浏览器监控、软件监控、
echo         文件监控、截图监控、健康监控
echo ========================================
echo.

:: ===== 检查Python =====
echo [1/10] 检查Python环境...
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到Python，请安装Python 3.8+
    pause
    exit /b 1
)

:: 检查Python版本
python -c "import sys; exit(0 if sys.version_info >= (3,8) else 1)" >nul 2>&1
if errorlevel 1 (
    echo [警告] 建议使用 Python 3.8+，当前版本可能不兼容
    choice /c YN /m "是否继续"
    if errorlevel 2 exit /b 1
)

:: ===== 清理模式 =====
if "%CLEAN_MODE%"=="1" (
    echo [信息] 清理模式：删除旧虚拟环境...
    if exist venv rmdir /s /q venv
    if exist dist rmdir /s /q dist
    if exist build rmdir /s /q build
)

:: ===== 虚拟环境 =====
echo [2/10] 配置虚拟环境...
if not exist venv\Scripts\activate (
    echo 创建虚拟环境...
    python -m venv venv
)

:: 激活虚拟环境
call venv\Scripts\activate

:: ===== 升级pip =====
echo [3/10] 升级pip...
python -m pip install --upgrade pip

:: ===== 安装依赖 =====
echo [4/10] 安装依赖...
if exist client_requirements.txt (
    pip install -r client_requirements.txt
) else (
    echo [错误] client_requirements.txt 不存在！
    pause
    exit /b 1
)

:: 单独安装pyinstaller
pip install pyinstaller

:: ===== 清理旧文件 =====
echo [5/10] 清理旧文件...
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build

:: ===== 检查必要文件 =====
echo [6/10] 检查必要文件...
set "MISSING_FILES=0"

:: 核心文件
for %%f in (
    client.py
    client_core.py
    client_i18n.py
    client_tray.py
    client_gui.py
    client_config.py
    client_utils.py
) do (
    if not exist %%f (
        echo [警告] 缺少核心文件: %%f
        set "MISSING_FILES=1"
    )
)

:: 监控模块文件
for %%f in (
    client_browser.py
    client_apps.py
    client_file_monitor.py
    client_remote.py
) do (
    if not exist %%f (
        echo [警告] 缺少监控模块: %%f
        set "MISSING_FILES=1"
    )
)

if "%MISSING_FILES%"=="1" (
    echo.
    echo [警告] 部分文件缺失，可能影响功能
    echo - 远程屏幕功能需要 client_remote.py
    echo - 浏览器监控需要 client_browser.py
    echo - 软件监控需要 client_apps.py
    echo - 文件监控需要 client_file_monitor.py
    choice /c YN /m "是否继续"
    if errorlevel 2 exit /b 1
)

:: ===== 创建版本文件 =====
echo [7/10] 创建版本信息...
(
    echo # -*- coding: utf-8 -*-
    echo.
    echo VSVersionInfo(
    echo   ffi=FixedFileInfo(
    echo     filevers=(4, 1, 0, 0),
    echo     prodvers=(4, 1, 0, 0),
    echo     mask=0x3f,
    echo     flags=0x0,
    echo     OS=0x40004,
    echo     fileType=0x1,
    echo     subtype=0x0,
    echo     date=(0, 0)
    echo   ),
    echo   kids=[
    echo     StringFileInfo(
    echo       [
    echo       StringTable(
    echo         '040904B0',
    echo         [StringStruct('CompanyName', '员工监控系统'),
    echo          StringStruct('FileDescription', '员工监控系统客户端 - 企业版'),
    echo          StringStruct('FileVersion', '4.1.0.0'),
    echo          StringStruct('InternalName', 'employee_monitor'),
    echo          StringStruct('LegalCopyright', 'Copyright © 2024'),
    echo          StringStruct('OriginalFilename', '员工监控系统客户端.exe'),
    echo          StringStruct('ProductName', '员工监控系统'),
    echo          StringStruct('ProductVersion', '4.1.0.0')]
    echo       )]
    echo     ),
    echo     VarFileInfo([VarStruct('Translation', [1033, 1200])])
    echo   ]
    echo )
) > version.txt

:: ===== 图标检查 =====
if not exist icon.ico (
    echo [警告] 图标文件 icon.ico 不存在，将使用默认图标
    set "ICON_OPT="
) else (
    set "ICON_OPT=--icon=icon.ico"
)

:: ===== 开始打包 =====
echo [8/10] 开始打包程序...
echo 这可能需要几分钟，请耐心等待...
echo.
echo 正在打包，请勿关闭窗口...

pyinstaller --onefile ^
    --noconsole ^
    --name "员工监控系统客户端" ^
    %ICON_OPT% ^
    --version-file=version.txt ^
    --add-data "client_core.py;." ^
    --add-data "client_i18n.py;." ^
    --add-data "client_tray.py;." ^
    --add-data "client_gui.py;." ^
    --add-data "client_config.py;." ^
    --add-data "client_utils.py;." ^
    --add-data "icon.ico;." ^
    --add-data "client_browser.py;." ^
    --add-data "client_apps.py;." ^
    --add-data "client_file_monitor.py;." ^
    --add-data "client_remote.py;." ^
    --hidden-import tkinter ^
    --hidden-import ttkthemes ^
    --hidden-import PIL._tkinter_finder ^
    --hidden-import winreg ^
    --hidden-import wmi ^
    --hidden-import psutil ^
    --hidden-import pystray ^
    --hidden-import plyer ^
    --hidden-import cryptography ^
    --hidden-import imagehash ^
    --hidden-import mss ^
    --hidden-import portalocker ^
    --hidden-import client_browser ^
    --hidden-import client_apps ^
    --hidden-import client_file_monitor ^
    --hidden-import client_remote ^
    --hidden-import watchdog ^
    --hidden-import websockets ^
    --hidden-import cv2 ^
    --hidden-import numpy ^
    --hidden-import pyzbar ^
    --hidden-import asyncio ^
    --hidden-import sqlite3 ^
    --collect-all ttkthemes ^
    client.py

:: ===== 检查打包结果 =====
if errorlevel 1 (
    echo [错误] 打包失败！
    echo.
    echo 常见问题：
    echo 1. 检查所有Python依赖是否安装成功
    echo    - 运行：pip list
    echo 2. 检查 OpenCV 是否安装正确
    echo    - 运行：python -c "import cv2; print(cv2.__version__)"
    echo 3. 尝试以管理员身份运行
    echo 4. 使用 --clean 参数重新打包
    echo.
    echo 按任意键查看详细日志...
    pause >nul
    if exist build\*.warn-*.txt (
        type build\*.warn-*.txt
    )
    pause
    exit /b 1
)

:: ===== 复制配置文件 =====
echo [9/10] 准备输出文件...

:: 复制配置文件
if exist config.json (
    copy config.json dist\ >nul
    echo ✓ 配置文件已复制
) else (
    echo {} > dist\config.json
    echo ✓ 默认配置文件已创建
)

:: 复制说明文档
copy 使用说明.txt dist\ >nul 2>&1

:: 创建详细说明文档
(
    echo ========================================
    echo    员工监控系统客户端 v4.1（企业版）
    echo ========================================
    echo.
    echo 【功能模块】
    echo.
    echo 1. 基础监控
    echo    ✓ 屏幕截图监控
    echo    ✓ 多显示器支持
    echo    ✓ 相似度检测（节省存储）
    echo    ✓ 智能上传队列
    echo.
    echo 2. 远程屏幕（新增）
    echo    ✓ 实时屏幕查看
    echo    ✓ 动态帧率控制（1-10fps）
    echo    ✓ 动态画质调节（30-95%%）
    echo    ✓ 差异帧传输（节省带宽）
    echo    ✓ 区域编码（ROI检测）
    echo    ✓ H.264硬件加速
    echo    ✓ 弱网自适应
    echo    ✓ 二维码检测
    echo    ✓ 多管理员同时查看
    echo.
    echo 3. 行为监控
    echo    ✓ 浏览器历史记录
    echo    ✓ 软件使用统计
    echo    ✓ 文件操作监控
    echo.
    echo 4. 系统功能
    echo    ✓ 健康监控系统
    echo    ✓ 进程看门狗
    echo    ✓ 智能功耗管理
    echo    ✓ 错误恢复系统
    echo    ✓ 数据加密
    echo    ✓ 国际化支持
    echo.
    echo 【快速开始】
    echo.
    echo 1. 首次运行会自动弹出姓名输入窗口
    echo 2. 程序启动后在系统托盘运行
    echo 3. 右键托盘图标可查看状态和设置
    echo 4. 管理员可在后台查看远程屏幕
    echo.
    echo 【默认服务器】
    echo.
	echo - https://trade-1.cc
    echo - http://localhost:8000
    echo.
    echo 【配置文件 config.json】
    echo.
    echo {
    echo   "server_urls": ["http://localhost:8000"],
    echo   "interval": 60,
    echo   "quality": 80,
    echo   "format": "webp",
    echo   "enable_remote_screen": true,
    echo   "remote_base_fps": 5,
    echo   "remote_min_fps": 1,
    echo   "remote_max_fps": 10,
    echo   "remote_base_quality": 70,
    echo   "remote_min_quality": 30,
    echo   "remote_max_quality": 85,
    echo   "remote_max_width": 1280,
    echo   "remote_min_width": 640,
    echo   "remote_enable_diff": true,
    echo   "remote_enable_region": true,
    echo   "remote_enable_h264": true,
    echo   "remote_enable_qr": false
    echo }
    echo.
    echo 【版本信息】
    echo.
    echo 版本：4.1.0
    echo 日期：2024-03-20
    echo.
    echo 【技术支持】
    echo.
    echo 如有问题，请联系系统管理员
    echo.
    echo ========================================
) > dist\README.txt

:: ===== 显示结果 =====
echo [10/10] 打包完成！
echo.
echo ========================================
echo   打包成功！ 🎉
echo ========================================
echo.
echo 输出目录: %CD%\dist
echo 可执行文件: 员工监控系统客户端.exe
echo.
for %%I in (dist\员工监控系统客户端.exe) do (
    set "FILESIZE=%%~zI"
    set /a "FILESIZE_KB=%%~zI / 1024"
    set /a "FILESIZE_MB=%%~zI / 1024 / 1024"
)
echo 文件大小: %FILESIZE_MB% MB (%FILESIZE_KB% KB)
echo.
echo 包含功能:
echo   ✓ 远程屏幕（弱网优化）
echo   ✓ 浏览器监控
echo   ✓ 软件监控
echo   ✓ 文件监控
echo   ✓ 截图监控
echo   ✓ 健康监控
echo.
echo 按任意键打开输出目录并退出...
pause >nul
start dist
exit /b 0