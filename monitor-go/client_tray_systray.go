// client_tray_systray.go - 修正

// 在文件开头添加 build tag
//go:build windows
// +build windows

package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/getlantern/systray"
)

// TrayManager 系统托盘管理器
type TrayManager struct {
    client               *MonitorClient
    running              bool
    mu                   sync.RWMutex
    lastNotification     map[string]time.Time
    notificationCooldown time.Duration
    quitCh               chan struct{}
    // 菜单项引用
    statusMenuItem     *systray.MenuItem
    healthMenuItem     *systray.MenuItem
    pauseMenuItem      *systray.MenuItem
    resumeMenuItem     *systray.MenuItem
    screenshotMenuItem *systray.MenuItem
    queueMenuItem      *systray.MenuItem
    cleanupMenuItem    *systray.MenuItem
    networkMenuItem    *systray.MenuItem
    reconfigureMenuItem *systray.MenuItem
    autoStartMenuItem  *systray.MenuItem
    hardwareMenuItem   *systray.MenuItem
    logMenuItem        *systray.MenuItem
    exitMenuItem       *systray.MenuItem
}

// NewTrayManager 创建系统托盘管理器
func NewTrayManager(client *MonitorClient) *TrayManager {
    return &TrayManager{
        client:               client,
        lastNotification:     make(map[string]time.Time),
        notificationCooldown: 60 * time.Second,
        quitCh:               make(chan struct{}),
    }
}

// Run 运行系统托盘
func (t *TrayManager) Run() {
    t.mu.Lock()
    if t.running {
        t.mu.Unlock()
        return
    }
    t.running = true
    t.mu.Unlock()

    // 启动 systray
    systray.Run(t.onReady, t.onExit)
}

// onReady systray 就绪回调
func (t *TrayManager) onReady() {
    // 设置图标
    t.setIcon()

    // 设置提示文本
    systray.SetTooltip("员工监控系统 v" + Version)

    // 创建菜单
    t.createMenu()

    // 启动状态更新
    go t.updateStatusLoop()

    // 显示启动通知
    t.showNotification("员工监控系统", "程序已启动，将在系统托盘中运行")

    logInfo("系统托盘已启动")
}

// onExit systray 退出回调
func (t *TrayManager) onExit() {
    t.mu.Lock()
    defer t.mu.Unlock()
    t.running = false
}

// setIcon 设置图标
func (t *TrayManager) setIcon() {
    // 尝试加载自定义图标
    iconPaths := []string{
        "resources/icon.ico",
        "icon.ico",
        "app.ico",
        "icon.png",
        "resources/icon.png",
    }

    for _, path := range iconPaths {
        if data, err := os.ReadFile(path); err == nil {
            systray.SetIcon(data)
            return
        }
    }

    // 如果没有找到图标文件，使用内置默认图标
    systray.SetIcon(t.getDefaultIcon())
}

// getDefaultIcon 获取默认图标（16x16 黑色方块）
func (t *TrayManager) getDefaultIcon() []byte {
    // 创建一个简单的 16x16 黑色图标
    // 实际使用时建议准备一个真正的 .ico 文件
    iconData := make([]byte, 16*16*4) // RGBA 格式
    for i := range iconData {
        if i%4 == 3 {
            iconData[i] = 255 // Alpha
        } else if i%4 < 3 {
            iconData[i] = 0 // RGB 黑色
        }
    }
    return iconData
}

// client_tray_systray.go - 修复 createMenu 方法

func (t *TrayManager) createMenu() {
    // 状态菜单项 - tooltip 也使用国际化
    t.statusMenuItem = systray.AddMenuItem(GetText("show_status"), GetText("show_status"))
    go func() {
        for range t.statusMenuItem.ClickedCh {
            t.showStatusDialog()
        }
    }()

    systray.AddSeparator()

    // 健康状态
    t.healthMenuItem = systray.AddMenuItem(GetText("health_status"), GetText("health_status"))
    go func() {
        for range t.healthMenuItem.ClickedCh {
            t.showHealthDialog()
        }
    }()

    systray.AddSeparator()

    // 暂停监控
    t.pauseMenuItem = systray.AddMenuItem(GetText("pause_monitor"), GetText("pause_monitor"))
    go func() {
        for range t.pauseMenuItem.ClickedCh {
            t.pauseMonitor()
        }
    }()

    // 恢复监控
    t.resumeMenuItem = systray.AddMenuItem(GetText("resume_monitor"), GetText("resume_monitor"))
    t.resumeMenuItem.Hide()
    go func() {
        for range t.resumeMenuItem.ClickedCh {
            t.resumeMonitor()
        }
    }()

    systray.AddSeparator()

    // 立即截图
    t.screenshotMenuItem = systray.AddMenuItem(GetText("screenshot_now"), GetText("screenshot_now"))
    go func() {
        for range t.screenshotMenuItem.ClickedCh {
            t.takeScreenshotNow()
        }
    }()

    systray.AddSeparator()

    // 上传队列
    t.queueMenuItem = systray.AddMenuItem(GetText("upload_queue"), GetText("upload_queue"))
    go func() {
        for range t.queueMenuItem.ClickedCh {
            t.showQueueDialog()
        }
    }()

    // 清理缓存
    t.cleanupMenuItem = systray.AddMenuItem(GetText("cleanup_cache"), GetText("cleanup_cache"))
    go func() {
        for range t.cleanupMenuItem.ClickedCh {
            t.cleanupCache()
        }
    }()

    systray.AddSeparator()

    // 网络诊断
    t.networkMenuItem = systray.AddMenuItem(GetText("network_diagnostic"), GetText("network_diagnostic"))
    go func() {
        for range t.networkMenuItem.ClickedCh {
            t.showNetworkDiagnostic()
        }
    }()

    systray.AddSeparator()

    // 重新配置
    t.reconfigureMenuItem = systray.AddMenuItem(GetText("reconfigure"), GetText("reconfigure"))
    go func() {
        for range t.reconfigureMenuItem.ClickedCh {
            t.reconfigure()
        }
    }()

    // 开机自启
    t.autoStartMenuItem = systray.AddMenuItem(t.getAutoStartText(), GetText("autostart"))
    go func() {
        for range t.autoStartMenuItem.ClickedCh {
            t.toggleAutoStart()
            t.autoStartMenuItem.SetTitle(t.getAutoStartText())
        }
    }()

    systray.AddSeparator()

    // 硬件信息
    t.hardwareMenuItem = systray.AddMenuItem(GetText("hardware_info"), GetText("hardware_info"))
    go func() {
        for range t.hardwareMenuItem.ClickedCh {
            t.showHardwareDialog()
        }
    }()

    systray.AddSeparator()

    // 查看日志
    t.logMenuItem = systray.AddMenuItem(GetText("view_log"), GetText("view_log"))
    go func() {
        for range t.logMenuItem.ClickedCh {
            t.viewLog()
        }
    }()

    systray.AddSeparator()

    // 退出
    t.exitMenuItem = systray.AddMenuItem(GetText("exit"), GetText("exit"))
    go func() {
        for range t.exitMenuItem.ClickedCh {
            t.exitApp()
        }
    }()

    // 初始化菜单状态
    t.updateMenuState()
}

// updateMenuState 更新菜单状态
func (t *TrayManager) updateMenuState() {
    paused := atomic.LoadInt32(&t.client.paused) == 1

    if paused {
        t.pauseMenuItem.Hide()
        t.resumeMenuItem.Show()
    } else {
        t.pauseMenuItem.Show()
        t.resumeMenuItem.Hide()
    }
}

// getAutoStartText 获取开机自启菜单文本
func (t *TrayManager) getAutoStartText() string {
    if t.client.IsAutoStartEnabled() {
        return GetText("autostart") + " ✓"
    }
    return GetText("autostart")
}

// updateToolTip 更新托盘提示
func (t *TrayManager) updateToolTip() {
    status := "●"
    if atomic.LoadInt32(&t.client.paused) == 1 {
        status = "⏸"
    } else if atomic.LoadInt32(&t.client.offlineMode) == 1 {
        status = "○"
    }

    stats := t.client.GetStats()
    screenshots, _ := stats["screenshots_taken"].(int)

    tooltip := fmt.Sprintf("%s 员工监控系统\n截图: %d\n员工: %s\n服务器: %s",
        status, screenshots, t.client.employeeID, t.client.currentServer)
    systray.SetTooltip(tooltip)
}

// updateStatusLoop 状态更新循环
func (t *TrayManager) updateStatusLoop() {
    ticker := time.NewTicker(3 * time.Second)
    defer ticker.Stop()

    for {
        select {
        case <-ticker.C:
            if t.client != nil && atomic.LoadInt32(&t.client.running) == 1 {
                t.updateToolTip()
                t.updateMenuState()
                t.autoStartMenuItem.SetTitle(t.getAutoStartText())
            }
        case <-t.quitCh:
            return
        }
    }
}

// showStatusDialog 显示状态对话框
func (t *TrayManager) showStatusDialog() {
    stats := t.client.GetStats()
    uptime, _ := stats["uptime"].(float64)
    hours := int(uptime / 3600)
    minutes := int((uptime - float64(hours*3600)) / 60)

    statusIcon := "●"
    if atomic.LoadInt32(&t.client.paused) == 1 {
        statusIcon = "⏸"
    } else if atomic.LoadInt32(&t.client.offlineMode) == 1 {
        statusIcon = "○"
    }

    queueSize := 0
    if t.client.uploadQueue != nil {
        qs := t.client.uploadQueue.GetStats()
        if size, ok := qs["queue_size"].(int); ok {
            queueSize = size
        }
    }

    message := fmt.Sprintf(
        "状态: %s\n\n"+
            "员工ID: %s\n"+
            "客户端ID: %s\n"+
            "服务器: %s\n\n"+
            "运行时间: %d小时%d分钟\n"+
            "截图数量: %d\n"+
            "上传成功: %d\n"+
            "跳过相似: %d\n"+
            "上传失败: %d\n"+
            "队列大小: %d\n\n"+
            "离线模式: %v\n"+
            "暂停状态: %v",
        statusIcon,
        t.client.employeeID,
        t.client.clientID,
        t.client.currentServer,
        hours, minutes,
        stats["screenshots_taken"],
        stats["screenshots_uploaded"],
        stats["skipped_similar"],
        stats["upload_failures"],
        queueSize,
        t.client.offlineMode == 1,
        t.client.paused == 1,
    )

    t.showNotification("系统状态", message)
}

// showHealthDialog 显示健康状态
func (t *TrayManager) showHealthDialog() {
    if t.client.healthMonitor == nil {
        t.showNotification("健康状态", "健康监控未启用")
        return
    }

    summary := t.client.healthMonitor.GetSummary()
    message := fmt.Sprintf(
        "健康状态:\n\n健康: %d\n降级: %d\n异常: %d\n未知: %d\n健康率: %.1f%%\n恢复次数: %d",
        summary["healthy"],
        summary["degraded"],
        summary["unhealthy"],
        summary["unknown"],
        summary["health_rate"].(float64)*100,
        summary["total_recoveries"],
    )

    t.showNotification("健康状态", message)
}

// showQueueDialog 显示队列状态
func (t *TrayManager) showQueueDialog() {
    if t.client.uploadQueue == nil {
        t.showNotification("上传队列", "上传队列未启用")
        return
    }

    stats := t.client.uploadQueue.GetStats()
    cacheSizeMB := 0.0
    if size, ok := stats["cache_size"].(int64); ok {
        cacheSizeMB = float64(size) / 1024 / 1024
    }

    message := fmt.Sprintf(
        "上传队列状态:\n\n队列大小: %d/%d\n已处理: %d\n失败: %d\n重试: %d\n缓存文件: %d\n缓存大小: %.2f MB",
        stats["queue_size"],
        stats["queue_maxsize"],
        stats["processed"],
        stats["failed"],
        stats["retried"],
        stats["cache_count"],
        cacheSizeMB,
    )

    t.showNotification("上传队列", message)
}

// showHardwareDialog 显示硬件信息
func (t *TrayManager) showHardwareDialog() {
    info := t.client.GetHardwareInfo()

    reliabilityText := "低"
    if info.Reliability > 0.7 {
        reliabilityText = "高"
    } else if info.Reliability > 0.4 {
        reliabilityText = "中"
    }

    fingerprintShort := info.Fingerprint
    if len(fingerprintShort) > 20 {
        fingerprintShort = fingerprintShort[:20] + "..."
    }

    cpuNameShort := info.CPUName
    if len(cpuNameShort) > 40 {
        cpuNameShort = cpuNameShort[:37] + "..."
    }

    message := fmt.Sprintf(
        "硬件信息\n\nCPU: %s\nCPU ID: %s\n核心数: %d\n\n主板: %s\n主板序列号: %s\n\n磁盘: %s\n磁盘序列号: %s\n\n系统UUID: %s\nBIOS版本: %s\n\n硬件指纹: %s\n可信度: %s (%.1f%%)",
        cpuNameShort,
        info.CPUID,
        info.CPUCores,
        info.MotherboardModel,
        info.MotherboardSN,
        info.DiskModel,
        info.DiskSerial,
        info.UUID,
        info.BIOSVersion,
        fingerprintShort,
        reliabilityText,
        info.Reliability*100,
    )

    t.showNotification("硬件信息", message)
}

// showNetworkDiagnostic 显示网络诊断
func (t *TrayManager) showNetworkDiagnostic() {
    networkOK := t.client.checkBasicNetwork()
    serverOK := false
    if networkOK && t.client.apiClient != nil {
        _, err := t.client.apiClient.Get("/health")
        serverOK = err == nil
    }

    modeText := "在线"
    if t.client.offlineMode == 1 {
        modeText = "离线"
    }

    message := fmt.Sprintf(
        "网络诊断结果:\n\n当前服务器: %s\n客户端ID: %s\n员工ID: %s\n模式: %s\n\n基础网络: %s\n服务器连接: %s",
        t.client.currentServer,
        t.client.clientID,
        t.client.employeeID,
        modeText,
        map[bool]string{true: "✅ 正常", false: "❌ 异常"}[networkOK],
        map[bool]string{true: "✅ 正常", false: "❌ 异常"}[serverOK],
    )

    t.showNotification("网络诊断", message)
}

// viewLog 查看日志
// client_tray_systray.go - 修复 viewLog 函数

func (t *TrayManager) viewLog() {
    // 获取可执行文件所在目录
    exePath, err := os.Executable()
    if err != nil {
        t.showNotification("查看日志", "无法获取程序路径: "+err.Error())
        return
    }
    exeDir := filepath.Dir(exePath)
    
    // 构建日志文件完整路径
    logFile := filepath.Join(exeDir, "logs", "monitor.log")
    
    // 检查文件是否存在
    if _, err := os.Stat(logFile); os.IsNotExist(err) {
        t.showNotification("查看日志", "日志文件不存在: "+logFile)
        return
    }
    
    data, err := os.ReadFile(logFile)
    if err != nil {
        t.showNotification("查看日志", "无法读取日志文件: "+err.Error())
        return
    }

    lines := strings.Split(string(data), "\n")
    start := len(lines) - 50
    if start < 0 {
        start = 0
    }

    logContent := strings.Join(lines[start:], "\n")
    if len(logContent) > 3000 {
        logContent = logContent[:3000] + "\n...(日志内容过长，已截断)"
    }
    
    if logContent == "" {
        logContent = "暂无日志内容"
    }

    t.showNotification("最近日志 (最后50行)", logContent)
}

// pauseMonitor 暂停监控
func (t *TrayManager) pauseMonitor() {
    atomic.StoreInt32(&t.client.paused, 1)
    t.updateMenuState()
    t.showNotification("监控", "监控已暂停")
}

// resumeMonitor 恢复监控
func (t *TrayManager) resumeMonitor() {
    atomic.StoreInt32(&t.client.paused, 0)
    t.updateMenuState()
    t.showNotification("监控", "监控已恢复")
}

// takeScreenshotNow 立即截图
func (t *TrayManager) takeScreenshotNow() {
    atomic.StoreInt32(&t.client.takeScreenshotNow, 1)
    t.showNotification("截图", "已触发立即截图")
}

// cleanupCache 清理缓存
func (t *TrayManager) cleanupCache() {
    if t.client.uploadQueue != nil {
        t.client.uploadQueue.cleanupCache()
        t.showNotification("缓存清理", "缓存清理完成")
    }
}

// toggleAutoStart 切换开机自启
func (t *TrayManager) toggleAutoStart() {
    enabled := t.client.IsAutoStartEnabled()

    if enabled {
        if err := t.client.DisableAutoStart(); err != nil {
            t.showNotification("开机自启", "禁用失败: "+err.Error())
        } else {
            t.showNotification("开机自启", "已禁用开机自启")
        }
    } else {
        if err := t.client.EnableAutoStart(); err != nil {
            t.showNotification("开机自启", "启用失败: "+err.Error())
        } else {
            t.showNotification("开机自启", "已启用开机自启")
        }
    }
}

// reconfigure 重新配置
func (t *TrayManager) reconfigure() {
    t.client.forceReconfigure = true
    t.client.firstRun = true

    if t.client.configManager != nil {
        t.client.configManager.Set("force_reconfigure", true)
    }

    t.showNotification("重新配置", "请在重启后重新配置")
    t.exitApp()
}

// exitApp 退出程序
func (t *TrayManager) exitApp() {
    if t.client != nil {
        t.client.Stop()
    }
    close(t.quitCh)
    systray.Quit()
}

// showNotification 显示系统通知
func (t *TrayManager) showNotification(title, message string) {
    t.mu.Lock()
    defer t.mu.Unlock()

    now := time.Now()
    key := title + "_" + message[:minInt(len(message), 50)]

    if lastTime, ok := t.lastNotification[key]; ok {
        if now.Sub(lastTime) < t.notificationCooldown {
            return
        }
    }

    t.lastNotification[key] = now

    // 输出到日志
    logInfo("[通知] %s: %s", title, message)
}

