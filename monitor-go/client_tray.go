// client_tray.go - 完善菜单处理

package main

import (
	"bufio"
	"fmt"
	"os"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

// TrayIcon 托盘图标管理器
type TrayIcon struct {
    client               *MonitorClient
    running              bool
    lastNotification     map[string]time.Time
    notificationCooldown time.Duration
    mu                   sync.RWMutex
    reader               *bufio.Reader
}

// NewTrayIcon 创建托盘图标
func NewTrayIcon(client *MonitorClient) *TrayIcon {
    return &TrayIcon{
        client:               client,
        lastNotification:     make(map[string]time.Time),
        notificationCooldown: 60 * time.Second,
        reader:               bufio.NewReader(os.Stdin),
    }
}

// Run 运行托盘图标
func (t *TrayIcon) Run() {
    t.running = true
    t.showConsoleMenu()
}

// Stop 停止托盘图标
func (t *TrayIcon) Stop() {
    t.running = false
}

func (t *TrayIcon) showConsoleMenu() {
    for t.running {
        fmt.Println("\n" + strings.Repeat("=", 50))
        fmt.Println("          员工监控系统 v" + Version)
        fmt.Println(strings.Repeat("=", 50))
        
        // 显示当前状态
        t.showStatusLine()
        
        fmt.Println("\n请选择操作:")
        fmt.Println(" 1. 显示详细状态")
        fmt.Println(" 2. 健康状态")
        fmt.Println(" 3. 看门狗状态")
        fmt.Println(" 4. 上传队列状态")
        fmt.Println(" 5. 远程屏幕状态")
        fmt.Println(" 6. 暂停监控")
        fmt.Println(" 7. 恢复监控")
        fmt.Println(" 8. 立即截图")
        fmt.Println(" 9. 清理缓存")
        fmt.Println("10. 网络诊断")
        fmt.Println("11. 重新配置")
        fmt.Println("12. 查看日志")
        
        // ========== 新增菜单项 ==========
        fmt.Println("13. 硬件信息")
        
        autoStartStatus := "❌ 未启用"
        if t.client.IsAutoStartEnabled() {
            autoStartStatus = "✅ 已启用"
        }
        fmt.Printf("14. 开机自启 [%s]\n", autoStartStatus)
        // ================================
        
        fmt.Println("15. 退出程序")
        fmt.Print("\n请输入选项 (1-15): ")
        
        input, err := t.reader.ReadString('\n')
        if err != nil {
            continue
        }
        input = strings.TrimSpace(input)
        
        switch input {
        case "1":
            t.ShowStatus()
        case "2":
            t.ShowHealthStatus()
        case "3":
            t.ShowWatchdogStatus()
        case "4":
            t.ShowQueueStatus()
        case "5":
            t.ShowRemoteStatus()
        case "6":
            t.PauseMonitor()
        case "7":
            t.ResumeMonitor()
        case "8":
            t.TakeScreenshotNow()
        case "9":
            t.CleanupCache()
        case "10":
            t.NetworkDiagnostic()
        case "11":
            t.Reconfigure()
        case "12":
            t.ViewLog()
        // ========== 新增 case ==========
        case "13":
            t.ShowHardwareInfo()
        case "14":
            t.ToggleAutoStartMenu()
        // ================================
        case "15":
            t.ExitApp()
        default:
            fmt.Println("无效选项，请重新输入")
        }
        
        time.Sleep(500 * time.Millisecond)
    }
}

func (t *TrayIcon) showStatusLine() {
    if t.client == nil {
        return
    }
    
    statusIcon := "🟢"
    if atomic.LoadInt32(&t.client.paused) == 1 {
        statusIcon = "⏸️"
    } else if atomic.LoadInt32(&t.client.offlineMode) == 1 {
        statusIcon = "🔴"
    }
    
    stats := t.client.GetStats()
    screenshots, _ := stats["screenshots_taken"].(int)
    
    fmt.Printf("\n状态: %s | 截图: %d | 员工: %s",
        statusIcon, screenshots, t.client.employeeID)
}

// ShowRemoteStatus 显示远程屏幕状态
func (t *TrayIcon) ShowRemoteStatus() {
    if t.client == nil || t.client.remoteScreen == nil {
        t.showNotification("远程屏幕", "远程屏幕未启用")
        return
    }
    
    status := t.client.remoteScreen.GetStatus()
    
    message := fmt.Sprintf(
        "远程屏幕状态:\n"+
            "状态: %s\n"+
            "观众数: %d\n"+
            "当前帧率: %d fps\n"+
            "当前画质: %d%%\n"+
            "当前宽度: %d\n"+
            "已发送帧: %d\n"+
            "已发送字节: %.2f MB\n"+
            "丢弃帧: %d\n"+
            "网络质量: %d",
        status.State,
        status.ViewerCount,
        status.CurrentFPS,
        status.CurrentQuality,
        status.CurrentWidth,
        status.FramesSent,
        float64(status.BytesSent)/1024/1024,
        status.DroppedFrames,
        status.NetworkQuality,
    )
    
    t.showNotification("远程屏幕状态", message)
}

// ViewLog 查看日志
func (t *TrayIcon) ViewLog() {
    logFile := "logs/monitor.log"
    data, err := os.ReadFile(logFile)
    if err != nil {
        t.showNotification("查看日志", "无法读取日志文件: "+err.Error())
        return
    }
    
    // 只显示最后30行
    lines := strings.Split(string(data), "\n")
    start := len(lines) - 30
    if start < 0 {
        start = 0
    }
    
    fmt.Println("\n" + strings.Repeat("=", 60))
    fmt.Println("最近日志 (最后30行)")
    fmt.Println(strings.Repeat("=", 60))
    
    for i := start; i < len(lines); i++ {
        if lines[i] != "" {
            fmt.Println(lines[i])
        }
    }
    
    fmt.Println(strings.Repeat("=", 60))
}

// ShowStatus 显示状态
func (t *TrayIcon) ShowStatus() {
    if t.client == nil {
        return
    }
    
    stats := t.client.GetStats()
    uptime, _ := stats["uptime"].(float64)
    hours := int(uptime / 3600)
    minutes := int((uptime - float64(hours*3600)) / 60)
    
    // 获取队列统计
    queueStats := ""
    if t.client.uploadQueue != nil {
        qs := t.client.uploadQueue.GetStats()
        queueStats = fmt.Sprintf("\n队列: %d/%d", qs["queue_size"], qs["queue_maxsize"])
    }
    
    message := fmt.Sprintf(
        "员工ID: %s\n"+
            "客户端ID: %s\n"+
            "服务器: %s\n"+
            "运行时间: %d小时%d分钟\n"+
            "截图数量: %d\n"+
            "上传成功: %d\n"+
            "跳过相似: %d\n"+
            "上传失败: %d\n"+
            "截图间隔: %.0f秒\n"+
            "离线模式: %v\n"+
            "暂停状态: %v%s",
        t.client.employeeID,
        t.client.clientID,
        t.client.currentServer,
        hours,
        minutes,
        stats["screenshots_taken"],
        stats["screenshots_uploaded"],
        stats["skipped_similar"],
        stats["upload_failures"],
        t.client.interval.Seconds(),
        t.client.offlineMode == 1,
        t.client.paused == 1,
        queueStats,
    )
    
    t.showNotification("系统状态", message)
}

// ShowHealthStatus 显示健康状态
func (t *TrayIcon) ShowHealthStatus() {
    if t.client == nil || t.client.healthMonitor == nil {
        t.showNotification("健康状态", "健康监控未启用")
        return
    }

    summary := t.client.healthMonitor.GetSummary()
    message := fmt.Sprintf(
        "健康状态:\n"+
            "健康: %d\n"+
            "降级: %d\n"+
            "异常: %d\n"+
            "未知: %d\n"+
            "健康率: %.1f%%\n"+
            "恢复次数: %d",
        summary["healthy"],
        summary["degraded"],
        summary["unhealthy"],
        summary["unknown"],
        summary["health_rate"].(float64)*100,
        summary["total_recoveries"],
    )

    t.showNotification("健康状态", message)
}

// ShowWatchdogStatus 显示看门狗状态
func (t *TrayIcon) ShowWatchdogStatus() {
    if t.client == nil || t.client.watchdog == nil {
        t.showNotification("看门狗状态", "看门狗未启用")
        return
    }

    status := t.client.watchdog.GetStatus()
    runningText := "运行中"
    if !status["running"].(bool) {
        runningText = "已停止"
    }

    stats := status["stats"].(map[string]interface{})
    message := fmt.Sprintf(
        "看门狗状态:\n"+
            "%s\n"+
            "总重启: %d\n"+
            "失败重启: %d\n\n"+
            "监控进程:\n",
        runningText,
        stats["total_restarts"],
        stats["failed_restarts"],
    )

    processes := status["processes"].(map[string]interface{})
    for name, proc := range processes {
        procMap := proc.(map[string]interface{})
        icon := "✅"
        if !procMap["alive"].(bool) {
            icon = "❌"
        }
        message += fmt.Sprintf("%s %s: %s", icon, name, procMap["status"])
        if procMap["restart_count"].(int) > 0 {
            message += fmt.Sprintf(" (重启:%d)", procMap["restart_count"])
        }
        message += "\n"
    }

    t.showNotification("看门狗状态", message)
}

// ShowQueueStatus 显示队列状态
func (t *TrayIcon) ShowQueueStatus() {
    if t.client == nil || t.client.uploadQueue == nil {
        t.showNotification("上传队列", "上传队列未启用")
        return
    }

    stats := t.client.uploadQueue.GetStats()
    queuePercent := float64(stats["queue_size"].(int)) / float64(stats["queue_maxsize"].(int)) * 100
    cacheSizeMB := float64(stats["cache_size"].(int64)) / 1024 / 1024

    message := fmt.Sprintf(
        "上传队列状态:\n"+
            "队列大小: %d/%d (%.1f%%)\n"+
            "已处理: %d\n"+
            "失败: %d\n"+
            "重试: %d\n"+
            "缓存文件: %d\n"+
            "缓存大小: %.2f MB\n"+
            "背压计数: %d\n"+
            "运行状态: %v",
        stats["queue_size"],
        stats["queue_maxsize"],
        queuePercent,
        stats["processed"],
        stats["failed"],
        stats["retried"],
        stats["cache_count"],
        cacheSizeMB,
        stats["backpressure"],
        stats["is_running"],
    )

    t.showNotification("上传队列", message)
}

// PauseMonitor 暂停监控
func (t *TrayIcon) PauseMonitor() {
    if t.client == nil {
        return
    }
    atomic.StoreInt32(&t.client.paused, 1)
    t.showNotification("监控", "监控已暂停")
}

// ResumeMonitor 恢复监控
func (t *TrayIcon) ResumeMonitor() {
    if t.client == nil {
        return
    }
    atomic.StoreInt32(&t.client.paused, 0)
    t.showNotification("监控", "监控已恢复")
}

// TakeScreenshotNow 立即截图
func (t *TrayIcon) TakeScreenshotNow() {
    if t.client == nil {
        return
    }
    atomic.StoreInt32(&t.client.takeScreenshotNow, 1)
    t.showNotification("截图", "已触发立即截图")
}

// CleanupCache 清理缓存
func (t *TrayIcon) CleanupCache() {
    if t.client != nil && t.client.uploadQueue != nil {
        t.client.uploadQueue.cleanupCache()
        t.showNotification("缓存清理", "缓存清理完成")
    }
}

// NetworkDiagnostic 网络诊断
func (t *TrayIcon) NetworkDiagnostic() {
    if t.client == nil {
        return
    }
    
    modeText := "在线"
    if t.client.offlineMode == 1 {
        modeText = "离线"
    }
    heartbeatText := "已启用"
    if !t.client.enableHeartbeat {
        heartbeatText = "已禁用"
    }
    
    // 测试网络连接
    networkOK := t.client.checkBasicNetwork()
    serverOK := false
    if networkOK && t.client.apiClient != nil {
        _, err := t.client.apiClient.Get("/health")
        serverOK = err == nil
    }
    
    message := fmt.Sprintf(
        "网络诊断结果:\n"+
            "当前服务器: %s\n"+
            "Client ID: %s\n"+
            "员工ID: %s\n"+
            "模式: %s\n"+
            "心跳: %s\n"+
            "基础网络: %v\n"+
            "服务器连接: %v",
        t.client.currentServer,
        t.client.clientID,
        t.client.employeeID,
        modeText,
        heartbeatText,
        map[bool]string{true: "✅ 正常", false: "❌ 异常"}[networkOK],
        map[bool]string{true: "✅ 正常", false: "❌ 异常"}[serverOK],
    )
    
    t.showNotification("网络诊断", message)
}

// Reconfigure 重新配置
func (t *TrayIcon) Reconfigure() {
    if t.client == nil {
        return
    }
    
    fmt.Println("\n" + strings.Repeat("=", 50))
    fmt.Println("重新配置模式")
    fmt.Println("程序将在退出后需要重新配置")
    fmt.Println(strings.Repeat("=", 50))
    
    fmt.Print("确认重新配置? (y/n): ")
    input, _ := t.reader.ReadString('\n')
    input = strings.TrimSpace(strings.ToLower(input))
    
    if input == "y" || input == "yes" {
        t.client.forceReconfigure = true
        t.client.firstRun = true
        
        // 保存配置标记
        if t.client.configManager != nil {
            t.client.configManager.Set("force_reconfigure", true)
        }
        
        t.showNotification("重新配置", "请在重启后重新配置")
    }
}

// ExitApp 退出程序
func (t *TrayIcon) ExitApp() {
    fmt.Println("\n正在退出程序...")
    t.showNotification("退出", "正在退出程序...")
    if t.client != nil {
        t.client.Stop()
    }
    t.running = false
}

func (t *TrayIcon) showNotification(title, message string) {
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

    fmt.Printf("\n[%s] %s:\n%s\n", time.Now().Format("15:04:05"), title, message)
}

func minInt(a, b int) int {
    if a < b {
        return a
    }
    return b
}

// ShowHardwareInfo 显示硬件信息
func (t *TrayIcon) ShowHardwareInfo() {
    if t.client == nil {
        return
    }
    
    info := t.client.GetHardwareInfo()
    
    // 构建显示信息
    message := fmt.Sprintf(
        "========== 硬件信息 ==========\n"+
            "CPU: %s\n"+
            "CPU ID: %s\n"+
            "CPU核心: %d\n"+
            "\n主板: %s\n"+
            "主板序列号: %s\n"+
            "\n磁盘: %s\n"+
            "磁盘序列号: %s\n"+
            "\n系统UUID: %s\n"+
            "BIOS: %s\n"+
            "\n硬件指纹: %s\n"+
            "指纹可信度: %.1f%%\n"+
            "=============================",
        truncateStringForTray(info.CPUName, 50),
        info.CPUID,
        info.CPUCores,
        info.MotherboardModel,
        info.MotherboardSN,
        info.DiskModel,
        info.DiskSerial,
        info.UUID,
        info.BIOSVersion,
        info.Fingerprint[:16]+"...",
        info.Reliability*100,
    )
    
    t.showNotification("硬件信息", message)
}

// ToggleAutoStartMenu 切换开机自启（带交互）
func (t *TrayIcon) ToggleAutoStartMenu() {
    enabled := t.client.IsAutoStartEnabled()
    
    if enabled {
        fmt.Print("\n确认禁用开机自启? (y/n): ")
        response, _ := t.reader.ReadString('\n')
        if strings.TrimSpace(strings.ToLower(response)) != "y" {
            t.showNotification("开机自启", "操作已取消")
            return
        }
        
        if err := t.client.DisableAutoStart(); err != nil {
            t.showNotification("开机自启", "禁用失败: "+err.Error())
        } else {
            t.showNotification("开机自启", "已禁用开机自启")
        }
    } else {
        fmt.Print("\n确认启用开机自启? (y/n): ")
        response, _ := t.reader.ReadString('\n')
        if strings.TrimSpace(strings.ToLower(response)) != "y" {
            t.showNotification("开机自启", "操作已取消")
            return
        }
        
        if err := t.client.EnableAutoStart(); err != nil {
            t.showNotification("开机自启", "启用失败: "+err.Error())
        } else {
            t.showNotification("开机自启", "已启用开机自启")
            
            // 询问是否设置延迟启动
            fmt.Print("\n是否设置延迟启动? (y/n): ")
            delayResp, _ := t.reader.ReadString('\n')
            if strings.TrimSpace(strings.ToLower(delayResp)) == "y" {
                fmt.Print("延迟秒数 (默认10): ")
                delayStr, _ := t.reader.ReadString('\n')
                delay := 10
                if d, err := strconv.Atoi(strings.TrimSpace(delayStr)); err == nil && d > 0 {
                    delay = d
                }
                if err := t.client.SetAutoStartDelay(delay); err == nil {
                    t.showNotification("开机自启", fmt.Sprintf("已设置延迟启动 %d 秒", delay))
                }
            }
        }
    }
}

// truncateStringForTray 截断字符串用于托盘显示
func truncateStringForTray(s string, maxLen int) string {
    if len(s) <= maxLen {
        return s
    }
    return s[:maxLen-3] + "..."
}