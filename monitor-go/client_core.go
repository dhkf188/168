// client_core.go - 监控客户端核心结构、配置管理、子系统初始化（完整重构版）
package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"runtime/debug"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

// ========== 配置管理器 ==========
type ConfigManager struct {
	configFile string
	config     map[string]interface{}
	mu         sync.RWMutex
	lastMtime  time.Time
}

func NewConfigManager(configFile string) *ConfigManager {
	cm := &ConfigManager{
		configFile: configFile,
		config:     make(map[string]interface{}),
	}
	cm.loadDefaultConfig()
	cm.Load()
	return cm
}

func (c *ConfigManager) loadDefaultConfig() {
	c.config = map[string]interface{}{
		"version":                Version,
		"server_urls":            []interface{}{"http://localhost:8000"},
		"interval":               60,
		"quality":                60,
		"format":                 "webp",
		"client_id":              "",
		"employee_id":            "",
		"employee_name":          "",
		"auto_start":             true,
		"hide_window":            true,
		"enable_heartbeat":       true,
		"enable_batch_upload":    true,
		"max_history":            10,
		"similarity_threshold":   0.95,
		"retry_times":            3,
		"retry_delay":            1,
		"encryption_enabled":     false,
		"enable_browser_monitor": true,
		"enable_app_monitor":     true,
		"enable_file_monitor":    true,
		"enable_remote_screen":   true,
		"remote_base_fps":        5,
		"remote_min_fps":         1,
		"remote_max_fps":         10,
		"remote_base_quality":    60,
		"remote_min_quality":     20,
		"remote_max_quality":     75,
		"remote_max_width":       1280,
		"remote_min_width":       640,
        "auto_start_silent":      true,
        "auto_start_delay":       0,
        "auto_start_method":      "registry",
        "enable_hardware_fingerprint": true,
        "hardware_fingerprint_version": 2,
        "hardware_cache_ttl":           300,
        
        // ========== 新增配置项 ==========
        
        // 网络优化配置
        "network_timeout":          30,           // 网络超时秒数
        "network_retry_times":      3,            // 重试次数
        "network_retry_delay":      1,            // 重试延迟秒数
        "network_max_retry_delay":  60,           // 最大重试延迟
        "network_adaptive_quality": true,         // 自适应质量
        "network_bandwidth_limit":  1024,         // 带宽限制 KB/s
        
        // 缓存配置
        "cache_max_size_mb":        500,          // 最大缓存MB
        "cache_cleanup_interval":   3600,         // 缓存清理间隔秒数
        "cache_max_age_hours":      24,           // 缓存最大存活小时
        
        // 内存配置
        "memory_limit_mb":          512,          // 内存限制MB
        "memory_gc_threshold":      0.8,          // GC触发阈值
        
        // 磁盘监控
        "disk_warning_mb":          200,          // 磁盘警告MB
        "disk_critical_mb":         100,          // 磁盘严重MB
        "disk_monitor_interval":    300,          // 磁盘监控间隔秒数
        
        // 日志配置
        "log_max_size_mb":          10,           // 日志最大MB
        "log_max_backups":          5,            // 日志备份数
        "log_max_age_days":         30,           // 日志保留天数
        "log_level":                "INFO",       // 日志级别
        
        // 稳定配置
        "panic_recovery":           true,         // 崩溃恢复
        "watchdog_timeout":         30,           // 看门狗超时秒数
        "max_restart_count":        10,           // 最大重启次数

        "connection_pool_size":       10,           // 连接池大小
        "connection_idle_timeout":    300,          // 空闲连接超时（秒）
        "connection_max_lifetime":    1800,         // 连接最大生命周期（秒）
        "latency_threshold":          500,          // 延迟阈值（毫秒）
	}
}

func (c *ConfigManager) Load() bool {
	logInfo("ConfigManager.Load 开始")

	c.mu.Lock()
	defer c.mu.Unlock()

	data, err := os.ReadFile(c.configFile)
	if err != nil {
		logInfo("配置文件不存在，创建默认配置")
		c.Save()
		return false
	}

	var loadedConfig map[string]interface{}
	if err := json.Unmarshal(data, &loadedConfig); err != nil {
		logError("解析配置文件失败: %v", err)
		return false
	}

	for k, v := range loadedConfig {
		c.config[k] = v
	}

	if info, err := os.Stat(c.configFile); err == nil {
		c.lastMtime = info.ModTime()
	}

	logInfo("ConfigManager.Load 完成")
	return true
}

func (c *ConfigManager) Save() bool {
	logInfo("ConfigManager.Save 开始")

	c.config["version"] = Version
	c.config["last_update"] = time.Now().Format(time.RFC3339)

	data, err := json.MarshalIndent(c.config, "", "  ")
	if err != nil {
		logError("序列化配置失败: %v", err)
		return false
	}

	if err := os.WriteFile(c.configFile, data, 0644); err != nil {
		logError("保存配置失败: %v", err)
		return false
	}

	if info, err := os.Stat(c.configFile); err == nil {
		c.lastMtime = info.ModTime()
	}

	logInfo("ConfigManager.Save 完成")
	return true
}

func (c *ConfigManager) Get(key string) interface{} {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.config[key]
}

func (c *ConfigManager) GetString(key string) string {
	if val := c.Get(key); val != nil {
		if s, ok := val.(string); ok {
			return s
		}
	}
	return ""
}

func (c *ConfigManager) GetInt(key string) int {
	if val := c.Get(key); val != nil {
		switch v := val.(type) {
		case int:
			return v
		case float64:
			return int(v)
		}
	}
	return 0
}

func (c *ConfigManager) GetBool(key string) bool {
	if val := c.Get(key); val != nil {
		if b, ok := val.(bool); ok {
			return b
		}
	}
	return false
}


// client_core.go - 在 ConfigManager 的方法区域添加

func (c *ConfigManager) GetInt64(key string) int64 {
    val := c.Get(key)
    if val == nil {
        return 0
    }
    
    switch v := val.(type) {
    case int:
        return int64(v)
    case int64:
        return v
    case float64:
        return int64(v)
    }
    return 0
}

func (c *ConfigManager) GetFloat64(key string) float64 {
	if val := c.Get(key); val != nil {
		switch v := val.(type) {
		case float64:
			return v
		case int:
			return float64(v)
		case int64:
			return float64(v)
		}
	}
	return 0
}

// client_core.go - 在 ConfigManager 的方法区域添加

func (c *ConfigManager) GetDuration(key string) time.Duration {
    val := c.Get(key)
    if val == nil {
        return 0
    }
    
    switch v := val.(type) {
    case int:
        return time.Duration(v) * time.Second
    case int64:
        return time.Duration(v) * time.Second
    case float64:
        return time.Duration(v) * time.Second
    case string:
        // 尝试解析字符串格式如 "30s", "5m"
        if d, err := time.ParseDuration(v); err == nil {
            return d
        }
    }
    return 0
}

func (c *ConfigManager) GetStringSlice(key string) []string {
	if val := c.Get(key); val != nil {
		if slice, ok := val.([]interface{}); ok {
			result := make([]string, len(slice))
			for i, v := range slice {
				if s, ok := v.(string); ok {
					result[i] = s
				}
			}
			return result
		}
	}
	return nil
}

func (c *ConfigManager) Set(key string, value interface{}) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.config[key] = value
	c.Save()
}

func (c *ConfigManager) Update(config map[string]interface{}) {
	logInfo("ConfigManager.Update 开始执行")

	c.mu.Lock()
	defer c.mu.Unlock()

	for k, v := range config {
		logInfo("更新配置: %s = %v", k, v)
		c.config[k] = v
	}

	c.Save()
	logInfo("ConfigManager.Update 执行完成")
}

func (c *ConfigManager) HasChanged() bool {
	info, err := os.Stat(c.configFile)
	if err != nil {
		return false
	}
	return info.ModTime().After(c.lastMtime)
}

func (c *ConfigManager) ReloadIfChanged() bool {
	if c.HasChanged() {
		return c.Load()
	}
	return false
}

// ========== 监控客户端主类 ==========
type MonitorClient struct {
	// 配置
	configManager *ConfigManager
	systemInfo    *SystemInfoCollector

	// 配置值
	clientID            string
	employeeID          string
	employeeName        string
	serverURLs          []string
	interval            time.Duration
	quality             int
	format              string
	autoStart           bool
	hideWindow          bool
	enableHeartbeat     bool
	enableBatchUpload   bool
	encryptionEnabled   bool
	maxHistory          int
	similarityThreshold float64
	retryTimes          int
	retryDelay          int

	// 状态（使用原子操作）
	running            int32
	paused             int32
	offlineMode        int32
	currentServerIndex int
	currentServer      string
	forceReconfigure   bool
	firstRun           bool
	takeScreenshotNow  int32

	// 子系统
	apiClient         *APIClient
	healthMonitor     *HealthMonitor
	uploadQueue       *UploadQueue
	screenshotManager *ScreenshotManager
	multiMonitor      *MultiMonitorScreenshot
	phashDetector     *PerceptualHash
	watchdog          *ProcessWatchdog
	powerManager      *PowerManager
	errorRecovery     *ErrorRecoverySystem
	security          *DataSecurityManager
	remoteScreen      *RemoteScreenManager
	appMonitor        *AppMonitor
	browserMonitor    *BrowserMonitor
	fileMonitor       *FileMonitor

	// 线程控制
	stopCh chan struct{}
	wg     sync.WaitGroup
	mu     sync.RWMutex

	// 统计
	stats   map[string]interface{}
	statsMu sync.RWMutex

    autoStartManager   *AutoStartManager
    hardwareIdentifier *HardwareIdentifier

    maxMemoryMB      int64
    diskWarningMB    int64
    diskCriticalMB   int64

		memoryLimiter    *MemoryLimiter
	networkAdaptor   *NetworkAdaptor
	connectionPool   *ConnectionPool
	crashRecovery    *CrashRecovery
	diskMonitor      *DiskMonitor
	retrier          *Retrier
	
	// 新增状态
	emergencyMode    bool
	emergencyMu      sync.RWMutex
}

// client_core.go - 修改 getEmployeeNameGUI 函数

func (m *MonitorClient) getEmployeeNameGUI(silentMode bool) string {
    logInfo("=== getEmployeeNameGUI 开始 ===")
    logInfo("silentMode=%v, firstRun=%v, forceReconfigure=%v", silentMode, m.firstRun, m.forceReconfigure)
    logInfo("当前 employeeName=%s", m.employeeName)
    
    // 如果已有员工姓名且不是强制重新配置，直接返回
    if m.employeeName != "" && !m.forceReconfigure {
        logInfo("使用已有员工姓名: %s", m.employeeName)
        return m.employeeName
    }

    // 从配置文件读取
    savedName := m.configManager.GetString("employee_name")
    if savedName != "" && !m.forceReconfigure {
        logInfo("从配置文件读取员工姓名: %s", savedName)
        return savedName
    }

    // 静默模式使用默认值
    if silentMode {
        defaultName := m.systemInfo.GetWindowsUser()
        if defaultName == "" {
            defaultName = "Employee"
        }
        logInfo("静默模式使用默认: %s", defaultName)
        return defaultName
    }

    logInfo("尝试弹出配置界面...")
    
    // ========== 使用统一的 GUI 入口 ==========
    var name string
    
    // 仅在 Windows 系统尝试图形界面
    if runtime.GOOS == "windows" {
        logInfo("Windows 系统，尝试图形界面...")
        
        // 添加 panic 恢复，防止 GUI 崩溃
        func() {
            defer func() {
                if r := recover(); r != nil {
                    logError("图形界面 panic: %v", r)
                }
            }()
            
            // ✅ 使用统一的 GUI 入口函数（内部会依次尝试 Fyne -> Walk -> 控制台）
            name = GetEmployeeNameGUI()
            logInfo("GUI 返回: '%s'", name)
        }()
    }
    
    // 如果 GUI 返回空或失败（非 Windows 系统或 GUI 全部失败），降级到控制台
    if name == "" {
        logInfo("降级到控制台版本")
        dialog := NewFirstRunDialog()
        name = dialog.Run()
        logInfo("控制台返回: '%s'", name)
    }
    
    // 如果用户取消或输入为空，使用系统用户名
    if name == "" {
        defaultName := m.systemInfo.GetWindowsUser()
        if defaultName == "" {
            defaultName = "Employee"
        }
        logInfo("用户取消，使用默认: %s", defaultName)
        return defaultName
    }
    
    return name
}

// client_core.go - 修复 RunWithGUI
func (m *MonitorClient) RunWithGUI(silentMode bool) {
    logInfo("=== RunWithGUI 开始 ===")
    logInfo("silentMode=%v, firstRun=%v", silentMode, m.firstRun)
    
    // 如果是首次运行且非静默模式，显示配置对话框
    if m.firstRun && !silentMode {
        logInfo("首次运行，尝试获取员工姓名...")
        name := m.getEmployeeNameGUI(silentMode)
        if name != "" {
            m.employeeName = name
            m.configManager.Set("employee_name", name)
            m.configManager.Save()
            logInfo("已保存员工姓名: %s", name)
        } else {
            logWarn("未获取到员工姓名，使用默认值")
            m.employeeName = m.systemInfo.GetWindowsUser()
            if m.employeeName == "" {
                m.employeeName = "Employee"
            }
        }
    } else {
        logInfo("非首次运行，跳过配置")
    }

    // 启动客户端
    logInfo("启动监控客户端...")
    go m.Start(silentMode)

    // 等待客户端初始化完成
    time.Sleep(2 * time.Second)

    // 启动系统托盘
    logInfo("启动系统托盘...")
    trayManager := NewTrayManager(m)
    trayManager.Run()
}

func NewMonitorClient(configFile string, forceReconfigure bool) *MonitorClient {
	client := &MonitorClient{
		configManager:    NewConfigManager(configFile),
		systemInfo:       NewSystemInfoCollector(),
		forceReconfigure: forceReconfigure,
		stopCh:           make(chan struct{}),
		stats:            make(map[string]interface{}),
        autoStartManager:   NewAutoStartManager("EmployeeMonitor"),
        hardwareIdentifier: NewHardwareIdentifier(),
	}



	client.loadConfig()
	client.firstRun = client.checkFirstRun()

	logInfo("客户端初始化完成，版本 %s", Version)

	return client
}

func (m *MonitorClient) CanReport() bool {
	return m.employeeID != "" && m.clientID != ""
}

func (m *MonitorClient) IsReady() bool {
	return m.employeeID != "" && m.clientID != ""
}

func (m *MonitorClient) loadConfig() {
	m.clientID = m.configManager.GetString("client_id")
	m.employeeID = m.configManager.GetString("employee_id")
	m.employeeName = m.configManager.GetString("employee_name")

	m.serverURLs = m.configManager.GetStringSlice("server_urls")
	if len(m.serverURLs) == 0 {
		m.serverURLs = []string{"http://localhost:8000"}
	}

	m.interval = time.Duration(m.configManager.GetInt("interval")) * time.Second
	m.quality = m.configManager.GetInt("quality")
	m.format = m.configManager.GetString("format")

	m.autoStart = m.configManager.GetBool("auto_start")
	m.hideWindow = m.configManager.GetBool("hide_window")
	m.enableHeartbeat = m.configManager.GetBool("enable_heartbeat")
	m.enableBatchUpload = m.configManager.GetBool("enable_batch_upload")
	m.encryptionEnabled = m.configManager.GetBool("encryption_enabled")

	m.maxHistory = m.configManager.GetInt("max_history")
	if val := m.configManager.Get("similarity_threshold"); val != nil {
		m.similarityThreshold = val.(float64)
	}
	m.retryTimes = m.configManager.GetInt("retry_times")
	m.retryDelay = m.configManager.GetInt("retry_delay")

	m.currentServerIndex = 0
	if len(m.serverURLs) > 0 {
		m.currentServer = m.serverURLs[0]
	}

	m.validateConfig()

	    autoStartEnabled := m.configManager.GetBool("auto_start")
    if autoStartEnabled && !m.IsAutoStartEnabled() {
        if err := m.EnableAutoStart(); err != nil {
            logWarn("启用开机自启失败: %v", err)
        } else {
            logInfo("根据配置已启用开机自启")
        }
    } else if !autoStartEnabled && m.IsAutoStartEnabled() {
        if err := m.DisableAutoStart(); err != nil {
            logWarn("禁用开机自启失败: %v", err)
        } else {
            logInfo("根据配置已禁用开机自启")
        }
    }
    
    // 处理延迟启动
    delay := m.configManager.GetInt("auto_start_delay")
    if delay > 0 {
        if err := m.SetAutoStartDelay(delay); err != nil {
            logWarn("设置延迟启动失败: %v", err)
        } else {
            logInfo("已设置延迟启动 %d 秒", delay)
        }
    }
}

func (m *MonitorClient) validateConfig() {
	validURLs := make([]string, 0)
	for _, url := range m.serverURLs {
		if strings.HasPrefix(url, "http://") || strings.HasPrefix(url, "https://") {
			validURLs = append(validURLs, url)
		} else {
			logWarn("无效的服务器URL: %s", url)
		}
	}

	if len(validURLs) == 0 {
		validURLs = []string{"https://trade-1.cc"}
		logWarn("使用默认服务器配置")
	}
	m.serverURLs = validURLs

	if m.interval < 10*time.Second || m.interval > 3600*time.Second {
		m.interval = 60 * time.Second
		logWarn("截图间隔调整为60秒")
	}

	if m.quality < 10 || m.quality > 100 {
		m.quality = 80
		logWarn("图片质量调整为80")
	}

	if m.format != "webp" && m.format != "jpg" && m.format != "jpeg" {
		m.format = "webp"
		logWarn("图片格式调整为webp")
	}
}

func (m *MonitorClient) checkFirstRun() bool {
    logInfo("checkFirstRun 开始: forceReconfigure=%v", m.forceReconfigure)
    
    if m.forceReconfigure {
        logInfo("强制重新配置模式")
        return true
    }

    if _, err := os.Stat(m.configManager.configFile); os.IsNotExist(err) {
        logInfo("首次运行：没有配置文件")
        return true
    }

    if m.clientID == "" || m.employeeID == "" || m.employeeName == "" {
        logInfo("首次运行：缺少必要信息 (clientID=%s, employeeID=%s, employeeName=%s)", 
            m.clientID, m.employeeID, m.employeeName)
        return true
    }

    logInfo("非首次运行")
    return false
}

// client_core.go - 完整整合版 initSubsystems

func (m *MonitorClient) initSubsystems() {
	logInfo("初始化子系统...")
	logInfo("═══════════════════════════════════════════════════════════")

	// ==================== 1. 加载新增配置项 ====================
	m.loadNewConfigValues()

	// ==================== 2. 核心组件初始化 ====================
	// API客户端 - 带网络自适应
	m.apiClient = NewAPIClient(m.currentServer, 30*time.Second, m.retryTimes, m.retryDelay)
	if m.networkAdaptor != nil {
		// 注入网络自适应到API客户端
		 if m.apiClient != nil {
			m.apiClient.SetNetworkAdaptor(m.networkAdaptor)
		 }
		
	}
	
	// 健康监控
	m.healthMonitor = NewHealthMonitor(60*time.Second, 300*time.Second)
	m.registerHealthComponents()
	
	// 错误恢复系统
	m.errorRecovery = NewErrorRecoverySystem(m)
	m.errorRecovery.Start()
	
	// 数据安全
	m.security = NewDataSecurityManager(m, m.encryptionEnabled)
	
	// 截图相关
	m.multiMonitor = NewMultiMonitorScreenshot()
	m.phashDetector = NewPerceptualHash(m.similarityThreshold)
	m.screenshotManager = NewScreenshotManager(m.quality, m.format, m.maxHistory, m.similarityThreshold)
	
	// 上传队列 - 使用配置的缓存大小
	cacheMaxSizeMB := m.configManager.GetInt64("cache_max_size_mb")
	if cacheMaxSizeMB <= 0 {
		cacheMaxSizeMB = 500
	}
	m.uploadQueue = NewUploadQueue(m, 100, 3, "cache", cacheMaxSizeMB*1024*1024)
	
	// 进程看门狗
	m.watchdog = NewProcessWatchdog(30*time.Second, 5)
	
	// 功耗管理
	m.powerManager = NewPowerManager(m, m.interval)

	// ==================== 3. 新增组件初始化 ====================
	
	// 内存限制器
	maxMemoryMB := m.configManager.GetInt64("memory_limit_mb")
	if maxMemoryMB <= 0 {
		maxMemoryMB = 512
	}
	m.memoryLimiter = NewMemoryLimiter(maxMemoryMB)
	logInfo("✅ 内存限制器已初始化 (上限: %d MB)", maxMemoryMB)
	
	// 网络自适应管理器
	m.networkAdaptor = NewNetworkAdaptor()
	// 从配置加载网络自适应参数
	if m.configManager.GetBool("network_adaptive_quality") {
		m.networkAdaptor.minQuality = int32(m.configManager.GetInt("remote_min_quality"))
		m.networkAdaptor.maxQuality = int32(m.configManager.GetInt("remote_max_quality"))
		m.networkAdaptor.rttThreshold = int64(m.configManager.GetInt("latency_threshold"))
		if m.networkAdaptor.rttThreshold <= 0 {
			m.networkAdaptor.rttThreshold = 500
		}
		logInfo("✅ 网络自适应已启用 (质量范围: %d-%d, RTT阈值: %dms)", 
			m.networkAdaptor.minQuality, m.networkAdaptor.maxQuality, m.networkAdaptor.rttThreshold)
	} else {
		logInfo("⚠️ 网络自适应已禁用")
	}
	
	// 连接池
	connectionPoolSize := m.configManager.GetInt("connection_pool_size")
	if connectionPoolSize <= 0 {
		connectionPoolSize = 10
	}
	idleTimeout := m.configManager.GetDuration("connection_idle_timeout")
	if idleTimeout <= 0 {
		idleTimeout = 5 * time.Minute
	}
	maxLifetime := m.configManager.GetDuration("connection_max_lifetime")
	if maxLifetime <= 0 {
		maxLifetime = 30 * time.Minute
	}
	m.connectionPool = NewConnectionPool(connectionPoolSize, idleTimeout, maxLifetime)
	logInfo("✅ 连接池已初始化 (大小: %d, 空闲超时: %v, 最大生命周期: %v)", 
		connectionPoolSize, idleTimeout, maxLifetime)
	
	// 崩溃恢复系统
	enablePanicRecovery := m.configManager.GetBool("panic_recovery")
	m.crashRecovery = NewCrashRecovery(m.globalPanicHandler)
	if enablePanicRecovery {
		m.registerComponentsForRecovery()
		logInfo("✅ 崩溃恢复系统已启用")
	} else {
		logInfo("⚠️ 崩溃恢复系统已禁用")
	}
	
	// 磁盘监控器
	diskWarningMB := m.configManager.GetInt64("disk_warning_mb")
	diskCriticalMB := m.configManager.GetInt64("disk_critical_mb")
	if diskWarningMB <= 0 {
		diskWarningMB = 200
	}
	if diskCriticalMB <= 0 {
		diskCriticalMB = 100
	}
	m.diskMonitor = NewDiskMonitor("cache", diskWarningMB, diskCriticalMB)
	
	// 设置磁盘监控回调
	m.diskMonitor.onWarning = func(freeMB int64) {
		logWarn("📀 磁盘空间不足: 剩余 %d MB, 即将进行清理", freeMB)
		if m.uploadQueue != nil {
			m.uploadQueue.cleanupCache()
		}
		// 触发健康状态更新
		if m.healthMonitor != nil {
			m.healthMonitor.UpdateStatus("disk", HealthDegraded, 
				fmt.Sprintf("磁盘空间不足: %d MB", freeMB), nil)
		}
	}
	m.diskMonitor.onCritical = func(freeMB int64) {
		logError("📀 磁盘空间严重不足: 剩余 %d MB, 进入紧急模式", freeMB)
		m.setEmergencyMode(true)
		// 触发健康状态更新
		if m.healthMonitor != nil {
			m.healthMonitor.UpdateStatus("disk", HealthUnhealthy, 
				fmt.Sprintf("磁盘空间严重不足: %d MB", freeMB), nil)
		}
		// 紧急清理所有监控器的缓存
		m.emergencyCleanupAll()
	}
	
	// 启动磁盘监控
	diskMonitorInterval := m.configManager.GetDuration("disk_monitor_interval")
	if diskMonitorInterval <= 0 {
		diskMonitorInterval = 5 * time.Minute
	}
	m.diskMonitor.StartMonitoring(diskMonitorInterval)
	logInfo("✅ 磁盘监控器已初始化 (警告: %d MB, 严重: %d MB, 间隔: %v)", 
		diskWarningMB, diskCriticalMB, diskMonitorInterval)

	// ==================== 4. 可选组件初始化 ====================
	
	if m.configManager.GetBool("enable_remote_screen") {
		m.remoteScreen = NewRemoteScreenManager(m)
		logInfo("✅ 远程屏幕管理器已创建")
	}

	if m.configManager.GetBool("enable_app_monitor") {
		m.appMonitor = NewAppMonitor(m)
		logInfo("✅ 软件使用监控器已创建")
	}

	if m.configManager.GetBool("enable_browser_monitor") {
		m.browserMonitor = NewBrowserMonitor(m)
		logInfo("✅ 浏览器监控器已创建")
	}

	if m.configManager.GetBool("enable_file_monitor") {
		m.fileMonitor = NewFileMonitor(m)
		logInfo("✅ 文件监控器已创建")
	}

	// ==================== 5. 智能重试器初始化 ====================
	retryConfig := RetryConfig{
		MaxAttempts:     m.retryTimes,
		InitialDelay:    time.Duration(m.retryDelay) * time.Second,
		MaxDelay:        time.Duration(m.configManager.GetInt("network_max_retry_delay")) * time.Second,
		Strategy:        RetryExponentialWithJitter,
		JitterFactor:    0.2,
		ShouldRetryFunc: m.shouldRetryError,
	}
	if retryConfig.MaxDelay <= 0 {
		retryConfig.MaxDelay = 60 * time.Second
	}
	if retryConfig.InitialDelay <= 0 {
		retryConfig.InitialDelay = 1 * time.Second
	}
	m.retrier = NewRetrier(retryConfig)
	logInfo("✅ 智能重试器已初始化 (最大尝试: %d, 初始延迟: %v, 最大延迟: %v)", 
		retryConfig.MaxAttempts, retryConfig.InitialDelay, retryConfig.MaxDelay)

	// ==================== 6. 注册到健康监控 ====================
	m.registerNewComponentsToHealthMonitor()

	// ==================== 7. 初始化健康状态 ====================
	m.initHealthStatus()
	
	logInfo("═══════════════════════════════════════════════════════════")
	logInfo("✅ 所有子系统初始化完成 (共 %d 个组件)", m.countComponents())
}

// loadNewConfigValues 加载新增配置项
func (m *MonitorClient) loadNewConfigValues() {
	// 确保 stats map 存在
	if m.stats == nil {
		m.stats = make(map[string]interface{})
	}
	
	// 紧急模式标志初始化
	m.emergencyMode = false
	
	logInfo("加载新增配置项:")
	logInfo("  - 网络超时: %d 秒", m.configManager.GetInt("network_timeout"))
	logInfo("  - 网络重试次数: %d", m.configManager.GetInt("network_retry_times"))
	logInfo("  - 缓存最大容量: %d MB", m.configManager.GetInt("cache_max_size_mb"))
	logInfo("  - 缓存清理间隔: %d 秒", m.configManager.GetInt("cache_cleanup_interval"))
	logInfo("  - 内存限制: %d MB", m.configManager.GetInt("memory_limit_mb"))
	logInfo("  - 磁盘警告阈值: %d MB", m.configManager.GetInt("disk_warning_mb"))
	logInfo("  - 磁盘严重阈值: %d MB", m.configManager.GetInt("disk_critical_mb"))
	logInfo("  - 日志级别: %s", m.configManager.GetString("log_level"))
	logInfo("  - 崩溃恢复: %v", m.configManager.GetBool("panic_recovery"))
	logInfo("  - 看门狗超时: %d 秒", m.configManager.GetInt("watchdog_timeout"))
	logInfo("  - 最大重启次数: %d", m.configManager.GetInt("max_restart_count"))
}

// registerNewComponentsToHealthMonitor 注册新组件到健康监控
func (m *MonitorClient) registerNewComponentsToHealthMonitor() {
	if m.healthMonitor == nil {
		return
	}
	
	// 注册内存组件
	m.healthMonitor.RegisterComponent("memory", func() {
		if m.memoryLimiter != nil {
			m.memoryLimiter.TriggerGC()
		}
	})
	
	// 注册磁盘组件
	m.healthMonitor.RegisterComponent("disk", func() {
		if m.diskMonitor != nil {
			freeMB, err := m.diskMonitor.GetFreeSpace()
			if err == nil && freeMB < m.diskCriticalMB { 
				m.diskMonitor.emergencyCleanup()
			}
		}
	})
	
	// 注册网络自适应组件
	m.healthMonitor.RegisterComponent("network_adaptor", nil)
	
	// 注册连接池组件
	m.healthMonitor.RegisterComponent("connection_pool", nil)
	
	logInfo("✅ 新增组件已注册到健康监控")
}

// registerComponentsForRecovery 注册组件到崩溃恢复系统
func (m *MonitorClient) registerComponentsForRecovery() {
	if m.crashRecovery == nil {
		return
	}
	
	// 注册主要组件
	m.crashRecovery.RegisterComponent("workLoop", func() { m.recoverWorkLoop() }, 10*time.Second)
	m.crashRecovery.RegisterComponent("networkMonitor", m.recoverNetworkMonitor, 10*time.Second)
	m.crashRecovery.RegisterComponent("heartbeatSender", m.recoverHeartbeatSender, 10*time.Second)
	m.crashRecovery.RegisterComponent("batchUploader", m.recoverBatchUploader, 10*time.Second)
	m.crashRecovery.RegisterComponent("screenshot", m.recoverScreenshot, 10*time.Second)
	m.crashRecovery.RegisterComponent("upload", m.recoverUpload, 10*time.Second)
	m.crashRecovery.RegisterComponent("healthMonitor", m.recoverHealthMonitor, 10*time.Second)
	
	logInfo("✅ 已注册 %d 个组件到崩溃恢复系统", 7)
}

// 崩溃恢复回调函数
func (m *MonitorClient) recoverWorkLoop() {
	logInfo("恢复工作循环...")
	go func() {
		if m.crashRecovery != nil {
			m.crashRecovery.Wrap("workLoop", func() { m.workLoop() })
		} else {
			m.workLoop()
		}
	}()
}

func (m *MonitorClient) recoverNetworkMonitor() {
	logInfo("恢复网络监控...")
	go func() {
		if m.crashRecovery != nil {
			m.crashRecovery.Wrap("networkMonitor", func() { m.networkMonitor() })
		} else {
			m.networkMonitor()
		}
	}()
}

func (m *MonitorClient) recoverHeartbeatSender() {
	logInfo("恢复心跳发送器...")
	go func() {
		if m.crashRecovery != nil {
			m.crashRecovery.Wrap("heartbeatSender", func() { m.heartbeatSender() })
		} else if m.enableHeartbeat {
			m.heartbeatSender()
		}
	}()
}

func (m *MonitorClient) recoverBatchUploader() {
	logInfo("恢复批量上传器...")
	go func() {
		if m.crashRecovery != nil {
			m.crashRecovery.Wrap("batchUploader", func() { m.batchUploader() })
		} else if m.enableBatchUpload {
			m.batchUploader()
		}
	}()
}

func (m *MonitorClient) recoverHealthMonitor() {
	logInfo("恢复健康监控...")
	if m.healthMonitor != nil {
		m.healthMonitor.StartMonitoring()
	}
}

// globalPanicHandler 全局 panic 处理器
func (m *MonitorClient) globalPanicHandler(r interface{}) {
	logError("🔥 全局 panic 恢复: %v", r)
	
	// 记录堆栈
	if logger != nil {
		stack := debug.Stack()
		logError("堆栈信息:\n%s", string(stack))
	}
	
	// 更新健康状态
	if m.healthMonitor != nil {
		m.healthMonitor.UpdateStatus("global", HealthDegraded, 
			fmt.Sprintf("global panic: %v", r), nil)
	}
	
	// 触发错误恢复
	if m.errorRecovery != nil {
		m.errorRecovery.ReportError(fmt.Errorf("global panic: %v", r), "global", nil)
	}
}

// shouldRetryError 判断错误是否应该重试
func (m *MonitorClient) shouldRetryError(err error) bool {
	if err == nil {
		return false
	}
	
	errStr := strings.ToLower(err.Error())
	
	// 网络错误 - 应该重试
	if strings.Contains(errStr, "timeout") ||
		strings.Contains(errStr, "connection refused") ||
		strings.Contains(errStr, "connection reset") ||
		strings.Contains(errStr, "no such host") ||
		strings.Contains(errStr, "network") {
		return true
	}
	
	// 服务器错误 - 应该重试
	if strings.Contains(errStr, "500") ||
		strings.Contains(errStr, "502") ||
		strings.Contains(errStr, "503") ||
		strings.Contains(errStr, "504") {
		return true
	}
	
	// 临时错误 - 应该重试
	if strings.Contains(errStr, "temporary") ||
		strings.Contains(errStr, "unavailable") ||
		strings.Contains(errStr, "busy") {
		return true
	}
	
	return false
}

// setEmergencyMode 设置紧急模式
func (m *MonitorClient) setEmergencyMode(enabled bool) {
	m.emergencyMu.Lock()
	defer m.emergencyMu.Unlock()
	
	if enabled && !m.emergencyMode {
		m.emergencyMode = true
		logWarn("进入紧急模式 - 将降低监控频率并优先清理资源")
		
		// 降低截图频率
		if m.interval > 120*time.Second {
			oldInterval := m.interval
			m.interval = 120 * time.Second
			logInfo("紧急模式: 截图间隔从 %v 调整为 %v", oldInterval, m.interval)
		}
		
		// 降低远程屏幕质量
		if m.remoteScreen != nil {
			atomic.StoreInt32(&m.remoteScreen.currentQuality, 20)
			atomic.StoreInt32(&m.remoteScreen.currentFPS, 1)
			logInfo("紧急模式: 远程屏幕质量降至最低")
		}
		
	} else if !enabled && m.emergencyMode {
		m.emergencyMode = false
		logInfo("退出紧急模式 - 恢复正常监控频率")
		
		// 恢复截图频率
		m.interval = time.Duration(m.configManager.GetInt("interval")) * time.Second
		
		// 恢复远程屏幕质量
		if m.remoteScreen != nil {
			atomic.StoreInt32(&m.remoteScreen.currentQuality, int32(m.configManager.GetInt("remote_base_quality")))
			atomic.StoreInt32(&m.remoteScreen.currentFPS, int32(m.configManager.GetInt("remote_base_fps")))
		}
	}
}

// emergencyCleanupAll 紧急清理所有资源
func (m *MonitorClient) emergencyCleanupAll() {
	logWarn("执行紧急资源清理...")
	
	// 清理上传队列缓存
	if m.uploadQueue != nil {
		m.uploadQueue.cleanupCache()
	}
	
	// 清理截图历史
	if m.screenshotManager != nil {
		m.screenshotManager.CleanupOldScreenshots(1) // 清理超过1小时的截图
	}
	
	// 清理旧日志
	exePath, _ := os.Executable()
	exeDir := filepath.Dir(exePath)
	logsDir := filepath.Join(exeDir, "logs")
	CleanOldLogs(logsDir, 1) // 清理超过1天的日志
	
	// 触发GC
	if m.memoryLimiter != nil {
		m.memoryLimiter.TriggerGC()
	} else {
		runtime.GC()
	}
	
	logInfo("紧急资源清理完成")
}

// countComponents 统计组件数量
func (m *MonitorClient) countComponents() int {
	count := 0
	if m.apiClient != nil {
		count++
	}
	if m.healthMonitor != nil {
		count++
	}
	if m.errorRecovery != nil {
		count++
	}
	if m.security != nil {
		count++
	}
	if m.multiMonitor != nil {
		count++
	}
	if m.phashDetector != nil {
		count++
	}
	if m.screenshotManager != nil {
		count++
	}
	if m.uploadQueue != nil {
		count++
	}
	if m.watchdog != nil {
		count++
	}
	if m.powerManager != nil {
		count++
	}
	if m.memoryLimiter != nil {
		count++
	}
	if m.networkAdaptor != nil {
		count++
	}
	if m.connectionPool != nil {
		count++
	}
	if m.crashRecovery != nil {
		count++
	}
	if m.diskMonitor != nil {
		count++
	}
	if m.retrier != nil {
		count++
	}
	if m.remoteScreen != nil {
		count++
	}
	if m.appMonitor != nil {
		count++
	}
	if m.browserMonitor != nil {
		count++
	}
	if m.fileMonitor != nil {
		count++
	}
	return count
}

func (m *MonitorClient) registerHealthComponents() {
	m.healthMonitor.RegisterComponent("screenshot", m.recoverScreenshot)
	m.healthMonitor.RegisterComponent("upload", m.recoverUpload)
	m.healthMonitor.RegisterComponent("network", m.recoverNetwork)
	m.healthMonitor.RegisterComponent("heartbeat", m.recoverHeartbeat)
	m.healthMonitor.RegisterComponent("config", m.recoverConfig)
	m.healthMonitor.RegisterComponent("watchdog", m.recoverWatchdog)
	m.healthMonitor.RegisterComponent("power", nil)
}

func (m *MonitorClient) initHealthStatus() {
	now := float64(time.Now().Unix())
	components := []string{"screenshot", "upload", "network", "heartbeat", "config", "watchdog", "power"}

	for _, name := range components {
		if comp := m.healthMonitor.GetComponentStatus(name); comp != nil {
			comp.LastCheckTime = now
			m.healthMonitor.UpdateStatus(name, HealthHealthy, "组件初始化完成", nil)
		}
	}
}

// ========== 恢复回调函数 ==========
func (m *MonitorClient) recoverScreenshot() {
	logInfo("恢复截图组件")
	if m.watchdog != nil {
		m.watchdog.Heartbeat("screenshot")
	}
}

func (m *MonitorClient) recoverUpload() {
	logInfo("恢复上传组件")
	if m.watchdog != nil {
		m.watchdog.Heartbeat("upload")
	}
}

func (m *MonitorClient) recoverNetwork() {
	logInfo("恢复网络组件")
	if m.watchdog != nil {
		m.watchdog.Heartbeat("network")
	}
}

func (m *MonitorClient) recoverHeartbeat() {
	logInfo("恢复心跳组件")
	if m.watchdog != nil {
		m.watchdog.Heartbeat("heartbeat")
	}
}

func (m *MonitorClient) recoverConfig() {
	logInfo("恢复配置组件")
	m.configManager.ReloadIfChanged()
	if m.watchdog != nil {
		m.watchdog.Heartbeat("config")
	}
}

func (m *MonitorClient) recoverWatchdog() {
	logInfo("恢复看门狗组件")
	if m.watchdog != nil {
		m.watchdog.Start()
		m.watchdog.Heartbeat("watchdog")
	}
}

// ========== 注册服务器 ==========
func (m *MonitorClient) RegisterWithServer(silentMode bool) bool {
	logInfo("=" + strings.Repeat("=", 58))
	logInfo("向服务器注册")
	logInfo("=" + strings.Repeat("=", 58))

	for i, server := range m.serverURLs {
		logInfo("    %d. %s", i+1, server)
	}
	logInfo("当前服务器: %s", m.currentServer)

	if m.apiClient == nil || m.apiClient.BaseURL != m.currentServer {
		m.apiClient = NewAPIClient(m.currentServer, 30*time.Second, m.retryTimes, m.retryDelay)
		logInfo("API客户端已初始化: %s", m.currentServer)
	}

	employeeName := m.getEmployeeName(silentMode)

	logInfo("收集硬件信息...")
	systemInfo := m.systemInfo.GetSystemInfo()
	hardwareInfo := m.systemInfo.GetHardwareFingerprint()

	registerData := map[string]interface{}{
		"client_id":            m.clientID,
		"computer_name":        systemInfo["computer_name"],
		"windows_user":         systemInfo["windows_user"],
		"mac_address":          hardwareInfo["mac_address"],
		"ip_address":           systemInfo["ip_address"],
		"os_version":           systemInfo["os_version"],
		"client_version":       Version,
		"interval":             int(m.interval.Seconds()),
		"quality":              m.quality,
		"format":               m.format,
		"employee_name":        employeeName,
		"capabilities":         []string{"webp", "heartbeat", "batch", "encryption"},
		"hardware_fingerprint": hardwareInfo["hardware_fingerprint"],
	}

	if m.security != nil {
		registerData = m.security.SignData(registerData)
	}

	logInfo("向服务器发送注册请求: %s/api/client/register", m.currentServer)

	resp, err := m.apiClient.Post("/api/client/register", registerData)

	if err != nil {
		logError("注册失败: %v", err)
		atomic.StoreInt32(&m.offlineMode, 1)
		logInfo("进入离线模式")
		return false
	}

	logInfo("解析响应...")
	if clientID, ok := resp["client_id"].(string); ok {
		m.clientID = clientID
	}
	if employeeID, ok := resp["employee_id"].(string); ok {
		m.employeeID = employeeID
	}

	if m.remoteScreen != nil {
		m.remoteScreen.UpdateIDs(m.clientID, m.employeeID)
		logInfo("远程屏幕身份已更新: clientID=%s", m.clientID)
	}

	logInfo("注册成功! 客户端ID: %s, 员工ID: %s", m.clientID, m.employeeID)

	if config, ok := resp["config"].(map[string]interface{}); ok {
		logInfo("服务器返回配置: %+v", config)
		m.updateConfigFromServer(config)
	}

	m.configManager.Update(map[string]interface{}{
		"client_id":     m.clientID,
		"employee_id":   m.employeeID,
		"employee_name": employeeName,
		"interval":      int(m.interval.Seconds()),
		"quality":       m.quality,
		"format":        m.format,
		"version":       Version,
	})

	m.forceReconfigure = false
	m.firstRun = false
	atomic.StoreInt32(&m.offlineMode, 0)

	if m.watchdog != nil {
		m.watchdog.Heartbeat("main")
	}

	logInfo("注册函数即将返回 true")
	return true
}

func (m *MonitorClient) getEmployeeName(silentMode bool) string {
	if m.employeeName != "" && !m.forceReconfigure {
		logInfo("使用已有员工姓名: %s", m.employeeName)
		return m.employeeName
	}

	savedName := m.configManager.GetString("employee_name")
	if savedName != "" && !m.forceReconfigure {
		logInfo("从配置文件读取员工姓名: %s", savedName)
		return savedName
	}

	if silentMode {
		defaultName := m.systemInfo.GetWindowsUser()
		if defaultName == "" {
			defaultName = "Employee"
		}
		logInfo("静默模式使用默认: %s", defaultName)
		return defaultName
	}

	fmt.Print("请输入您的姓名: ")
	var name string
	fmt.Scanln(&name)
	name = strings.TrimSpace(name)
	if name != "" {
		return name
	}

	defaultName := m.systemInfo.GetWindowsUser()
	if defaultName == "" {
		defaultName = "Employee"
	}
	return defaultName
}

func (m *MonitorClient) updateConfigFromServer(config map[string]interface{}) {
	logInfo("updateConfigFromServer 开始执行")

	changed := false

	if interval, ok := config["interval"].(float64); ok && interval > 0 {
		newInterval := time.Duration(int(interval)) * time.Second
		if newInterval != m.interval {
			logInfo("interval 变更: %v -> %v", m.interval, newInterval)
			m.interval = newInterval
			changed = true
		}
	}

	if quality, ok := config["quality"].(float64); ok {
		newQuality := int(quality)
		if newQuality != m.quality {
			logInfo("quality 变更: %d -> %d", m.quality, newQuality)
			m.quality = newQuality
			if m.screenshotManager != nil {
				m.screenshotManager.quality = m.quality
			}
			changed = true
		}
	}

	if format, ok := config["format"].(string); ok && format != m.format {
		logInfo("format 变更: %s -> %s", m.format, format)
		m.format = format
		if m.screenshotManager != nil {
			m.screenshotManager.format = m.format
		}
		changed = true
	}

	if enableHeartbeat, ok := config["enable_heartbeat"].(bool); ok && enableHeartbeat != m.enableHeartbeat {
		logInfo("enableHeartbeat 变更: %v -> %v", m.enableHeartbeat, enableHeartbeat)
		m.enableHeartbeat = enableHeartbeat
		changed = true
	}

	if similarityThreshold, ok := config["similarity_threshold"].(float64); ok && similarityThreshold != m.similarityThreshold {
		logInfo("similarityThreshold 变更: %v -> %v", m.similarityThreshold, similarityThreshold)
		m.similarityThreshold = similarityThreshold
		if m.phashDetector != nil {
			m.phashDetector.threshold = similarityThreshold
		}
		changed = true
	}

	if changed {
		m.configManager.Update(map[string]interface{}{
			"interval":             int(m.interval.Seconds()),
			"quality":              m.quality,
			"format":               m.format,
			"enable_heartbeat":     m.enableHeartbeat,
			"similarity_threshold": m.similarityThreshold,
		})

		if m.watchdog != nil {
			m.watchdog.Heartbeat("config")
		}
	}
}

// ========== 统计获取 ==========
func (m *MonitorClient) GetStats() map[string]interface{} {
	m.statsMu.RLock()
	defer m.statsMu.RUnlock()

	stats := make(map[string]interface{})
	for k, v := range m.stats {
		stats[k] = v
	}

	if startTime, ok := stats["start_time"].(time.Time); ok {
		stats["uptime"] = time.Since(startTime).Seconds()
	}

	if m.uploadQueue != nil {
		stats["queue"] = m.uploadQueue.GetStats()
	}

	if m.healthMonitor != nil {
		stats["health"] = m.healthMonitor.GetSummary()
	}

	if m.watchdog != nil {
		stats["watchdog"] = m.watchdog.GetStatus()
	}

	if m.powerManager != nil {
		stats["power"] = m.powerManager.GetStats()
	}

	if m.errorRecovery != nil {
		stats["error_recovery"] = m.errorRecovery.GetStats()
	}

	if m.security != nil {
		stats["security"] = m.security.GetStats()
	}

	return stats
}

// ========== 硬件识别相关方法 ==========

// GetHardwareInfo 获取完整硬件信息
func (m *MonitorClient) GetHardwareInfo() *HardwareInfo {
    if m.hardwareIdentifier == nil {
        m.hardwareIdentifier = NewHardwareIdentifier()
    }
    return m.hardwareIdentifier.GetCompleteHardwareInfo()
}

// GetHardwareFingerprint 获取硬件指纹
func (m *MonitorClient) GetHardwareFingerprint() string {
    if m.hardwareIdentifier == nil {
        m.hardwareIdentifier = NewHardwareIdentifier()
    }
    fingerprint, _ := m.hardwareIdentifier.GetHardwareFingerprint()
    return fingerprint
}

// GetHardwareFingerprintWithReliability 获取硬件指纹和可信度
func (m *MonitorClient) GetHardwareFingerprintWithReliability() (string, float64) {
    if m.hardwareIdentifier == nil {
        m.hardwareIdentifier = NewHardwareIdentifier()
    }
    return m.hardwareIdentifier.GetHardwareFingerprint()
}

// ========== 开机自启相关方法 ==========

// EnableAutoStart 启用开机自启
func (m *MonitorClient) EnableAutoStart() error {
    if m.autoStartManager == nil {
        m.autoStartManager = NewAutoStartManager("EmployeeMonitor")
    }
    return m.autoStartManager.EnableAutoStart()
}

// DisableAutoStart 禁用开机自启
func (m *MonitorClient) DisableAutoStart() error {
    if m.autoStartManager == nil {
        m.autoStartManager = NewAutoStartManager("EmployeeMonitor")
    }
    return m.autoStartManager.DisableAutoStart()
}

// IsAutoStartEnabled 检查是否已启用开机自启
func (m *MonitorClient) IsAutoStartEnabled() bool {
    if m.autoStartManager == nil {
        m.autoStartManager = NewAutoStartManager("EmployeeMonitor")
    }
    enabled, _ := m.autoStartManager.IsAutoStartEnabled()
    return enabled
}

// GetAutoStartInfo 获取开机自启详细信息
func (m *MonitorClient) GetAutoStartInfo() map[string]interface{} {
    if m.autoStartManager == nil {
        m.autoStartManager = NewAutoStartManager("EmployeeMonitor")
    }
    return m.autoStartManager.GetAutoStartInfo()
}

// ToggleAutoStart 切换开机自启状态
func (m *MonitorClient) ToggleAutoStart() error {
    if m.autoStartManager == nil {
        m.autoStartManager = NewAutoStartManager("EmployeeMonitor")
    }
    return m.autoStartManager.ToggleAutoStart()
}

// SetAutoStartDelay 设置延迟启动
func (m *MonitorClient) SetAutoStartDelay(delaySeconds int) error {
    if m.autoStartManager == nil {
        m.autoStartManager = NewAutoStartManager("EmployeeMonitor")
    }
    return m.autoStartManager.SetAutoStartDelay(delaySeconds)
}