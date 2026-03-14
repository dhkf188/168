@echo off
chcp 65001 >nul
title 员工监控系统打包工具
color 0A

echo ========================================
echo   员工监控系统客户端打包工具 v3.0
echo ========================================
echo.

:: 检查虚拟环境
if not exist venv\Scripts\activate (
    echo [1/8] 创建虚拟环境...
    python -m venv venv
)

:: 激活虚拟环境
echo [2/8] 激活虚拟环境...
call venv\Scripts\activate

:: 安装依赖
echo [3/8] 安装依赖...
pip install -r client_requirements.txt pyinstaller

:: 清理旧文件
echo [4/8] 清理旧文件...
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build

:: 开始打包
echo [5/8] 开始打包程序...
pyinstaller --onefile ^
    --noconsole ^
    --name "员工监控系统客户端" ^
    --icon=icon.ico ^
    --version-file=version.txt ^
    --add-data "client_gui.py;." ^
    --add-data "client_utils.py;." ^
    --add-data "client_config.py;." ^
    --add-data "icon.ico;." ^
    --hidden-import tkinter ^
    --hidden-import ttkthemes ^
    --hidden-import PIL._tkinter_finder ^
    --hidden-import winreg ^
    --hidden-import wmi ^
    --hidden-import psutil ^
    --hidden-import pystray ^
    --hidden-import plyer ^
    --hidden-import cryptography ^
    --hidden-import netifaces ^
    --hidden-import imagehash ^
    --hidden-import mss ^
    --collect-all ttkthemes ^
    client.py

:: 检查打包是否成功
if errorlevel 1 (
    echo [错误] 打包失败！
    echo.
    echo 常见问题：
    echo 1. 确保所有依赖都已安装
    echo 2. 检查 client_gui.py 是否存在
    echo 3. 尝试以管理员身份运行
    pause
    exit /b 1
)

:: 复制配置文件
echo [6/8] 复制配置文件...
if exist config.json (
    copy config.json dist\
    echo 配置文件已复制
) else (
    echo 创建默认配置文件...
    echo {} > dist\config.json
    echo 默认配置文件已创建
)

:: 创建说明文件
echo [7/8] 创建使用说明...
(
    echo 员工监控系统客户端 v3.2
    echo ======================
    echo.
    echo 使用说明：
    echo 1. 首次运行会自动弹出窗口输入姓名
    echo 2. 程序会在系统托盘运行
    echo 3. 右键托盘图标可查看状态、暂停监控
    echo 4. 开机自启功能可在托盘图标菜单设置
    echo.
    echo 默认服务器: https://one68-2ykz.onrender.com
    echo 备用服务器: http://localhost:8000
    echo.
    echo 功能特性：
    echo - 健康监控系统
    echo - 上传队列系统
    echo - 缓冲区池系统
    echo - 多显示器截图
    echo - 感知哈希相似度检测
    echo - 进程看门狗
    echo - 原子文件操作
    echo.
    echo 技术支持：请联系管理员
    echo 版本日期：2024-03-14
) > dist\使用说明.txt

:: 显示结果
echo [8/8] 打包完成！
echo.
echo ========================================
echo   打包成功！
echo ========================================
echo.
echo 输出目录: %CD%\dist
echo 可执行文件: 员工监控系统客户端.exe
echo.
echo 文件大小:
for %%I in (dist\员工监控系统客户端.exe) do echo %%~zI 字节
echo.
echo 按任意键打开输出目录...
pause >nul
start dist