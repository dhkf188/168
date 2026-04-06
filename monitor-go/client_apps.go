// client_apps.go - 软件使用监控器（实时采集版）
package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"sort"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/shirou/gopsutil/v3/process"
)

// AppMonitor 软件使用监控器
type AppMonitor struct {
	client          *MonitorClient
	ignoreProcesses []string
	activeApps      map[int]*ActiveApp
	reportInterval  time.Duration
	lastReportTime  time.Time
	running         int32
	mu              sync.RWMutex
	stopCh          chan struct{}
	wg              sync.WaitGroup

	// 配置
	maxCacheSize int
}

// ActiveApp 活跃应用
type ActiveApp struct {
	PID            int
	Name           string
	Exe            string
	StartTime      time.Time
	LastSeen       time.Time
	WindowTitle    string
	CPUPercent     float64
	MemoryMB       float64
}

// AppUsage 软件使用记录
type AppUsage struct {
	EmployeeID  string    `json:"employee_id"`
	ClientID    string    `json:"client_id"`
	AppName     string    `json:"app_name"`
	AppPath     string    `json:"app_path"`
	WindowTitle string    `json:"window_title"`
	StartTime   time.Time `json:"start_time"`
	Duration    int       `json:"duration"`
	CPUAvg      int       `json:"cpu_avg"`
	MemoryAvg   int       `json:"memory_avg"`
}

// NewAppMonitor 创建软件监控器
func NewAppMonitor(client *MonitorClient) *AppMonitor {
	return &AppMonitor{
		client: client,
		ignoreProcesses: []string{
			"System", "Registry", "smss.exe", "csrss.exe", "wininit.exe",
			"services.exe", "lsass.exe", "lsm.exe", "svchost.exe", "conhost.exe",
			"fontdrvhost.exe", "dwm.exe", "Idle", "dllhost.exe", "RuntimeBroker.exe",
			"backgroundTaskHost.exe", "sihost.exe", "taskhostw.exe", "ShellExperienceHost.exe",
			"SearchUI.exe", "SearchIndexer.exe", "WmiPrvSE.exe", "spoolsv.exe",
			"postgres.exe", "mysqld.exe", "sqlservr.exe", "mongod.exe", "redis-server.exe",
			"node.exe", "python.exe", "java.exe", "javaw.exe", "git.exe",
			"cmd.exe", "powershell.exe", "explorer.exe", "taskmgr.exe",
		},
		activeApps:     make(map[int]*ActiveApp),
		reportInterval: 120 * time.Second, // 2分钟上报一次
		stopCh:         make(chan struct{}),
		maxCacheSize:   10000,
	}
}

// StartMonitoring 启动监控
func (a *AppMonitor) StartMonitoring() {
	if !atomic.CompareAndSwapInt32(&a.running, 0, 1) {
		logInfo("软件使用监控器已在运行")
		return
	}

	logInfo("软件使用监控器启动 [上报间隔: %v, 实时采集模式]", a.reportInterval)
	a.wg.Add(1)
	go a.monitorLoop()
}

// StopMonitoring 停止监控
func (a *AppMonitor) StopMonitoring() {
	if !atomic.CompareAndSwapInt32(&a.running, 1, 0) {
		return
	}

	logInfo("软件使用监控器停止中...")
	close(a.stopCh)

	// 保存所有未保存的应用
	a.flushActiveApps()

	done := make(chan struct{})
	go func() {
		a.wg.Wait()
		close(done)
	}()

	select {
	case <-done:
		logInfo("软件使用监控器已停止")
	case <-time.After(5 * time.Second):
		logWarn("软件使用监控器停止超时")
	}
}

// flushActiveApps 刷新所有活跃应用（停止时调用）
func (a *AppMonitor) flushActiveApps() {
	a.mu.Lock()
	defer a.mu.Unlock()

	for _, info := range a.activeApps {
		duration := int(info.LastSeen.Sub(info.StartTime).Seconds())
		if duration >= 5 {
			logInfo("⏹️ 停止时保存应用: %s (时长: %d秒)", info.Name, duration)
			a.saveAppUsage(info, duration)
		}
	}
	a.activeApps = make(map[int]*ActiveApp)
}

func (a *AppMonitor) monitorLoop() {
	defer a.wg.Done()

	logInfo("软件使用监控循环已启动")
	ticker := time.NewTicker(5 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			if atomic.LoadInt32(&a.client.running) == 0 {
				return
			}
			a.trackAppUsage()
			a.collectAndReport()
		case <-a.stopCh:
			return
		}
	}
}

// trackAppUsage 跟踪应用使用（实时采集）
func (a *AppMonitor) trackAppUsage() {
	currentTime := time.Now()
	foreground := a.getForegroundApp()

	a.mu.Lock()
	defer a.mu.Unlock()

	// 检查前台窗口是否是应用（排除忽略列表）
	isAppForeground := foreground != nil && foreground.PID > 0

	if isAppForeground {
		pid := foreground.PID
		appName := foreground.Name

		if existing, ok := a.activeApps[pid]; ok {
			// 更新最后活跃时间
			existing.LastSeen = currentTime
			existing.CPUPercent = foreground.CPUPercent
			existing.MemoryMB = foreground.MemoryMB
			existing.WindowTitle = foreground.WindowTitle

			// 检查应用是否变化（同一个PID可能运行不同程序？这种情况很少）
			// 主要是更新窗口标题
		} else {
			// 新应用，创建记录
			a.activeApps[pid] = &ActiveApp{
				PID:         pid,
				Name:        appName,
				Exe:         foreground.Exe,
				StartTime:   currentTime,
				LastSeen:    currentTime,
				WindowTitle: foreground.WindowTitle,
				CPUPercent:  foreground.CPUPercent,
				MemoryMB:    foreground.MemoryMB,
			}
			logDebug("🆕 开始跟踪应用: %s - %s", appName, foreground.WindowTitle)
		}
	} else {
		// 当前不是应用窗口（桌面、任务管理器等），保存所有正在跟踪的应用
		if len(a.activeApps) > 0 {
			logDebug("📴 用户离开应用，保存所有使用记录")
			for _, info := range a.activeApps {
				duration := int(info.LastSeen.Sub(info.StartTime).Seconds())
				if duration >= 5 {
					logDebug("⏹️ 保存应用: %s - %s (时长: %d秒)", info.Name, info.WindowTitle, duration)
					a.saveAppUsage(info, duration)
				} else if duration < 5 {
					logDebug("丢弃短时间使用: %s (时长: %d秒)", info.Name, duration)
				}
			}
			// 清空所有活跃记录
			a.activeApps = make(map[int]*ActiveApp)
		}
		return
	}

	// 清理超时记录（超过30秒未更新，作为兜底）
	toRemove := make([]int, 0)
	for pid, info := range a.activeApps {
		if currentTime.Sub(info.LastSeen) > 30*time.Second {
			duration := int(info.LastSeen.Sub(info.StartTime).Seconds())
			if duration >= 5 {
				logDebug("⏹️ 超时保存应用: %s - %s (时长: %d秒)", info.Name, info.WindowTitle, duration)
				a.saveAppUsage(info, duration)
			}
			toRemove = append(toRemove, pid)
		}
	}

	for _, pid := range toRemove {
		delete(a.activeApps, pid)
	}
}

// getAllProcesses 获取所有进程（用于更新CPU/内存样本）
func (a *AppMonitor) getAllProcesses() []ProcessInfo {
	if runtime.GOOS != "windows" {
		return []ProcessInfo{}
	}

	ps, err := process.Processes()
	if err != nil {
		logDebug("获取进程列表失败: %v", err)
		return []ProcessInfo{}
	}

	processes := make([]ProcessInfo, 0, len(ps))
	for _, p := range ps {
		if p == nil {
			continue
		}

		name, err := p.Name()
		if err != nil || name == "" {
			continue
		}

		cpu, _ := p.CPUPercent()

		mem, _ := p.MemoryInfo()
		memMB := float64(0)
		if mem != nil {
			memMB = float64(mem.RSS) / 1024 / 1024
		}

		processes = append(processes, ProcessInfo{
			PID:        int(p.Pid),
			Name:       name,
			Exe:        "",
			CPUPercent: cpu,
			MemoryMB:   memMB,
		})
	}

	return processes
}

// getForegroundApp 获取当前前台应用
func (a *AppMonitor) getForegroundApp() *ForegroundApp {
	if runtime.GOOS != "windows" {
		return nil
	}

	winInfo := GetForegroundWindowInfo()
	if winInfo == nil {
		return nil
	}

	p, err := process.NewProcess(int32(winInfo.PID))
	if err != nil {
		return nil
	}

	name, err := p.Name()
	if err != nil || name == "" {
		return nil
	}

	// 检查是否在忽略列表中
	nameLower := strings.ToLower(name)
	for _, ign := range a.ignoreProcesses {
		if nameLower == strings.ToLower(ign) {
			return nil
		}
	}

	cpu, _ := p.CPUPercent()
	mem, _ := p.MemoryInfo()
	memMB := float64(0)
	if mem != nil {
		memMB = float64(mem.RSS) / 1024 / 1024
	}

	return &ForegroundApp{
		PID:         int(winInfo.PID),
		Name:        name,
		Exe:         "",
		WindowTitle: winInfo.Title,
		CPUPercent:  cpu,
		MemoryMB:    memMB,
	}
}

// saveAppUsage 保存应用使用记录
func (a *AppMonitor) saveAppUsage(info *ActiveApp, duration int) {
	if !a.client.IsReady() {
		logDebug("saveAppUsage: 客户端未就绪，跳过保存")
		return
	}

	// 只保存使用超过5秒的应用
	if duration < 5 {
		logDebug("使用时长不足5秒，丢弃: %s (%d秒)", info.Name, duration)
		return
	}

	// 计算CPU和内存平均值（简化：使用最后采样的值）
	cpuAvg := int(info.CPUPercent)
	memoryAvg := int(info.MemoryMB)

	usage := AppUsage{
		EmployeeID:  a.client.employeeID,
		ClientID:    a.client.clientID,
		AppName:     info.Name,
		AppPath:     info.Exe,
		WindowTitle: info.WindowTitle,
		StartTime:   info.StartTime,
		Duration:    duration,
		CPUAvg:      cpuAvg,
		MemoryAvg:   memoryAvg,
	}

	// 保存到缓存文件
	go a.saveUsageToFile(usage)
	logDebug("💾 保存应用记录: [%s] %s (%d秒)", info.Name, info.WindowTitle, duration)
}

// saveUsageToFile 保存使用记录到文件
func (a *AppMonitor) saveUsageToFile(usage AppUsage) {
	cacheDir := "cache"
	if err := os.MkdirAll(cacheDir, 0755); err != nil {
		logError("创建缓存目录失败: %v", err)
		return
	}

	cacheFile := filepath.Join(cacheDir, fmt.Sprintf("app_%d_%d.json", usage.StartTime.Unix(), time.Now().UnixNano()))

	jsonData, err := json.Marshal(usage)
	if err != nil {
		logError("序列化失败: %v", err)
		return
	}

	if err := os.WriteFile(cacheFile, jsonData, 0644); err != nil {
		logError("保存缓存文件失败: %v", err)
	}
}

// collectAndReport 收集并上报软件使用统计
func (a *AppMonitor) collectAndReport() {
	currentTime := time.Now()

	// 检查上报间隔
	if currentTime.Sub(a.lastReportTime) < a.reportInterval {
		return
	}

	if a.client.employeeID == "" {
		logDebug("软件使用上报: employeeID未就绪，跳过")
		return
	}

	logInfo("📊 开始收集软件使用数据...")

	// 收集所有已保存的使用记录
	allUsage := a.readAllSavedUsage()

	if len(allUsage) == 0 {
		logInfo("📊 没有软件使用记录需要上报")
		a.lastReportTime = currentTime
		return
	}

	// 按时间排序（最新的在前）
	sort.Slice(allUsage, func(i, j int) bool {
		return allUsage[i].StartTime.After(allUsage[j].StartTime)
	})

	logInfo("📊 收集到 %d 条软件使用记录", len(allUsage))

	// 打印所有记录
	for i, item := range allUsage {
		logInfo("  %d. [%s] %s (时长: %d秒, 时间: %s)",
			i+1, item.AppName, item.WindowTitle, item.Duration,
			item.StartTime.Format("15:04:05"))
	}

	// 上报所有记录
	if len(allUsage) > 0 {
		a.uploadUsageLocked(allUsage, currentTime)
	} else {
		a.lastReportTime = currentTime
	}
}

// readAllSavedUsage 读取所有已保存的软件使用记录
func (a *AppMonitor) readAllSavedUsage() []AppUsage {
	results := make([]AppUsage, 0)
	cacheDir := "cache"

	// 读取所有软件使用缓存文件
	files, err := filepath.Glob(filepath.Join(cacheDir, "app_*.json"))
	if err != nil {
		return results
	}

	for _, cacheFile := range files {
		data, err := os.ReadFile(cacheFile)
		if err != nil {
			continue
		}

		var item AppUsage
		if err := json.Unmarshal(data, &item); err == nil {
			// 补全ID信息
			item.EmployeeID = a.client.employeeID
			item.ClientID = a.client.clientID

			// 只保留最近2小时内的记录
			if time.Since(item.StartTime) < 2*time.Hour {
				results = append(results, item)
			}
		}
		// 读取后删除缓存文件
		os.Remove(cacheFile)
	}

	return results
}

// uploadUsageLocked 上传软件使用记录
func (a *AppMonitor) uploadUsageLocked(usage []AppUsage, currentTime time.Time) {
	if a.client.offlineMode != 0 {
		logInfo("离线模式，软件使用数据已缓存")
		a.saveBatchToCache(usage)
		return
	}

	if a.client.apiClient == nil {
		logError("API客户端未初始化")
		a.saveBatchToCache(usage)
		return
	}

	logInfo("📤 上报软件使用记录: %d条", len(usage))

	batchSize := 100
	successCount := 0

	for i := 0; i < len(usage); i += batchSize {
		end := i + batchSize
		if end > len(usage) {
			end = len(usage)
		}

		batch := usage[i:end]

		// 转换为map格式用于上报
		serializable := make([]map[string]interface{}, len(batch))
		for j, item := range batch {
			serializable[j] = map[string]interface{}{
				"employee_id":  item.EmployeeID,
				"client_id":    item.ClientID,
				"app_name":     item.AppName,
				"app_path":     item.AppPath,
				"window_title": item.WindowTitle,
				"start_time":   item.StartTime.Format(time.RFC3339),
				"duration":     item.Duration,
				"cpu_avg":      item.CPUAvg,
				"memory_avg":   item.MemoryAvg,
			}
		}

		// 添加重试逻辑
		var err error
		for retry := 0; retry < 3; retry++ {
			if retry > 0 {
				logDebug("重试上报批次 %d-%d (%d/3)", i, end, retry+1)
				time.Sleep(time.Duration(retry) * time.Second)
			}

			_, err = a.client.apiClient.Post("/api/apps/usage", serializable)
			if err == nil {
				break
			}
			logDebug("上报失败: %v", err)
		}

		if err != nil {
			logError("上报软件使用批次失败: %v", err)
			a.saveBatchToCache(batch)
		} else {
			logInfo("✅ 软件使用上报成功: %d条 (批次 %d-%d)", len(batch), i, end)
			successCount += len(batch)
		}
	}

	if successCount > 0 {
		a.lastReportTime = currentTime
	}
}

// saveBatchToCache 保存批次到缓存
func (a *AppMonitor) saveBatchToCache(batch []AppUsage) {
	cacheDir := "cache"
	os.MkdirAll(cacheDir, 0755)

	for _, item := range batch {
		cacheFile := filepath.Join(cacheDir, fmt.Sprintf("app_%d_%d.json",
			item.StartTime.Unix(), time.Now().UnixNano()))
		jsonData, _ := json.Marshal(item)
		os.WriteFile(cacheFile, jsonData, 0644)
	}
}

// ProcessInfo 进程信息
type ProcessInfo struct {
	PID        int
	Name       string
	Exe        string
	CPUPercent float64
	MemoryMB   float64
}

// ForegroundApp 前台应用信息
type ForegroundApp struct {
	PID         int
	Name        string
	Exe         string
	WindowTitle string
	CPUPercent  float64
	MemoryMB    float64
}