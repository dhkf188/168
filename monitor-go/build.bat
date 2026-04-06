@echo off
echo ========================================
echo 编译员工监控系统
echo ========================================

REM 检查图标文件
if not exist "icon.ico" (
    echo 警告: icon.ico 不存在，将使用默认图标
    set ICON_FLAG=
) else (
    echo 找到图标: icon.ico
    set ICON_FLAG=icon.ico
)

REM 清理旧文件
if exist monitor.exe del monitor.exe
if exist *.syso del *.syso

REM 如果存在图标，生成资源文件
if defined ICON_FLAG (
    echo 生成图标资源...
    rsrc -ico icon.ico -o monitor.syso
    if %errorlevel% neq 0 (
        echo 图标资源生成失败，继续编译...
        set ICON_FLAG=
    )
)

REM 编译
echo 编译中...
go build -ldflags="-H windowsgui -s -w" -tags windows -o monitor.exe .

if %errorlevel% equ 0 (
    echo ========================================
    echo 编译成功！输出文件: monitor.exe
    echo ========================================
) else (
    echo 编译失败！
)

pause