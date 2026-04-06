// client_browser.go - 浏览器监控器（生产级优化版 - 修复嵌套锁问题）
package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"runtime"
	"sort"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	_ "github.com/mattn/go-sqlite3"
	"github.com/shirou/gopsutil/v3/process"
)

// BrowserMonitor 浏览器监控器
type BrowserMonitor struct {
	client          *MonitorClient
	browsers        map[string]string
	historyPaths    map[string][]string
	activeURLs      map[int]*ActiveURL
	reportedURLs    map[string]time.Time // 改为存储时间，便于精确清理
	reportHistory   map[string]time.Time
	reportInterval  time.Duration
	lastReportTime  time.Time
	running         int32
	mu              sync.RWMutex
	stopCh          chan struct{}
	wg              sync.WaitGroup

	// 配置参数
	maxHistorySize     int
	cleanupInterval    time.Duration
	browserReadTimeout time.Duration

	// 统计信息
	stats *MonitorStats
}

// MonitorStats 监控统计信息
type MonitorStats struct {
	TotalReports    int64     `json:"total_reports"`
	TotalURLs       int64     `json:"total_urls"`
	LastSuccessTime time.Time `json:"last_success_time"`
	LastErrorTime   time.Time `json:"last_error_time"`
	ErrorCount      int64     `json:"error_count"`
	mu              sync.RWMutex
}

// ActiveURL 活跃URL记录
type ActiveURL struct {
    PID         int       `json:"pid"`
    Browser     string    `json:"browser"`
    URL         string    `json:"url"`          // 如果能提取到URL
    PageTitle   string    `json:"page_title"`   // 页面标题
    Title       string    `json:"title"`        // 原始窗口标题
    StartTime   time.Time `json:"start_time"`
    LastSeen    time.Time `json:"last_seen"`
}

// BrowserHistory 浏览器历史记录（确保字段完整）
type BrowserHistory struct {
    EmployeeID string    `json:"employee_id"`
    ClientID   string    `json:"client_id"`
    URL        string    `json:"url"`           // URL（如果能提取到）
    PageTitle  string    `json:"page_title"`    // 页面标题
    Title      string    `json:"title"`         // 原始窗口标题
    Browser    string    `json:"browser"`
    VisitTime  time.Time `json:"visit_time"`
    Duration   int       `json:"duration"`
}

// WindowInfo 窗口信息（保留，可能被其他代码使用）
type WindowInfo struct {
	PID   int    `json:"pid"`
	Title string `json:"title"`
	HWND  uintptr `json:"hwnd"`
}

// BrowserConfig 浏览器配置（保留，可能被其他代码使用）
type BrowserConfig struct {
	Name         string
	ProcessNames []string
	WindowTitle  string
	HistoryPaths []string
}

// NewBrowserMonitor 创建浏览器监控器
func NewBrowserMonitor(client *MonitorClient) *BrowserMonitor {
	userHome, _ := os.UserHomeDir()

	// 构建浏览器历史路径
	historyPaths := map[string][]string{
		"Chrome": {
			filepath.Join(userHome, "AppData", "Local", "Google", "Chrome", "User Data", "Default", "History"),
			filepath.Join(userHome, "AppData", "Local", "Google", "Chrome", "User Data", "Profile *", "History"),
		},
		"Edge": {
			filepath.Join(userHome, "AppData", "Local", "Microsoft", "Edge", "User Data", "Default", "History"),
		},
		"Firefox": {
			filepath.Join(userHome, "AppData", "Roaming", "Mozilla", "Firefox", "Profiles", "*.default-release", "places.sqlite"),
		},
		"Brave": {
			filepath.Join(userHome, "AppData", "Local", "BraveSoftware", "Brave-Browser", "User Data", "Default", "History"),
		},
		"Opera": {
			filepath.Join(userHome, "AppData", "Roaming", "Opera Software", "Opera Stable", "History"),
		},
	}

	return &BrowserMonitor{
		client: client,
		browsers: map[string]string{
			"chrome.exe":  "Chrome",
			"msedge.exe":  "Edge",
			"firefox.exe": "Firefox",
			"brave.exe":   "Brave",
			"opera.exe":   "Opera",
		},
		historyPaths:       historyPaths,
		activeURLs:         make(map[int]*ActiveURL),
		reportedURLs:       make(map[string]time.Time),
		reportHistory:      make(map[string]time.Time),
		reportInterval:     120 * time.Second,
		stopCh:             make(chan struct{}),
		maxHistorySize:     10000,
		cleanupInterval:    time.Hour,
		browserReadTimeout: 5 * time.Second,
		stats:              &MonitorStats{},
	}
}

// StartMonitoring 启动监控
// client_browser.go - 在 StartMonitoring 中添加诊断
func (b *BrowserMonitor) StartMonitoring() {
    if !atomic.CompareAndSwapInt32(&b.running, 0, 1) {
        logWarn("浏览器监控器已在运行中")
        return
    }

    logInfo("浏览器监控器启动 [上报间隔: %v, 最大记录: %d]", b.reportInterval, b.maxHistorySize)
    
    // ✅ 添加诊断
    go b.diagnoseHistoryPaths()
    
    b.wg.Add(1)
    go b.monitorLoop()
    go b.cleanupLoop()
}

// 诊断历史文件路径
func (b *BrowserMonitor) diagnoseHistoryPaths() {
    time.Sleep(2 * time.Second) // 等待启动完成
    
    logInfo("========== 浏览器历史路径诊断 ==========")
    userHome, _ := os.UserHomeDir()
    logInfo("用户目录: %s", userHome)
    
    for browserType, paths := range b.historyPaths {
        for _, pattern := range paths {
            matches, _ := filepath.Glob(pattern)
            if len(matches) > 0 {
                for _, match := range matches {
                    info, err := os.Stat(match)
                    if err == nil {
                        logInfo("✅ %s 历史文件存在: %s (大小: %d bytes)", 
                            browserType, match, info.Size())
                    } else {
                        logInfo("❌ %s 历史文件存在但无法访问: %s, %v", 
                            browserType, match, err)
                    }
                }
            } else {
                logInfo("❌ %s 历史文件不存在: %s", browserType, pattern)
            }
        }
    }
    logInfo("========================================")
}

// StopMonitoring 停止监控
func (b *BrowserMonitor) StopMonitoring() {
	if !atomic.CompareAndSwapInt32(&b.running, 1, 0) {
		return
	}

	logInfo("浏览器监控器停止中...")
	close(b.stopCh)

	// 等待完成，带超时
	done := make(chan struct{})
	go func() {
		b.wg.Wait()
		close(done)
	}()

	select {
	case <-done:
		logInfo("浏览器监控器已停止")
	case <-time.After(5 * time.Second):
		logWarn("浏览器监控器停止超时，强制退出")
	}

	// 上报最终统计
	b.reportStats()
}

// monitorLoop 主监控循环
func (b *BrowserMonitor) monitorLoop() {
	defer b.wg.Done()

	ticker := time.NewTicker(5 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			if atomic.LoadInt32(&b.client.running) == 0 {
				return
			}
			b.trackActiveBrowsers()
			b.collectAndReport()
		case <-b.stopCh:
			return
		}
	}
}

// cleanupLoop 定期清理循环
func (b *BrowserMonitor) cleanupLoop() {
	ticker := time.NewTicker(b.cleanupInterval)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			b.cleanupExpiredData()
		case <-b.stopCh:
			return
		}
	}
}

// trackActiveBrowsers 跟踪活跃浏览器
func (b *BrowserMonitor) trackActiveBrowsers() {
    currentTime := time.Now()
    foreground := b.getForegroundBrowser()

    b.mu.Lock()
    defer b.mu.Unlock()

    // 检查前台窗口是否是浏览器
    isBrowserForeground := foreground != nil && foreground.PID > 0

    if isBrowserForeground {
        // 当前是浏览器窗口，正常处理
        pid := foreground.PID
        pageTitle := b.extractPageTitle(foreground.Title)
        url := b.extractURLFromTitle(foreground.Title)
        
        // 使用页面标题作为标识
        identifier := pageTitle
        if identifier == "" {
            identifier = url
        }
        if identifier == "" {
            identifier = "未知页面"
        }

        if existing, ok := b.activeURLs[pid]; ok {
            // 更新最后活跃时间
            existing.LastSeen = currentTime
            
            // 检查页面是否变化
            if existing.URL != identifier && identifier != "" {
                // ✅ 页面变化，立即保存旧页面（只要超过5秒）
                duration := int(existing.LastSeen.Sub(existing.StartTime).Seconds())
                if duration >= 5 {
                    logDebug("🔄 页面切换，保存旧页面: %s -> %s (浏览时长: %d秒)", 
                        existing.URL, identifier, duration)
                    b.saveURActivity(existing, duration)
                } else {
                    logDebug("页面切换太快，丢弃旧页面: %s (时长: %d秒)", existing.URL, duration)
                }
                // 开始新页面跟踪
                existing.URL = identifier
                existing.PageTitle = pageTitle
                existing.Title = foreground.Title
                existing.StartTime = currentTime
                existing.LastSeen = currentTime
                logDebug("🆕 开始跟踪新页面: %s - %s", foreground.Browser, identifier)
            }
        } else if identifier != "" {
            // 新页面，创建记录
            b.activeURLs[pid] = &ActiveURL{
                PID:       pid,
                Browser:   foreground.Browser,
                URL:       identifier,
                PageTitle: pageTitle,
                Title:     foreground.Title,
                StartTime: currentTime,
                LastSeen:  currentTime,
            }
            logDebug("🆕 开始跟踪新页面: %s - %s", foreground.Browser, identifier)
        }
    } else {
        // ✅ 当前不是浏览器窗口，立即结束所有正在跟踪的页面
        logDebug("📴 用户离开浏览器，保存所有浏览记录")
        for _, info := range b.activeURLs {
            duration := int(info.LastSeen.Sub(info.StartTime).Seconds())
            if duration >= 5 && info.URL != "" && info.URL != "未知页面" {
                logInfo("⏹️ 保存页面: %s - %s (浏览时长: %d秒)", 
                    info.Browser, info.URL, duration)
                b.saveURActivity(info, duration)
            } else if duration < 5 {
                logDebug("丢弃短时间浏览: %s (时长: %d秒)", info.URL, duration)
            }
        }
        // 清空所有活跃记录
        b.activeURLs = make(map[int]*ActiveURL)
        return
    }

    // 清理超时记录（超过30秒未更新，作为兜底）
    toRemove := make([]int, 0)
    for pid, info := range b.activeURLs {
        if currentTime.Sub(info.LastSeen) > 30*time.Second {
            duration := int(info.LastSeen.Sub(info.StartTime).Seconds())
            if duration >= 5 && info.URL != "" && info.URL != "未知页面" {
                logInfo("⏹️ 超时保存页面: %s - %s (浏览时长: %d秒)", 
                    info.Browser, info.URL, duration)
                b.saveURActivity(info, duration)
            }
            toRemove = append(toRemove, pid)
        }
    }

    for _, pid := range toRemove {
        delete(b.activeURLs, pid)
    }
}

// extractPageTitle 从窗口标题提取页面标题
func (b *BrowserMonitor) extractPageTitle(title string) string {
    if title == "" {
        return ""
    }

    // 移除浏览器名称后缀
    browserSuffixes := []string{
        " - Google Chrome", " - Chromium",
        " - Microsoft Edge", " - Edge",
        " - Mozilla Firefox", " - Firefox",
        " - Brave", " - Opera", " - Vivaldi",
    }

    for _, suffix := range browserSuffixes {
        if strings.HasSuffix(title, suffix) {
            title = strings.TrimSuffix(title, suffix)
            break
        }
        if strings.Contains(title, suffix) {
            parts := strings.Split(title, suffix)
            if len(parts) > 0 {
                title = strings.TrimSpace(parts[0])
                break
            }
        }
    }

    return strings.TrimSpace(title)
}

// getForegroundBrowser 获取当前前台浏览器
func (b *BrowserMonitor) getForegroundBrowser() *ForegroundBrowser {
    
    if runtime.GOOS != "windows" {
        logDebug("🔍 getForegroundBrowser: 非Windows系统")
        return nil
    }

    // 使用已有的 Windows API 函数
    winInfo := GetForegroundWindowInfo()
    if winInfo == nil {
        logDebug("🔍 getForegroundBrowser: GetForegroundWindowInfo 返回 nil")
        return nil
    }
    if winInfo.PID == 0 {
        logDebug("🔍 getForegroundBrowser: 窗口 PID 为 0")
        return nil
    }
    

    p, err := process.NewProcess(int32(winInfo.PID))
    if err != nil {
        logDebug("🔍 getForegroundBrowser: 无法获取进程信息, err=%v", err)
        return nil
    }

    name, err := p.Name()
    if err != nil || name == "" {
        logDebug("🔍 getForegroundBrowser: 无法获取进程名, err=%v", err)
        return nil
    }


    browserName, isBrowser := b.browsers[strings.ToLower(name)]
    if !isBrowser {
        logDebug("🔍 getForegroundBrowser: 进程 %s 不是浏览器 (支持列表: %v)", name, b.browsers)
        return nil
    }

    logDebug("✅ 检测到浏览器: %s, 标题: %s", browserName, winInfo.Title)

    return &ForegroundBrowser{
        PID:     int(winInfo.PID),
        Name:    name,
        Browser: browserName,
        Title:   winInfo.Title,
    }
}

// extractURLFromTitle 从窗口标题提取URL（增强版）
// extractURLFromTitle 从窗口标题提取页面标题（用于展示）
func (b *BrowserMonitor) extractURLFromTitle(title string) string {
    if title == "" {
        return ""
    }

    logDebug("extractURLFromTitle: 原始标题=%s", title)

    // 移除浏览器名称后缀，得到页面标题
    browserSuffixes := []string{
        " - Google Chrome", " - Chromium",
        " - Microsoft Edge", " - Edge",
        " - Mozilla Firefox", " - Firefox",
        " - Brave", " - Opera", " - Vivaldi",
    }

    for _, suffix := range browserSuffixes {
        if strings.HasSuffix(title, suffix) {
            title = strings.TrimSuffix(title, suffix)
            logDebug("extractURLFromTitle: 移除后缀后=%s", title)
            break
        }
    }

    // 清理空格
    title = strings.TrimSpace(title)
    
    // 如果没有移除后缀，尝试其他模式
    // 有些浏览器标题格式是 "页面标题 - 浏览器名称"
    for _, suffix := range browserSuffixes {
        if strings.Contains(title, suffix) {
            parts := strings.Split(title, suffix)
            if len(parts) > 0 {
                title = strings.TrimSpace(parts[0])
                break
            }
        }
    }

    logDebug("extractURLFromTitle: 最终页面标题=%s", title)
    return title
}

// saveURActivity 保存URL活动记录
// saveURActivity 保存URL活动记录
func (b *BrowserMonitor) saveURActivity(info *ActiveURL, duration int) {
    if b.client.employeeID == "" || info.URL == "" || info.URL == "未知页面" {
        return
    }

    // 只保存浏览超过5秒的记录
    if duration < 5 {
        logDebug("浏览时长不足5秒，丢弃: %s (%d秒)", info.URL, duration)
        return
    }

    data := BrowserHistory{
        EmployeeID: b.client.employeeID,
        ClientID:   b.client.clientID,
        URL:        info.URL,
        PageTitle:  info.PageTitle,
        Title:      info.Title,
        Browser:    info.Browser,
        Duration:   duration,
        VisitTime:  info.StartTime,
    }

    cacheFile := b.getCacheFilePath(info.StartTime)
    if err := b.saveToCache(cacheFile, data); err != nil {
        logError("保存浏览器活动到缓存失败: %v", err)
    } else {
        logDebug("💾 保存浏览记录: [%s] %s (%d秒)", info.Browser, info.URL, duration)
    }
}

// collectAndReport 收集并上报浏览器历史
func (b *BrowserMonitor) collectAndReport() {
    currentTime := time.Now()

    logDebug("collectAndReport: lastReportTime=%v, 距离上次=%v, interval=%v",
        b.lastReportTime, currentTime.Sub(b.lastReportTime), b.reportInterval)

    // 检查上报间隔
    if currentTime.Sub(b.lastReportTime) < b.reportInterval {
        logDebug("上报间隔未到，跳过")
        return
    }

    if b.client.employeeID == "" {
        logDebug("浏览器历史上报: employeeID未就绪，跳过")
        return
    }

    logInfo("📊 开始收集浏览器历史数据...")

    b.mu.Lock()
    defer b.mu.Unlock()

    // ✅ 收集所有已保存的浏览记录（从缓存文件中读取）
    allHistory := b.readAllSavedHistory()
    
    if len(allHistory) == 0 {
        logInfo("📊 没有浏览记录需要上报")
        b.lastReportTime = currentTime
        return
    }

    // 按时间排序（最新的在前）
    sort.Slice(allHistory, func(i, j int) bool {
        return allHistory[i].VisitTime.After(allHistory[j].VisitTime)
    })

    logInfo("📊 收集到 %d 条浏览记录", len(allHistory))

    // 打印所有记录
    for i, item := range allHistory {
        logInfo("  %d. [%s] %s (浏览时长: %d秒, 时间: %s)", 
            i+1, item.Browser, item.URL, item.Duration,
            item.VisitTime.Format("15:04:05"))
    }

    // 上报所有记录
    if len(allHistory) > 0 {
        b.uploadHistoryLocked(allHistory, currentTime)
    } else {
        b.lastReportTime = currentTime
    }
}

// readAllSavedHistory 读取所有已保存的浏览记录
func (b *BrowserMonitor) readAllSavedHistory() []BrowserHistory {
    results := make([]BrowserHistory, 0)
    cacheDir := "cache"

    // 读取所有浏览器历史缓存文件
    files, err := filepath.Glob(filepath.Join(cacheDir, "browser_*.json"))
    if err != nil {
        return results
    }

    for _, cacheFile := range files {
        data, err := os.ReadFile(cacheFile)
        if err != nil {
            continue
        }

        var item BrowserHistory
        if err := json.Unmarshal(data, &item); err == nil {
            // 补全ID信息
            item.EmployeeID = b.client.employeeID
            item.ClientID = b.client.clientID
            
            // 只保留最近2小时内的记录
            if time.Since(item.VisitTime) < 2*time.Hour {
                results = append(results, item)
            }
        }
        // 读取后删除缓存文件
        os.Remove(cacheFile)
    }

    return results
}

// uploadHistoryLocked 上传历史记录
func (b *BrowserMonitor) uploadHistoryLocked(history []BrowserHistory, currentTime time.Time) {
    if b.client.offlineMode != 0 {
        logInfo("离线模式，浏览器历史已缓存")
        b.saveBatchToCache(history)
        return
    }

    if b.client.apiClient == nil {
        logError("API客户端未初始化")
        b.saveBatchToCache(history)
        return
    }

    logInfo("📤 上报浏览器历史: %d条记录", len(history))

    batchSize := 100
    successCount := 0
    
    for i := 0; i < len(history); i += batchSize {
        end := i + batchSize
        if end > len(history) {
            end = len(history)
        }

        batch := history[i:end]
        
        // 添加重试逻辑
        var err error
        for retry := 0; retry < 3; retry++ {
            if retry > 0 {
                logDebug("重试上报批次 %d-%d (%d/3)", i, end, retry+1)
                time.Sleep(time.Duration(retry) * time.Second)
            }
            
            _, err = b.client.apiClient.Post("/api/browser/history", batch)
            if err == nil {
                break
            }
            logDebug("上报失败: %v", err)
        }
        
        if err != nil {
            logError("上报浏览器历史批次失败: %v", err)
            b.updateStats(false)
            b.saveBatchToCache(batch)
        } else {
            logInfo("✅ 浏览器历史上报成功: %d条 (批次 %d-%d)", len(batch), i, end)
            successCount += len(batch)
        }
    }

    if successCount > 0 {
        b.updateStats(true)
        b.lastReportTime = currentTime
        b.cleanupCacheFiles(history)
    }
}

// collectAllHistory 收集所有浏览器历史
func (b *BrowserMonitor) collectAllHistory() []BrowserHistory {
	history := make([]BrowserHistory, 0)

	// 并发收集各浏览器历史
	var wg sync.WaitGroup
	var mu sync.Mutex
	historyChan := make(chan []BrowserHistory, 5)

	// Chrome/Edge 历史
	wg.Add(1)
	go func() {
		defer wg.Done()
		if chromeHistory := b.readChromiumHistory("Chrome"); len(chromeHistory) > 0 {
			historyChan <- chromeHistory
		}
		if edgeHistory := b.readChromiumHistory("Edge"); len(edgeHistory) > 0 {
			historyChan <- edgeHistory
		}
	}()

	// Firefox 历史
	wg.Add(1)
	go func() {
		defer wg.Done()
		if firefoxHistory := b.readFirefoxHistory(); len(firefoxHistory) > 0 {
			historyChan <- firefoxHistory
		}
	}()

	// 收集结果
	go func() {
		wg.Wait()
		close(historyChan)
	}()

	for h := range historyChan {
		mu.Lock()
		history = append(history, h...)
		mu.Unlock()
	}

	return history
}

// client_browser.go - 修复 readChromiumHistory 函数
func (b *BrowserMonitor) readChromiumHistory(browserType string) []BrowserHistory {
    results := make([]BrowserHistory, 0)
    
    defer func() {
        if r := recover(); r != nil {
            logError("读取浏览器历史时发生 panic: %v", r)
        }
    }()
    
    // ✅ 添加这个变量定义
    cutoffTimestamp := time.Now().Add(-24 * time.Hour).Unix()
    
    paths, ok := b.historyPaths[browserType]
    if !ok {
        return results
    }
    
    for _, pattern := range paths {
        // ✅ 这里使用 filepath.Glob 获取匹配文件
        matches, err := filepath.Glob(pattern)
        if err != nil {
            continue
        }
        
        for _, historyPath := range matches {
            // 使用函数作用域确保资源释放
            func() {
                if !b.isFileAccessible(historyPath) {
                    return
                }
                
                tempFile, err := b.copyToTempFile(historyPath)
                if err != nil {
                    logError("复制历史文件失败: %s, %v", historyPath, err)
                    return
                }
                defer os.Remove(tempFile)
                
                db, err := sql.Open("sqlite3", tempFile)
                if err != nil {
                    logError("打开数据库失败: %v", err)
                    return
                }
                defer db.Close()
                
                db.SetMaxOpenConns(1)
                db.SetMaxIdleConns(0)
                
                if err := db.Ping(); err != nil {
                    logError("数据库连接测试失败: %v", err)
                    return
                }
                
                ctx, cancel := context.WithTimeout(context.Background(), b.browserReadTimeout)
                defer cancel()
                
                // ✅ 修复 SQL 查询
                rows, err := db.QueryContext(ctx, `
                    SELECT url, title, last_visit_time/1000000-11644473600 as visit_time
                    FROM urls
                    WHERE url != '' 
                      AND last_visit_time > ?
                    ORDER BY last_visit_time DESC
                    LIMIT 200
                `, cutoffTimestamp*1000000)
                
                if err != nil {
                    logError("查询失败: %v", err)
                    return
                }
                defer rows.Close()
                
                for rows.Next() {
                    var url, title string
                    var visitTime int64
                    
                    if err := rows.Scan(&url, &title, &visitTime); err != nil {
                        continue
                    }
                    
                    if b.shouldSkipURL(url) {
                        continue
                    }
                    
                    results = append(results, BrowserHistory{
                        URL:       url,
                        PageTitle: b.sanitizeTitle(title),
                        Browser:   browserType,
                        VisitTime: time.Unix(visitTime, 0),
                    })
                }
            }()
        }
    }
    
    return results
}

// readFirefoxHistory 读取Firefox历史（预留接口）
func (b *BrowserMonitor) readFirefoxHistory() []BrowserHistory {
	// Firefox 使用 places.sqlite，表结构不同
	// 此处返回空，实际实现需要处理 Firefox 的数据库结构
	return []BrowserHistory{}
}

// 辅助方法
func (b *BrowserMonitor) getCacheFilePath(t time.Time) string {
	cacheDir := "cache"
	os.MkdirAll(cacheDir, 0755)
	return filepath.Join(cacheDir, fmt.Sprintf("browser_%d_%d.json", t.Unix(), time.Now().UnixNano()))
}

func (b *BrowserMonitor) saveToCache(filePath string, data interface{}) error {
	jsonData, err := json.Marshal(data)
	if err != nil {
		return err
	}
	return os.WriteFile(filePath, jsonData, 0644)
}

func (b *BrowserMonitor) readCacheFiles() []BrowserHistory {
	results := make([]BrowserHistory, 0)
	cacheDir := "cache"

	files, err := filepath.Glob(filepath.Join(cacheDir, "browser_*.json"))
	if err != nil {
		return results
	}

	for _, cacheFile := range files {
		data, err := os.ReadFile(cacheFile)
		if err != nil {
			continue
		}

		var item BrowserHistory
		if err := json.Unmarshal(data, &item); err == nil {
			// 补全ID信息
			item.EmployeeID = b.client.employeeID
			item.ClientID = b.client.clientID
			results = append(results, item)
		}
		os.Remove(cacheFile)
	}

	return results
}

func (b *BrowserMonitor) saveBatchToCache(batch []BrowserHistory) {
	cacheDir := "cache"
	os.MkdirAll(cacheDir, 0755)

	for _, item := range batch {
		cacheFile := filepath.Join(cacheDir, fmt.Sprintf("browser_%d_%d.json",
			item.VisitTime.Unix(), time.Now().UnixNano()))
		jsonData, _ := json.Marshal(item)
		os.WriteFile(cacheFile, jsonData, 0644)
	}
}

func (b *BrowserMonitor) cleanupCacheFiles(history []BrowserHistory) {
    cacheDir := "cache"
    
    for _, item := range history {
        // 尝试匹配可能的缓存文件名格式
        patterns := []string{
            fmt.Sprintf("browser_%d_*.json", item.VisitTime.Unix()),  // 新格式
            fmt.Sprintf("browser_%d.json", item.VisitTime.Unix()),     // 旧格式
        }
        
        for _, pattern := range patterns {
            matches, err := filepath.Glob(filepath.Join(cacheDir, pattern))
            if err != nil {
                continue
            }
            for _, cacheFile := range matches {
                if err := os.Remove(cacheFile); err == nil {
                    logDebug("清理缓存文件: %s", filepath.Base(cacheFile))
                }
            }
        }
    }
}

// ========== cleanupExpiredCacheFiles 已存在 ==========

// cleanupExpiredCacheFiles 清理过期缓存文件（7天以上）
func (b *BrowserMonitor) cleanupExpiredCacheFiles() {
    cacheDir := "cache"
    files, _ := filepath.Glob(filepath.Join(cacheDir, "browser_*.json"))
    cutoffTime := time.Now().Add(-7 * 24 * time.Hour)

    for _, file := range files {
        info, err := os.Stat(file)
        if err != nil {
            continue
        }
        if info.ModTime().Before(cutoffTime) {
            os.Remove(file)
        }
    }
}

func (b *BrowserMonitor) isFileAccessible(path string) bool {
	_, err := os.Stat(path)
	return err == nil
}

// client_browser.go - 修复 copyToTempFile
func (b *BrowserMonitor) copyToTempFile(src string) (string, error) {
    // ✅ 检查源文件是否存在
    srcInfo, err := os.Stat(src)
    if err != nil {
        return "", fmt.Errorf("源文件不存在: %w", err)
    }
    
    if srcInfo.Size() == 0 {
        return "", fmt.Errorf("源文件为空: %s", src)
    }
    
    tempFile := filepath.Join(os.TempDir(), fmt.Sprintf("browser_history_%d.db", time.Now().UnixNano()))
    
    // ✅ 使用带缓冲的复制
    srcFile, err := os.Open(src)
    if err != nil {
        return "", fmt.Errorf("打开源文件失败: %w", err)
    }
    defer srcFile.Close()
    
    dstFile, err := os.Create(tempFile)
    if err != nil {
        return "", fmt.Errorf("创建临时文件失败: %w", err)
    }
    defer dstFile.Close()
    
    // 复制文件内容
    written, err := io.Copy(dstFile, srcFile)
    if err != nil {
        os.Remove(tempFile)
        return "", fmt.Errorf("复制文件失败: %w", err)
    }
    
    if written != srcInfo.Size() {
        os.Remove(tempFile)
        return "", fmt.Errorf("复制不完整: 期望 %d, 实际 %d", srcInfo.Size(), written)
    }
    
    // 确保数据写入磁盘
    if err := dstFile.Sync(); err != nil {
        os.Remove(tempFile)
        return "", fmt.Errorf("同步文件失败: %w", err)
    }
    
    logDebug("临时文件创建成功: %s (大小: %d bytes)", tempFile, written)
    return tempFile, nil
}
func (b *BrowserMonitor) shouldSkipURL(url string) bool {
	if url == "" {
		return true
	}

	// 跳过内部页面
	skipPrefixes := []string{
		"chrome://", "edge://", "about:", "file://",
		"data:", "javascript:", "blob:", "view-source:",
	}

	for _, prefix := range skipPrefixes {
		if strings.HasPrefix(url, prefix) {
			return true
		}
	}

	return false
}

func (b *BrowserMonitor) sanitizeTitle(title string) string {
	// 清理标题中的特殊字符
	title = strings.TrimSpace(title)
	if len(title) > 500 {
		title = title[:500]
	}
	return title
}

// cleanupReportedURLs 清理过期的去重记录
func (b *BrowserMonitor) cleanupReportedURLs(cutoffTime time.Time) {
    for urlKey, lastTime := range b.reportedURLs {
        if lastTime.Before(cutoffTime) {
            delete(b.reportedURLs, urlKey)
        }
    }
    
    // reportHistory 已不再使用，但保留清理逻辑以兼容
    for url, lastTime := range b.reportHistory {
        if lastTime.Before(cutoffTime) {
            delete(b.reportHistory, url)
        }
    }
}

func (b *BrowserMonitor) cleanupExpiredData() {
    cutoffTime := time.Now().Add(-24 * time.Hour)

    b.mu.Lock()
    b.cleanupReportedURLs(cutoffTime)
    b.mu.Unlock()

    // 清理过期缓存文件
    go b.cleanupExpiredCacheFiles()

    logDebug("清理过期数据完成: reportedURLs=%d", len(b.reportedURLs))
}

func (b *BrowserMonitor) updateStats(success bool) {
	b.stats.mu.Lock()
	defer b.stats.mu.Unlock()

	if success {
		b.stats.TotalReports++
		b.stats.LastSuccessTime = time.Now()
	} else {
		b.stats.ErrorCount++
		b.stats.LastErrorTime = time.Now()
	}
}

func (b *BrowserMonitor) reportStats() {
	b.stats.mu.RLock()
	defer b.stats.mu.RUnlock()

	logInfo("浏览器监控统计: 总上报=%d, 错误数=%d, 最后成功=%v",
		b.stats.TotalReports, b.stats.ErrorCount, b.stats.LastSuccessTime)
}

// ForegroundBrowser 前台浏览器信息
type ForegroundBrowser struct {
	PID     int
	Name    string
	Browser string
	Title   string
}