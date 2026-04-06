// client_operations.go - 截图、上传、心跳、网络监控等业务操作（完整重构版）
package main

import (
	"bytes"
	"crypto/md5"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"image/jpeg"
	"io"
	"mime/multipart"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/chai2010/webp"
	"github.com/kbinani/screenshot"
)

// ========== 健康监控 ==========
type HealthMonitor struct {
	components        map[string]*ComponentHealth
	history           []HealthRecord
	checkInterval     time.Duration
	recoveryCooldown  time.Duration
	lastRecoveryTime  map[string]time.Time
	recoveryCallbacks map[string][]func()
	running           int32
	mu                sync.RWMutex
	stopCh            chan struct{}
	wg                sync.WaitGroup
}

func NewHealthMonitor(checkInterval, recoveryCooldown time.Duration) *HealthMonitor {
	return &HealthMonitor{
		components:        make(map[string]*ComponentHealth),
		history:           make([]HealthRecord, 0, 1000),
		checkInterval:     checkInterval,
		recoveryCooldown:  recoveryCooldown,
		lastRecoveryTime:  make(map[string]time.Time),
		recoveryCallbacks: make(map[string][]func()),
		stopCh:            make(chan struct{}),
	}
}

func (h *HealthMonitor) RegisterComponent(name string, callback func()) {
	h.mu.Lock()
	defer h.mu.Unlock()

	if _, exists := h.components[name]; !exists {
		h.components[name] = &ComponentHealth{
			Name:            name,
			Status:          HealthUnknown,
			LastCheckTime:   float64(time.Now().Unix()),
			LastHealthyTime: 0,
			FailureCount:    0,
			RecoveryCount:   0,
			Message:         "",
			Metrics:         make(map[string]interface{}),
		}
		if callback != nil {
			h.recoveryCallbacks[name] = append(h.recoveryCallbacks[name], callback)
		}
		logInfo("组件已注册: %s", name)
	}
}

func (h *HealthMonitor) UpdateStatus(component string, status HealthStatus, message string, metrics map[string]interface{}) {
	h.mu.Lock()
	defer h.mu.Unlock()

	comp, exists := h.components[component]
	if !exists {
		logWarn("尝试更新未注册的组件: %s", component)
		return
	}

	now := float64(time.Now().Unix())
	comp.Status = status
	comp.LastCheckTime = now
	comp.Message = message

	if metrics != nil {
		for k, v := range metrics {
			comp.Metrics[k] = v
		}
	}

	if status == HealthHealthy {
		comp.LastHealthyTime = now
		comp.FailureCount = 0
	} else if status == HealthDegraded || status == HealthUnhealthy {
		comp.FailureCount++
	}

	record := HealthRecord{
		Timestamp:    now,
		Component:    component,
		Status:       status,
		Message:      message,
		ResponseTime: 0,
		Details:      metrics,
	}
	h.history = append(h.history, record)
	if len(h.history) > 1000 {
		h.history = h.history[1:]
	}

	if comp.FailureCount >= 3 {
		h.triggerRecovery(component)
	}
}

func (h *HealthMonitor) triggerRecovery(component string) {
	now := time.Now()
	lastRecovery, exists := h.lastRecoveryTime[component]

	if exists && now.Sub(lastRecovery) < h.recoveryCooldown {
		return
	}

	h.lastRecoveryTime[component] = now

	if comp, ok := h.components[component]; ok {
		comp.RecoveryCount++
	}

	logWarn("触发组件恢复: %s", component)

	for _, callback := range h.recoveryCallbacks[component] {
		go func(cb func()) {
			defer func() {
				if r := recover(); r != nil {
					logError("恢复回调panic: %v", r)
				}
			}()
			cb()
		}(callback)
	}
}

func (h *HealthMonitor) GetComponentStatus(component string) *ComponentHealth {
	h.mu.RLock()
	defer h.mu.RUnlock()

	if comp, ok := h.components[component]; ok {
		return comp
	}
	return nil
}

func (h *HealthMonitor) GetSummary() map[string]interface{} {
	h.mu.RLock()
	defer h.mu.RUnlock()

	total := len(h.components)
	healthy, degraded, unhealthy, unknown := 0, 0, 0, 0
	totalRecoveries := 0

	for _, comp := range h.components {
		switch comp.Status {
		case HealthHealthy:
			healthy++
		case HealthDegraded:
			degraded++
		case HealthUnhealthy:
			unhealthy++
		default:
			unknown++
		}
		totalRecoveries += comp.RecoveryCount
	}

	healthRate := 0.0
	if total > 0 {
		healthRate = float64(healthy) / float64(total)
	}

	return map[string]interface{}{
		"total":            total,
		"healthy":          healthy,
		"degraded":         degraded,
		"unhealthy":        unhealthy,
		"unknown":          unknown,
		"health_rate":      healthRate,
		"total_recoveries": totalRecoveries,
	}
}

func (h *HealthMonitor) StartMonitoring() {
	if !atomic.CompareAndSwapInt32(&h.running, 0, 1) {
		return
	}

	h.wg.Add(1)
	go h.monitorLoop()
	logInfo("健康监控已启动")
}

func (h *HealthMonitor) StopMonitoring() {
	if !atomic.CompareAndSwapInt32(&h.running, 1, 0) {
		return
	}

	close(h.stopCh)

	done := make(chan struct{})
	go func() {
		h.wg.Wait()
		close(done)
	}()

	select {
	case <-done:
		logInfo("健康监控已停止")
	case <-time.After(5 * time.Second):
		logWarn("健康监控停止超时")
	}
}

func (h *HealthMonitor) monitorLoop() {
	defer h.wg.Done()

	ticker := time.NewTicker(h.checkInterval)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			now := float64(time.Now().Unix())
			h.mu.RLock()
			for name, comp := range h.components {
				if now-comp.LastCheckTime > float64(h.checkInterval.Seconds())*3 {
					logDebug("组件 %s 状态更新超时", name)
					comp.Status = HealthUnknown
				}
			}
			h.mu.RUnlock()
		case <-h.stopCh:
			return
		}
	}
}

// ========== 进程看门狗 ==========
type WatchedProcess struct {
	Func                 func()
	AutoRestart          bool
	HealthCheck          func() bool
	HealthCheckInterval  time.Duration
	LastHealthCheck      time.Time
	HealthCheckFailures  int
	Thread               *sync.WaitGroup
	RestartCount         int
	LastRestart          time.Time
	Status               string
	Error                error
	StopCh               chan struct{}
	Running              bool
}

type ProcessWatchdog struct {
	processes     map[string]*WatchedProcess
	checkInterval time.Duration
	maxRestarts   int
	running       int32
	mu            sync.RWMutex
	stopCh        chan struct{}
	wg            sync.WaitGroup
	stats         map[string]interface{}
}

func NewProcessWatchdog(checkInterval time.Duration, maxRestarts int) *ProcessWatchdog {
	return &ProcessWatchdog{
		processes:     make(map[string]*WatchedProcess),
		checkInterval: checkInterval,
		maxRestarts:   maxRestarts,
		stopCh:        make(chan struct{}),
		stats: map[string]interface{}{
			"total_restarts":              0,
			"failed_restarts":             0,
			"total_health_check_failures": 0,
		},
	}
}

func (w *ProcessWatchdog) Watch(name string, fn func(), autoRestart bool, healthCheck func() bool, healthCheckInterval time.Duration) bool {
	w.mu.Lock()
	defer w.mu.Unlock()

	if _, exists := w.processes[name]; exists {
		logWarn("进程 %s 已存在", name)
		return false
	}

	w.processes[name] = &WatchedProcess{
		Func:                fn,
		AutoRestart:         autoRestart,
		HealthCheck:         healthCheck,
		HealthCheckInterval: healthCheckInterval,
		Status:              "stopped",
		StopCh:              make(chan struct{}),
	}

	logInfo("进程已加入监控: %s", name)
	return true
}

func (w *ProcessWatchdog) StartWatch(name string) bool {
	w.mu.Lock()
	defer w.mu.Unlock()

	proc, exists := w.processes[name]
	if !exists {
		return false
	}

	if proc.RestartCount >= w.maxRestarts {
		logError("进程 %s 已达最大重启次数", name)
		proc.Status = "failed"
		return false
	}

	if time.Since(proc.LastRestart) < time.Minute && proc.LastRestart.Unix() > 0 {
		return false
	}

	proc.StopCh = make(chan struct{})
	proc.Running = true

	wg := &sync.WaitGroup{}
	wg.Add(1)
	proc.Thread = wg

	go w.runProcess(name, proc)

	proc.Status = "running"
	proc.RestartCount++
	proc.LastRestart = time.Now()

	logInfo("看门狗启动进程: %s", name)
	return true
}

func (w *ProcessWatchdog) runProcess(name string, proc *WatchedProcess) {
	defer func() {
		if r := recover(); r != nil {
			logError("进程 %s panic: %v", name, r)
			proc.Status = "crashed"
			proc.Error = fmt.Errorf("%v", r)
		}
		proc.Running = false
		proc.Thread.Done()
	}()

	done := make(chan struct{})
	go func() {
		proc.Func()
		close(done)
	}()

	select {
	case <-done:
		proc.Status = "stopped"
		logInfo("进程 %s 正常退出", name)
	case <-proc.StopCh:
		proc.Status = "stopped"
		logInfo("进程 %s 被停止", name)
	}

	if proc.AutoRestart && proc.Status != "failed" {
		logInfo("等待重启进程 %s", name)
		time.Sleep(5 * time.Second)
		w.StartWatch(name)
	}
}

func (w *ProcessWatchdog) Heartbeat(name string) {
	w.mu.RLock()
	defer w.mu.RUnlock()

	if proc, exists := w.processes[name]; exists {
		proc.HealthCheckFailures = 0
	}
}

func (w *ProcessWatchdog) StopWatch(name string) {
	w.mu.Lock()
	defer w.mu.Unlock()

	proc, exists := w.processes[name]
	if !exists {
		return
	}

	proc.AutoRestart = false
	proc.Status = "stopping"
	close(proc.StopCh)

	if proc.Thread != nil {
		done := make(chan struct{})
		go func() {
			proc.Thread.Wait()
			close(done)
		}()

		select {
		case <-done:
		case <-time.After(10 * time.Second):
			logWarn("停止进程 %s 超时", name)
		}
	}

	proc.Status = "stopped"
	proc.Thread = nil
	logInfo("看门狗停止进程: %s", name)
}

func (w *ProcessWatchdog) Start() {
	if !atomic.CompareAndSwapInt32(&w.running, 0, 1) {
		return
	}

	w.wg.Add(1)
	go w.watchdogLoop()
	logInfo("进程看门狗已启动")
}

func (w *ProcessWatchdog) Stop() {
	if !atomic.CompareAndSwapInt32(&w.running, 1, 0) {
		return
	}

	close(w.stopCh)

	done := make(chan struct{})
	go func() {
		w.wg.Wait()
		close(done)
	}()

	select {
	case <-done:
		logInfo("进程看门狗已停止")
	case <-time.After(10 * time.Second):
		logWarn("进程看门狗停止超时")
	}
}

func (w *ProcessWatchdog) watchdogLoop() {
	defer w.wg.Done()

	ticker := time.NewTicker(w.checkInterval)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			w.mu.RLock()
			for name, proc := range w.processes {
				if !proc.AutoRestart {
					continue
				}

				if !proc.Running {
					logWarn("进程 %s 已停止，准备重启", name)
					go w.StartWatch(name)
					continue
				}

				if proc.HealthCheck != nil && time.Since(proc.LastHealthCheck) >= proc.HealthCheckInterval {
					go w.performHealthCheck(name, proc)
				}
			}
			w.mu.RUnlock()
		case <-w.stopCh:
			return
		}
	}
}

func (w *ProcessWatchdog) performHealthCheck(name string, proc *WatchedProcess) {
	w.mu.Lock()
	defer w.mu.Unlock()

	proc.LastHealthCheck = time.Now()

	isHealthy := true
	if proc.HealthCheck != nil {
		isHealthy = proc.HealthCheck()
	}

	if !isHealthy {
		proc.HealthCheckFailures++
		logDebug("进程 %s 健康检查失败 (%d/3)", name, proc.HealthCheckFailures)

		if proc.HealthCheckFailures >= 3 {
			logError("进程 %s 连续3次失败，准备重启", name)
			if val, ok := w.stats["total_health_check_failures"].(int); ok {
				w.stats["total_health_check_failures"] = val + 1
			}
			w.restartProcess(name)
		}
	} else if proc.HealthCheckFailures > 0 {
		logDebug("进程 %s 健康恢复", name)
		proc.HealthCheckFailures = 0
	}
}

func (w *ProcessWatchdog) restartProcess(name string) {
	w.mu.Lock()
	defer w.mu.Unlock()

	proc, exists := w.processes[name]
	if !exists || atomic.LoadInt32(&w.running) == 0 {
		return
	}

	if !proc.AutoRestart {
		return
	}

	if proc.RestartCount >= w.maxRestarts {
		logError("进程 %s 已达最大重启次数", name)
		proc.Status = "failed"
		return
	}

	logInfo("正在重启进程: %s", name)

	if proc.Thread != nil {
		close(proc.StopCh)
	}

	proc.StopCh = make(chan struct{})
	proc.Thread = nil
	proc.Status = "stopped"
	proc.Running = false

	go w.StartWatch(name)

	if val, ok := w.stats["total_restarts"].(int); ok {
		w.stats["total_restarts"] = val + 1
	}
}

func (w *ProcessWatchdog) GetStatus() map[string]interface{} {
	w.mu.RLock()
	defer w.mu.RUnlock()

	processes := make(map[string]interface{})
	for name, proc := range w.processes {
		processes[name] = map[string]interface{}{
			"status":        proc.Status,
			"restart_count": proc.RestartCount,
			"error":         proc.Error,
			"auto_restart":  proc.AutoRestart,
			"alive":         proc.Running,
		}
	}

	return map[string]interface{}{
		"running":   atomic.LoadInt32(&w.running) == 1,
		"processes": processes,
		"stats":     w.stats,
	}
}

// ========== 上传队列 ==========
type UploadQueue struct {
	queue        chan *UploadTask
	client       interface{}
	workers      []*sync.WaitGroup
	running      int32
	cacheDir     string
	maxCacheSize int64
	maxRetries   int
	mu           sync.RWMutex
	stopCh       chan struct{}
	wg           sync.WaitGroup
	stats        map[string]interface{}
	backpressure int32
}


// cleanupCache 清理过期缓存文件
func (u *UploadQueue) cleanupCache() {
    u.mu.Lock()
    defer u.mu.Unlock()
    
    files, err := filepath.Glob(filepath.Join(u.cacheDir, "*"))
    if err != nil {
        logDebug("获取缓存文件列表失败: %v", err)
        return
    }
    
    // 收集文件信息
    type fileInfo struct {
        path string
        size int64
        mod  time.Time
    }
    var fileList []fileInfo
    var totalSize int64
    
    for _, file := range files {
        info, err := os.Stat(file)
        if err != nil {
            continue
        }
        if info.IsDir() || strings.HasPrefix(filepath.Base(file), ".tmp_") {
            continue
        }
        
        fileList = append(fileList, fileInfo{
            path: file,
            size: info.Size(),
            mod:  info.ModTime(),
        })
        totalSize += info.Size()
    }
    
    // 如果超过最大缓存大小，删除最旧的文件
    if totalSize > u.maxCacheSize {
        // 按修改时间排序（最旧的在前）
        for i := 0; i < len(fileList)-1; i++ {
            for j := i + 1; j < len(fileList); j++ {
                if fileList[i].mod.After(fileList[j].mod) {
                    fileList[i], fileList[j] = fileList[j], fileList[i]
                }
            }
        }
        
        freed := int64(0)
        deleted := 0
        for _, f := range fileList {
            if totalSize-freed <= u.maxCacheSize {
                break
            }
            if err := os.Remove(f.path); err == nil {
                freed += f.size
                deleted++
                u.mu.Lock()
				if val, ok := u.stats["discarded"].(int64); ok {
					u.stats["discarded"] = val + 1
				}
				u.mu.Unlock()
                logDebug("删除过期缓存: %s (%.2fKB)", filepath.Base(f.path), float64(f.size)/1024)
            }
        }
        
        if freed > 0 {
            logInfo("缓存清理: 删除 %d 个文件，释放 %.2fMB", deleted, float64(freed)/1024/1024)
        }
    }
}

// GetStats 获取统计信息（完善版）
func (u *UploadQueue) GetStats() map[string]interface{} {
    u.mu.RLock()
    defer u.mu.RUnlock()
    
    stats := make(map[string]interface{})
    for k, v := range u.stats {
        stats[k] = v
    }
    stats["queue_size"] = len(u.queue)
    stats["queue_maxsize"] = cap(u.queue)
    stats["backpressure"] = atomic.LoadInt32(&u.backpressure)
    stats["is_running"] = atomic.LoadInt32(&u.running) == 1
    
    // 计算缓存统计
    files, _ := filepath.Glob(filepath.Join(u.cacheDir, "*"))
    cacheCount := 0
    var cacheSize int64
    var oldestFile time.Time
    var newestFile time.Time
    
    for _, f := range files {
        if info, err := os.Stat(f); err == nil && !info.IsDir() && !strings.HasPrefix(filepath.Base(f), ".tmp_") {
            cacheCount++
            cacheSize += info.Size()
            if oldestFile.IsZero() || info.ModTime().Before(oldestFile) {
                oldestFile = info.ModTime()
            }
            if newestFile.IsZero() || info.ModTime().After(newestFile) {
                newestFile = info.ModTime()
            }
        }
    }
    
    stats["cache_count"] = cacheCount
    stats["cache_size"] = cacheSize
    stats["cache_size_mb"] = float64(cacheSize) / 1024 / 1024
    if !oldestFile.IsZero() {
        stats["cache_oldest"] = oldestFile.Format("2006-01-02 15:04:05")
        stats["cache_age_hours"] = time.Since(oldestFile).Hours()
    }
    if !newestFile.IsZero() {
        stats["cache_newest"] = newestFile.Format("2006-01-02 15:04:05")
    }
    
    return stats
}

func NewUploadQueue(client interface{}, maxQueueSize int, workerCount int, cacheDir string, maxCacheSize int64) *UploadQueue {
	if maxQueueSize <= 0 {
		maxQueueSize = 100
	}
	if workerCount <= 0 {
		workerCount = 3
	}

	return &UploadQueue{
		queue:        make(chan *UploadTask, maxQueueSize),
		client:       client,
		cacheDir:     cacheDir,
		maxCacheSize: maxCacheSize,
		maxRetries:   3,
		stopCh:       make(chan struct{}),
		stats: map[string]interface{}{
			"enqueued":     int64(0),
			"processed":    int64(0),
			"failed":       int64(0),
			"retried":      int64(0),
			"discarded":    int64(0),
			"queue_full":   int64(0),
			"cache_saved":  int64(0),
			"cache_loaded": int64(0),
		},
	}
}

func (u *UploadQueue) Start() {
	if !atomic.CompareAndSwapInt32(&u.running, 0, 1) {
		return
	}

	os.MkdirAll(u.cacheDir, 0755)
	u.loadCachedTasks()

	workerCount := 3
	for i := 0; i < workerCount; i++ {
		wg := &sync.WaitGroup{}
		wg.Add(1)
		u.workers = append(u.workers, wg)
		u.wg.Add(1)
		go u.workerLoop(wg, i)
	}

	logInfo("上传队列已启动 (workers=%d, queue_size=%d)", workerCount, cap(u.queue))
}

func (u *UploadQueue) Stop() {
	if !atomic.CompareAndSwapInt32(&u.running, 1, 0) {
		return
	}

	close(u.stopCh)

	done := make(chan struct{})
	go func() {
		u.wg.Wait()
		close(done)
	}()

	select {
	case <-done:
		logInfo("上传队列已停止")
	case <-time.After(10 * time.Second):
		logWarn("上传队列停止超时")
	}
}

func (u *UploadQueue) Enqueue(task *UploadTask) bool {
	if task == nil {
		return false
	}

	queueUsage := float64(len(u.queue)) / float64(cap(u.queue))
	if queueUsage > 0.8 {
		atomic.AddInt32(&u.backpressure, 1)
	}

	select {
	case u.queue <- task:
		u.mu.Lock()
		if val, ok := u.stats["enqueued"].(int64); ok {
			u.stats["enqueued"] = val + 1
		}else{
			u.stats["enqueued"] = int64(1)
		}
		u.mu.Unlock()
		return true
	default:
		u.mu.Lock()
		if val, ok := u.stats["queue_full"].(int64); ok {
			u.stats["queue_full"] = val + 1
		}else{
			u.stats["queue_full"] = int64(1)
		}
		u.mu.Unlock()
		u.saveToCache(task)
		return false
	}
}

func (u *UploadQueue) workerLoop(wg *sync.WaitGroup, workerID int) {
	defer wg.Done()
	defer u.wg.Done()

	for {
		select {
		case task := <-u.queue:
			u.processTask(task)
		case <-u.stopCh:
			return
		}
	}
}

func (u *UploadQueue) processTask(task *UploadTask) {
	client, ok := u.client.(*MonitorClient)
	if !ok {
		logError("无法获取客户端实例")
		return
	}

	if task.EmployeeID == "" {
		logDebug("任务缺少EmployeeID，跳过: %s", task.Filename)
		return
	}

	for attempt := 0; attempt <= u.maxRetries; attempt++ {
		if attempt > 0 {
			delay := time.Duration(attempt*attempt) * time.Second
			if delay > 30*time.Second {
				delay = 30 * time.Second
			}
			u.mu.Lock()
			if val, ok := u.stats["retried"].(int64); ok {
				u.stats["retried"] = val + 1
			}else{
				u.stats["retried"] = int64(1)
			}
			u.mu.Unlock()
			time.Sleep(delay)
		}

		err := u.doUpload(client, task)
		if err == nil {
            u.mu.Lock()
            if val, ok := u.stats["processed"].(int64); ok {
                u.stats["processed"] = val + 1
            } else {
                u.stats["processed"] = int64(1)
            }
            u.mu.Unlock()
			return
		}

		logDebug("上传失败 (attempt %d/%d): %v", attempt+1, u.maxRetries+1, err)
	}

    u.mu.Lock()
    if val, ok := u.stats["failed"].(int64); ok {
        u.stats["failed"] = val + 1
    } else {
        u.stats["failed"] = int64(1)
    }
    u.mu.Unlock()
    u.saveToCache(task)
}

func (u *UploadQueue) doUpload(client *MonitorClient, task *UploadTask) error {
	if client.apiClient == nil || atomic.LoadInt32(&client.offlineMode) == 1 {
		return fmt.Errorf("offline mode")
	}

	body := &bytes.Buffer{}
	writer := multipart.NewWriter(body)

	part, err := writer.CreateFormFile("file", task.Filename)
	if err != nil {
		return err
	}
	if _, err := part.Write(task.ImageData); err != nil {
		return err
	}

	writer.WriteField("employee_id", task.EmployeeID)
	if task.ClientID != "" {
		writer.WriteField("client_id", task.ClientID)
	}
	if task.ComputerName != "" {
		writer.WriteField("computer_name", task.ComputerName)
	}
	if task.WindowsUser != "" {
		writer.WriteField("windows_user", task.WindowsUser)
	}
	if task.Timestamp != "" {
		writer.WriteField("timestamp", task.Timestamp)
	}
	writer.WriteField("encrypted", fmt.Sprintf("%v", task.Encrypted))
	writer.WriteField("format", task.Format)

	writer.Close()

	url := client.apiClient.BaseURL + "/api/upload"
	req, err := http.NewRequest("POST", url, body)
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", writer.FormDataContentType())

	client.apiClient.Session.Timeout = 30 * time.Second
	resp, err := client.apiClient.Session.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		respBody, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("HTTP %d: %s", resp.StatusCode, string(respBody))
	}

	return nil
}

func (u *UploadQueue) saveToCache(task *UploadTask) {
	if task == nil {
		return
	}

	cacheSize := u.getCacheSize()
	if cacheSize > u.maxCacheSize {
		u.mu.Lock()
		if val, ok := u.stats["discarded"].(int64); ok {
			u.stats["discarded"] = val + 1
		}
		u.mu.Unlock()
		logWarn("缓存已满(%.1fMB)，丢弃文件: %s", float64(cacheSize)/1024/1024, task.Filename)
		return
	}

	cacheFile := filepath.Join(u.cacheDir, task.Filename)
	atomicOp := &AtomicFileOperation{}
	if atomicOp.AtomicWrite(cacheFile, task.ImageData) {
		u.mu.Lock()
		if val, ok := u.stats["cache_saved"].(int64); ok {
			u.stats["cache_saved"] = val + 1
		}else{
			u.stats["cache_saved"] = int64(1)
		}
		u.mu.Unlock()
	}

}

func (u *UploadQueue) loadCachedTasks() {
	files, _ := filepath.Glob(filepath.Join(u.cacheDir, "screenshot_*"))
	count := 0

	for _, cacheFile := range files {
		atomicOp := &AtomicFileOperation{}
		data, err := atomicOp.AtomicRead(cacheFile)
		if err != nil {
			continue
		}

		baseName := filepath.Base(cacheFile)
		task := &UploadTask{
			ImageData: data,
			Filename:  baseName,
			Format:    strings.TrimPrefix(filepath.Ext(baseName), "."),
		}

		u.Enqueue(task)
		count++
		atomicOp.AtomicDelete(cacheFile)
	}

    if count > 0 {
        logInfo("从缓存加载了 %d 个任务", count)
        u.mu.Lock()
        if val, ok := u.stats["cache_loaded"].(int64); ok {
            u.stats["cache_loaded"] = val + int64(count)
        } else {
            u.stats["cache_loaded"] = int64(count)
        }
        u.mu.Unlock()
    }

}

func (u *UploadQueue) getCacheSize() int64 {
	files, _ := filepath.Glob(filepath.Join(u.cacheDir, "*"))
	var totalSize int64
	for _, file := range files {
		if info, err := os.Stat(file); err == nil && !info.IsDir() {
			totalSize += info.Size()
		}
	}
	return totalSize
}

// ========== 感知哈希 ==========
type PerceptualHash struct {
	threshold float64
	cache     map[string]string
	mu        sync.RWMutex
}

func NewPerceptualHash(threshold float64) *PerceptualHash {
	return &PerceptualHash{
		threshold: threshold,
		cache:     make(map[string]string),
	}
}

func (p *PerceptualHash) AreSimilar(img1Path, img2Path string) bool {
	info1, err1 := os.Stat(img1Path)
	info2, err2 := os.Stat(img2Path)

	if err1 != nil || err2 != nil {
		return false
	}

	size1 := info1.Size()
	size2 := info2.Size()
	if size1 > 0 && size2 > 0 {
		diff := float64(size1-size2) / float64(maxInt64(size1, size2))
		if diff > 0.3 {
			return false
		}
	}

	hash1 := p.getMD5(img1Path)
	hash2 := p.getMD5(img2Path)

	return hash1 == hash2
}

func (p *PerceptualHash) getMD5(filepath string) string {
	p.mu.RLock()
	if hash, ok := p.cache[filepath]; ok {
		p.mu.RUnlock()
		return hash
	}
	p.mu.RUnlock()

	data, err := os.ReadFile(filepath)
	if err != nil {
		return ""
	}

	hash := md5.Sum(data)
	hashStr := hex.EncodeToString(hash[:])

	p.mu.Lock()
	p.cache[filepath] = hashStr
	if len(p.cache) > 100 {
		for key := range p.cache {
			delete(p.cache, key)
			break
		}
	}
	p.mu.Unlock()

	return hashStr
}

// ========== 多显示器截图 ==========
type MultiMonitorScreenshot struct{}

func NewMultiMonitorScreenshot() *MultiMonitorScreenshot {
	return &MultiMonitorScreenshot{}
}

func (m *MultiMonitorScreenshot) CaptureAllMonitors() ([]byte, int, int, error) {
	n := screenshot.NumActiveDisplays()
	if n == 0 {
		return nil, 0, 0, fmt.Errorf("没有检测到显示器")
	}

	bounds := screenshot.GetDisplayBounds(0)

	img, err := screenshot.CaptureRect(bounds)
	if err != nil {
		return nil, 0, 0, fmt.Errorf("截图失败: %v", err)
	}

	var buf bytes.Buffer
	opts := &jpeg.Options{Quality: 80}
	if err := jpeg.Encode(&buf, img, opts); err != nil {
		return nil, 0, 0, fmt.Errorf("编码失败: %v", err)
	}

	return buf.Bytes(), bounds.Dx(), bounds.Dy(), nil
}

func (m *MultiMonitorScreenshot) CaptureDisplay(displayIndex int) ([]byte, int, int, error) {
	bounds := screenshot.GetDisplayBounds(displayIndex)
	img, err := screenshot.CaptureRect(bounds)
	if err != nil {
		return nil, 0, 0, err
	}

	var buf bytes.Buffer
	opts := &jpeg.Options{Quality: 80}
	if err := jpeg.Encode(&buf, img, opts); err != nil {
		return nil, 0, 0, err
	}

	return buf.Bytes(), bounds.Dx(), bounds.Dy(), nil
}

// ========== 错误恢复系统 ==========
type CircuitBreaker struct {
	Threshold int
	Timeout   time.Duration
	LastBreak time.Time
	Broken    bool
}

type ErrorRecoverySystem struct {
	errorCounts      map[ErrorType]int
	errorHistory     []map[string]interface{}
	circuitBreakers  map[ErrorType]*CircuitBreaker
	degradedServices map[string]bool
	mu               sync.RWMutex
	running          int32
	client           interface{}
}

func NewErrorRecoverySystem(client interface{}) *ErrorRecoverySystem {
	return &ErrorRecoverySystem{
		errorCounts: make(map[ErrorType]int),
		errorHistory: make([]map[string]interface{}, 0, 100),
		circuitBreakers: map[ErrorType]*CircuitBreaker{
			ErrorNetwork: {Threshold: 5, Timeout: 300 * time.Second},
			ErrorServer:  {Threshold: 3, Timeout: 600 * time.Second},
		},
		degradedServices: make(map[string]bool),
		client:           client,
	}
}

func (e *ErrorRecoverySystem) Start() {
	atomic.StoreInt32(&e.running, 1)
	logInfo("智能错误恢复系统已启动")
}

func (e *ErrorRecoverySystem) Stop() {
	atomic.StoreInt32(&e.running, 0)
}

func (e *ErrorRecoverySystem) ClassifyError(err error) ErrorType {
	if err == nil {
		return ErrorUnknown
	}

	errStr := strings.ToLower(err.Error())

	if strings.Contains(errStr, "connection") ||
		strings.Contains(errStr, "timeout") ||
		strings.Contains(errStr, "network") {
		return ErrorNetwork
	}

	if strings.Contains(errStr, "500") ||
		strings.Contains(errStr, "502") ||
		strings.Contains(errStr, "503") {
		return ErrorServer
	}

	if strings.Contains(errStr, "memory") ||
		strings.Contains(errStr, "disk") ||
		strings.Contains(errStr, "full") {
		return ErrorResource
	}

	if strings.Contains(errStr, "permission") ||
		strings.Contains(errStr, "no such file") {
		return ErrorLocal
	}

	return ErrorUnknown
}

func (e *ErrorRecoverySystem) ReportError(err error, component string, context map[string]interface{}) {
	if atomic.LoadInt32(&e.running) == 0 {
		return
	}

	errorType := e.ClassifyError(err)

	e.mu.Lock()
	defer e.mu.Unlock()

	e.errorCounts[errorType]++

	e.errorHistory = append(e.errorHistory, map[string]interface{}{
		"time":      time.Now().Unix(),
		"type":      string(errorType),
		"component": component,
		"error":     err.Error(),
		"context":   context,
	})

	if len(e.errorHistory) > 100 {
		e.errorHistory = e.errorHistory[1:]
	}

	e.checkCircuitBreaker(errorType)
	e.triggerRecovery(errorType, component, err)
}

func (e *ErrorRecoverySystem) checkCircuitBreaker(errorType ErrorType) {
	cb, exists := e.circuitBreakers[errorType]
	if !exists {
		return
	}

	now := time.Now()

	if cb.Broken {
		if now.Sub(cb.LastBreak) > cb.Timeout {
			cb.Broken = false
			logInfo("%s 熔断恢复", errorType)
		}
		return
	}

	recentErrors := 0
	for _, history := range e.errorHistory {
		if history["type"] == string(errorType) && time.Unix(history["time"].(int64), 0).After(now.Add(-time.Minute)) {
			recentErrors++
		}
	}

	if recentErrors >= cb.Threshold {
		cb.Broken = true
		cb.LastBreak = now
		logWarn("%s 触发熔断，暂停 %v", errorType, cb.Timeout)
	}
}

func (e *ErrorRecoverySystem) triggerRecovery(errorType ErrorType, component string, err error) {
	switch errorType {
	case ErrorNetwork:
		if !e.isCircuitBroken(ErrorNetwork) {
			logDebug("触发网络恢复")
		}
	case ErrorServer:
		if e.isCircuitBroken(ErrorServer) {
			logDebug("触发服务器切换")
		}
	case ErrorResource:
		runtime.GC()
		logDebug("触发资源清理")
	}
}

func (e *ErrorRecoverySystem) isCircuitBroken(errorType ErrorType) bool {
	cb, exists := e.circuitBreakers[errorType]
	if !exists {
		return false
	}

	if cb.Broken {
		if time.Since(cb.LastBreak) > cb.Timeout {
			cb.Broken = false
			return false
		}
		return true
	}
	return false
}

func (e *ErrorRecoverySystem) ShouldRetry(err error, retryCount int) bool {
	errorType := e.ClassifyError(err)

	if e.isCircuitBroken(errorType) {
		return false
	}

	maxRetries := map[ErrorType]int{
		ErrorNetwork:  5,
		ErrorServer:   3,
		ErrorLocal:    2,
		ErrorResource: 1,
		ErrorUnknown:  1,
	}

	return retryCount < maxRetries[errorType]
}

func (e *ErrorRecoverySystem) GetRecoveryDelay(err error, retryCount int) float64 {
	errorType := e.ClassifyError(err)

	baseDelays := map[ErrorType]float64{
		ErrorNetwork:  5,
		ErrorServer:   10,
		ErrorLocal:    2,
		ErrorResource: 30,
		ErrorUnknown:  5,
	}

	base := baseDelays[errorType]
	shift := uint(0)
	if retryCount-1 > 0 {
		shift = uint(retryCount - 1)
	}
	delay := base * float64(int(1)<<shift)

	if delay > 300 {
		delay = 300
	}
	return delay
}

func (e *ErrorRecoverySystem) GetStats() map[string]interface{} {
	e.mu.RLock()
	defer e.mu.RUnlock()

	errorCounts := make(map[string]int)
	for k, v := range e.errorCounts {
		errorCounts[string(k)] = v
	}

	circuitBreakers := make(map[string]interface{})
	for k, v := range e.circuitBreakers {
		remaining := 0.0
		if v.Broken {
			remaining = v.Timeout.Seconds() - time.Since(v.LastBreak).Seconds()
			if remaining < 0 {
				remaining = 0
			}
		}
		circuitBreakers[string(k)] = map[string]interface{}{
			"broken":    v.Broken,
			"remaining": remaining,
		}
	}

	recentErrors := make([]map[string]interface{}, 0, 10)
	for i := len(e.errorHistory) - 10; i < len(e.errorHistory); i++ {
		if i >= 0 {
			recentErrors = append(recentErrors, e.errorHistory[i])
		}
	}

	return map[string]interface{}{
		"error_counts":      errorCounts,
		"recent_errors":     recentErrors,
		"circuit_breakers":  circuitBreakers,
		"degraded_services": e.degradedServices,
	}
}

// ========== 数据安全管理器 ==========
type DataSecurityManager struct {
	encryptionEnabled bool
	client            interface{}
	hashCache         map[string]string
	mu                sync.RWMutex
}

func NewDataSecurityManager(client interface{}, encryptionEnabled bool) *DataSecurityManager {
	return &DataSecurityManager{
		encryptionEnabled: encryptionEnabled,
		client:            client,
		hashCache:         make(map[string]string),
	}
}

func (d *DataSecurityManager) EncryptData(data []byte) []byte {
	if !d.encryptionEnabled {
		return data
	}
	return []byte(base64.StdEncoding.EncodeToString(data))
}

func (d *DataSecurityManager) DecryptData(data []byte) []byte {
	if !d.encryptionEnabled {
		return data
	}
	decoded, err := base64.StdEncoding.DecodeString(string(data))
	if err != nil {
		return data
	}
	return decoded
}

func (d *DataSecurityManager) CalculateHash(data []byte, algorithm string) string {
	if algorithm == "md5" {
		hash := md5.Sum(data)
		return hex.EncodeToString(hash[:])
	}
	hash := sha256.Sum256(data)
	return hex.EncodeToString(hash[:])
}

func (d *DataSecurityManager) VerifyIntegrity(data []byte, expectedHash string) bool {
	actualHash := d.CalculateHash(data, "sha256")
	return actualHash == expectedHash
}

func (d *DataSecurityManager) SignData(data map[string]interface{}) map[string]interface{} {
	signed := make(map[string]interface{})
	for k, v := range data {
		signed[k] = v
	}

	signed["_timestamp"] = float64(time.Now().Unix())

	signStr := d.serializeMap(signed)
	hash := sha256.Sum256([]byte(signStr))
	signed["_signature"] = hex.EncodeToString(hash[:])

	return signed
}

func (d *DataSecurityManager) serializeMap(data map[string]interface{}) string {
	bytes, _ := json.Marshal(data)
	return string(bytes)
}

func (d *DataSecurityManager) MaskSensitiveData(text string, keepFirst, keepLast int) string {
	if len(text) <= keepFirst+keepLast {
		return text
	}
	return text[:keepFirst] + strings.Repeat("*", len(text)-keepFirst-keepLast) + text[len(text)-keepLast:]
}

func (d *DataSecurityManager) GetStats() map[string]interface{} {
	d.mu.RLock()
	defer d.mu.RUnlock()

	return map[string]interface{}{
		"encryption_enabled": d.encryptionEnabled,
		"hash_cache_size":    len(d.hashCache),
	}
}

// ========== 功耗管理系统 ==========
// client_operations.go - 在 PowerManager 结构体中添加缺失字段

type PowerManager struct {
    client              interface{}
    powerSavingMode     bool
    idleMode            bool
    batteryMode         bool
    baseInterval        time.Duration
    powerSavingInterval time.Duration
    idleInterval        time.Duration
    lastActivityTime    time.Time
    lastActivityMu      sync.RWMutex  // 添加锁保护
    idleThreshold       time.Duration
    stats               map[string]interface{}
    mu                  sync.RWMutex
    running             int32
    stopCh              chan struct{}
    wg                  sync.WaitGroup
}

// RecordActivity 记录用户活动（完善版）
func (p *PowerManager) RecordActivity() {
    p.lastActivityMu.Lock()
    defer p.lastActivityMu.Unlock()
    p.lastActivityTime = time.Now()
    
    if p.idleMode {
        p.lastActivityMu.Unlock()
        p.mu.Lock()
        p.idleMode = false
        if val, ok := p.stats["idle_exited"].(int); ok {
            p.stats["idle_exited"] = val + 1
        }
        p.mu.Unlock()
        p.lastActivityMu.Lock()
        logDebug("用户活动恢复，退出空闲模式")
    }
}

// IsIdle 检查是否空闲
func (p *PowerManager) IsIdle() bool {
    p.lastActivityMu.RLock()
    defer p.lastActivityMu.RUnlock()
    return time.Since(p.lastActivityTime) > p.idleThreshold
}

// GetIdleTime 获取空闲时间
func (p *PowerManager) GetIdleTime() time.Duration {
    p.lastActivityMu.RLock()
    defer p.lastActivityMu.RUnlock()
    return time.Since(p.lastActivityTime)
}

func NewPowerManager(client interface{}, baseInterval time.Duration) *PowerManager {
	return &PowerManager{
		client:              client,
		baseInterval:        baseInterval,
		powerSavingInterval: baseInterval * 2,
		idleInterval:        baseInterval * 3,
		idleThreshold:       5 * time.Minute,
		lastActivityTime:    time.Now(),
		stats: map[string]interface{}{
			"power_saving_entered": 0,
			"power_saving_exited":  0,
			"idle_entered":         0,
			"idle_exited":          0,
			"battery_mode_entered": 0,
			"battery_mode_exited":  0,
			"total_time_saved":     0,
		},
		stopCh: make(chan struct{}),
	}
}

func (p *PowerManager) Start() {
	if !atomic.CompareAndSwapInt32(&p.running, 0, 1) {
		return
	}

	p.wg.Add(1)
	go p.monitorLoop()
	logInfo("智能功耗管理系统已启动")
}

func (p *PowerManager) Stop() {
	if !atomic.CompareAndSwapInt32(&p.running, 1, 0) {
		return
	}

	close(p.stopCh)

	done := make(chan struct{})
	go func() {
		p.wg.Wait()
		close(done)
	}()

	select {
	case <-done:
		logInfo("功耗管理系统已停止")
	case <-time.After(5 * time.Second):
		logWarn("功耗管理系统停止超时")
	}
}

func (p *PowerManager) monitorLoop() {
	defer p.wg.Done()

	ticker := time.NewTicker(60 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			p.checkIdleStatus()
			p.adjustInterval()
		case <-p.stopCh:
			return
		}
	}
}

func (p *PowerManager) checkIdleStatus() {
	now := time.Now()

	wasIdle := p.idleMode
	p.idleMode = now.Sub(p.lastActivityTime) > p.idleThreshold

	if p.idleMode && !wasIdle {
		p.mu.Lock()
		if val, ok := p.stats["idle_entered"].(int); ok {
			p.stats["idle_entered"] = val + 1
		}
		p.mu.Unlock()
		logInfo("进入空闲模式")
	} else if !p.idleMode && wasIdle {
		p.mu.Lock()
		if val, ok := p.stats["idle_exited"].(int); ok {
			p.stats["idle_exited"] = val + 1
		}
		p.mu.Unlock()
		logInfo("退出空闲模式")
	}
}

func (p *PowerManager) adjustInterval() {
	// 简化实现
}

func (p *PowerManager) SetPowerSaving(enabled bool) {
	p.mu.Lock()
	defer p.mu.Unlock()

	if enabled && !p.powerSavingMode {
		if val, ok := p.stats["power_saving_entered"].(int); ok {
			p.stats["power_saving_entered"] = val + 1
		}
	} else if !enabled && p.powerSavingMode {
		if val, ok := p.stats["power_saving_exited"].(int); ok {
			p.stats["power_saving_exited"] = val + 1
		}
	}

	p.powerSavingMode = enabled
	logInfo("%s节电模式", map[bool]string{true: "启用", false: "禁用"}[enabled])
}

func (p *PowerManager) GetStats() map[string]interface{} {
	p.mu.RLock()
	defer p.mu.RUnlock()

	stats := make(map[string]interface{})
	for k, v := range p.stats {
		stats[k] = v
	}
	stats["current_interval"] = p.baseInterval.Seconds()
	stats["power_saving_mode"] = p.powerSavingMode
	stats["idle_mode"] = p.idleMode
	stats["battery_mode"] = p.batteryMode

	return stats
}

// ========== 截图管理器 ==========
type ScreenshotManager struct {
	quality             int
	format              string
	maxHistory          int
	similarityThreshold float64
	lastScreenshotPath  string
	lastScreenshotTime  *time.Time
	screenshotHistory   []string
	stats               map[string]interface{}
	mu                  sync.RWMutex
}

// client_operations.go - 在 ScreenshotManager 结构体后添加

// UpdateScreenshotTime 更新截图时间（用于频率控制）
func (s *ScreenshotManager) UpdateScreenshotTime(t time.Time) {
    s.mu.Lock()
    defer s.mu.Unlock()
    s.lastScreenshotTime = &t
}

// GetLastScreenshotTime 获取上次截图时间
func (s *ScreenshotManager) GetLastScreenshotTime() *time.Time {
    s.mu.RLock()
    defer s.mu.RUnlock()
    return s.lastScreenshotTime
}

// GetLastScreenshotPath 获取上次截图路径
func (s *ScreenshotManager) GetLastScreenshotPath() string {
    s.mu.RLock()
    defer s.mu.RUnlock()
    return s.lastScreenshotPath
}

// SetLastScreenshotPath 设置上次截图路径
func (s *ScreenshotManager) SetLastScreenshotPath(path string) {
    s.mu.Lock()
    defer s.mu.Unlock()
    s.lastScreenshotPath = path
}

// AddToHistory 添加到历史记录
func (s *ScreenshotManager) AddToHistory(filename string) {
    s.mu.Lock()
    defer s.mu.Unlock()
    
    s.screenshotHistory = append(s.screenshotHistory, filename)
    if len(s.screenshotHistory) > s.maxHistory {
        oldFile := s.screenshotHistory[0]
        s.screenshotHistory = s.screenshotHistory[1:]
        go os.Remove(oldFile) // 异步删除
    }
}

func NewScreenshotManager(quality int, format string, maxHistory int, similarityThreshold float64) *ScreenshotManager {
	if format != "webp" && format != "jpg" && format != "jpeg" {
		format = "webp"
	}

	return &ScreenshotManager{
		quality:             quality,
		format:              format,
		maxHistory:          maxHistory,
		similarityThreshold: similarityThreshold,
		screenshotHistory:   make([]string, 0),
		stats: map[string]interface{}{
			"taken":    0,
			"uploaded": 0,
			"skipped":  0,
			"failed":   0,
		},
	}
}

func (s *ScreenshotManager) TakeScreenshot() (string, error) {
	timestamp := time.Now().Format("20060102_150405")
	filename := fmt.Sprintf("screenshot_%s.%s", timestamp, s.format)

	s.mu.Lock()
	defer s.mu.Unlock()

	s.screenshotHistory = append(s.screenshotHistory, filename)
	if len(s.screenshotHistory) > s.maxHistory {
		oldFile := s.screenshotHistory[0]
		s.screenshotHistory = s.screenshotHistory[1:]
		os.Remove(oldFile)
	}

	if val, ok := s.stats["taken"].(int); ok {
		s.stats["taken"] = val + 1
	}

	return filename, nil
}

func (s *ScreenshotManager) AreSimilar(img1Path, img2Path string) bool {
	phash := NewPerceptualHash(s.similarityThreshold)
	similar := phash.AreSimilar(img1Path, img2Path)

	if similar {
		s.mu.Lock()
		if val, ok := s.stats["skipped"].(int); ok {
			s.stats["skipped"] = val + 1
		}
		s.mu.Unlock()
	}

	return similar
}

func (s *ScreenshotManager) CleanupOldScreenshots(maxAgeHours int) {
	pattern := fmt.Sprintf("screenshot_*.%s", s.format)
	files, _ := filepath.Glob(pattern)

	now := time.Now()
	count := 0
	sizeFreed := int64(0)

	for _, file := range files {
		if strings.HasPrefix(filepath.Base(file), ".tmp_") {
			continue
		}

		info, err := os.Stat(file)
		if err != nil {
			continue
		}

		if now.Sub(info.ModTime()) > time.Duration(maxAgeHours)*time.Hour {
			size := info.Size()
			if err := os.Remove(file); err == nil {
				sizeFreed += size
				count++
			}
		}
	}

	if count > 0 {
		logInfo("清理了 %d 个旧截图，释放 %.2fMB", count, float64(sizeFreed)/1024/1024)
	}
}

func (s *ScreenshotManager) GetStats() map[string]interface{} {
	s.mu.RLock()
	defer s.mu.RUnlock()

	stats := make(map[string]interface{})
	for k, v := range s.stats {
		stats[k] = v
	}
	return stats
}

// ========== MonitorClient 业务操作 ==========
func (m *MonitorClient) Start(silentMode bool) {
	logInfo("=" + strings.Repeat("=", 58))
	logInfo("员工监控系统客户端 v%s (企业版)", Version)
	logInfo("=" + strings.Repeat("=", 58))

	m.initSubsystems()
	atomic.StoreInt32(&m.running, 1)

	if m.healthMonitor != nil {
		m.healthMonitor.StartMonitoring()
	}

	if m.errorRecovery != nil {
		m.errorRecovery.Start()
	}

	if m.uploadQueue != nil {
		m.uploadQueue.Start()
	}

	if m.powerManager != nil {
		m.powerManager.Start()
	}

	if m.watchdog != nil {
		m.watchdog.Start()
	}

	logInfo("开始注册...")
	if !m.RegisterWithServer(silentMode) {
		logWarn("注册失败，将以离线模式运行")
		atomic.StoreInt32(&m.offlineMode, 1)
	}
	logInfo("注册完成，继续启动监控...")

	if m.appMonitor != nil {
		m.appMonitor.StartMonitoring()
		logInfo("软件使用监控器已启动")
	}

	if m.remoteScreen != nil {
		m.remoteScreen.UpdateIDs(m.clientID, m.employeeID)
		m.remoteScreen.Start()
		logInfo("远程屏幕服务已启动")
	}

	if m.browserMonitor != nil {
		m.browserMonitor.StartMonitoring()
		logInfo("浏览器监控器已启动")
	}

	if m.fileMonitor != nil {
		m.fileMonitor.StartMonitoring()
		logInfo("文件监控器已启动")
	}

	m.statsMu.Lock()
	m.stats["start_time"] = time.Now()
	m.statsMu.Unlock()

	m.wg.Add(1)
	go func() {
		defer m.wg.Done()
		m.workLoop()
	}()

	m.wg.Add(1)
	go func() {
		defer m.wg.Done()
		m.networkMonitor()
	}()

	if m.enableHeartbeat {
		m.wg.Add(1)
		go func() {
			defer m.wg.Done()
			m.heartbeatSender()
		}()
	}

	if m.enableBatchUpload {
		m.wg.Add(1)
		go func() {
			defer m.wg.Done()
			m.batchUploader()
		}()
	}

	logInfo("监控程序启动成功")
	logInfo("按 Ctrl+C 退出")
	logInfo("等待停止信号...")

	<-m.stopCh
	logInfo("收到停止信号，开始清理...")
	m.Stop()
}

func (m *MonitorClient) Stop() {
	logInfo("正在停止监控程序...")

	if !atomic.CompareAndSwapInt32(&m.running, 1, 0) {
		logInfo("监控程序已停止")
		return
	}

	close(m.stopCh)

	stopComponents := []func(){
		func() { if m.remoteScreen != nil { m.remoteScreen.Stop() } },
		func() { if m.appMonitor != nil { m.appMonitor.StopMonitoring() } },
		func() { if m.browserMonitor != nil { m.browserMonitor.StopMonitoring() } },
		func() { if m.fileMonitor != nil { m.fileMonitor.StopMonitoring() } },
		func() { if m.watchdog != nil { m.watchdog.Stop() } },
		func() { if m.powerManager != nil { m.powerManager.Stop() } },
		func() { if m.uploadQueue != nil { m.uploadQueue.Stop() } },
		func() { if m.healthMonitor != nil { m.healthMonitor.StopMonitoring() } },
		func() { if m.errorRecovery != nil { m.errorRecovery.Stop() } },
	}

	var wg sync.WaitGroup
	for _, stop := range stopComponents {
		wg.Add(1)
		go func(fn func()) {
			defer wg.Done()
			fn()
		}(stop)
	}

	done := make(chan struct{})
	go func() {
		wg.Wait()
		close(done)
	}()

	select {
	case <-done:
		logInfo("所有组件已停止")
	case <-time.After(10 * time.Second):
		logWarn("组件停止超时")
	}

	select {
	case <-time.After(5 * time.Second):
		logWarn("主循环退出超时")
	}

	if m.offlineMode == 0 && m.enableHeartbeat {
		m.sendHeartbeat()
	}

	m.printStats()
	logInfo("监控程序已停止")
}

func (m *MonitorClient) printStats() {
	uptime := time.Since(m.stats["start_time"].(time.Time))
	logInfo("=" + strings.Repeat("=", 58))
	logInfo("运行统计")
	logInfo("运行时间: %.2f小时", uptime.Hours())

	if val, ok := m.stats["screenshots_taken"].(int); ok {
		logInfo("截图数量: %d", val)
	}
	if val, ok := m.stats["skipped_similar"].(int); ok {
		logInfo("跳过相似: %d", val)
	}
	if val, ok := m.stats["screenshots_uploaded"].(int); ok {
		logInfo("上传成功: %d", val)
	}
	if val, ok := m.stats["upload_failures"].(int); ok {
		logInfo("上传失败: %d", val)
	}

	if m.powerManager != nil {
		powerStats := m.powerManager.GetStats()
		if totalTimeSaved, ok := powerStats["total_time_saved"].(float64); ok {
			logInfo("节电时间: %.2f小时", totalTimeSaved/3600)
		}
	}

	logInfo("=" + strings.Repeat("=", 58))
}

// client_core.go - 修改 workLoop 函数

func (m *MonitorClient) workLoop() {
    logInfo("workLoop 函数开始执行")
    logInfo("开始监控，间隔: %.0f秒", m.interval.Seconds())

    lastScreenshotTime := time.Time{}
    lastScreenshotPath := ""
    lastSyncTime := time.Time{}
    lastActivityCheck := time.Now()

    nextScreenshot := time.Now().Add(5 * time.Second)
    logInfo("第一次截图时间: %s", nextScreenshot.Format("15:04:05"))

    for {
        select {
        case <-m.stopCh:
            return
        default:
        }

        now := time.Now()

        // 每5秒记录一次活动（模拟用户活动检测）
        if now.Sub(lastActivityCheck) >= 5*time.Second {
            lastActivityCheck = now
            if m.powerManager != nil {
                // 如果有任何监控活动，视为用户活跃
                m.powerManager.RecordActivity()
            }
        }

        if m.watchdog != nil {
            m.watchdog.Heartbeat("main")
        }

        if atomic.LoadInt32(&m.paused) == 1 {
            time.Sleep(1 * time.Second)
            continue
        }

        if atomic.CompareAndSwapInt32(&m.takeScreenshotNow, 1, 0) {
            if now.Sub(lastScreenshotTime) >= 3*time.Second {
                logInfo("立即截图触发")
                path, _ := m.takeScreenshotAsync(lastScreenshotPath)
                if path != "" {
                    lastScreenshotPath = path
                    lastScreenshotTime = now
                    if m.screenshotManager != nil {
                        m.screenshotManager.SetLastScreenshotPath(path)
                        m.screenshotManager.UpdateScreenshotTime(now)
                    }
                }
            }
            nextScreenshot = now.Add(m.interval)
            time.Sleep(100 * time.Millisecond)
            continue
        }

        if now.After(nextScreenshot) || now.Equal(nextScreenshot) {
            if now.Sub(lastScreenshotTime) >= 3*time.Second {
                path, _ := m.takeScreenshotAsync(lastScreenshotPath)
                if path != "" {
                    lastScreenshotPath = path
                    lastScreenshotTime = now
                    if m.screenshotManager != nil {
                        m.screenshotManager.SetLastScreenshotPath(path)
                        m.screenshotManager.UpdateScreenshotTime(now)
                    }
                }
            }
            nextScreenshot = now.Add(m.interval)
        }

        if now.Sub(lastSyncTime) >= 10*time.Minute && atomic.LoadInt32(&m.offlineMode) == 0 && m.apiClient != nil {
            resp, err := m.apiClient.Get(fmt.Sprintf("/api/client/%s/config", m.clientID))
            if err == nil && resp != nil {
                m.updateConfigFromServer(resp)
            }
            lastSyncTime = now
        }

        time.Sleep(1 * time.Second)
    }
}

func (m *MonitorClient) takeScreenshotAsync(lastScreenshotPath string) (string, error) {
	if m.employeeID == "" {
		logDebug("takeScreenshotAsync: employeeID 为空，跳过本次采集")
		return "", nil
	}

	now := time.Now()
	if m.screenshotManager != nil && m.screenshotManager.lastScreenshotTime != nil {
		if now.Sub(*m.screenshotManager.lastScreenshotTime) < 3*time.Second {
			logDebug("截图太频繁，跳过")
			return "", nil
		}
	}

	bounds := screenshot.GetDisplayBounds(0)
	img, err := screenshot.CaptureRect(bounds)
	if err != nil {
		logError("截图失败: %v", err)
		return "", err
	}

	logDebug("截图尺寸: %dx%d", bounds.Dx(), bounds.Dy())

	var buf bytes.Buffer
	var imageData []byte

	if m.format == "webp" {
		quality := float32(m.quality)
		if quality <= 0 {
			quality = 80
		}
		err = webp.Encode(&buf, img, &webp.Options{
			Lossless: false,
			Quality:  quality,
		})
		if err != nil {
			logError("WebP编码失败: %v", err)
			return "", err
		}
		imageData = buf.Bytes()
	} else {
		quality := m.quality
		if quality <= 0 {
			quality = 80
		}
		opts := &jpeg.Options{Quality: quality}
		if err := jpeg.Encode(&buf, img, opts); err != nil {
			logError("JPEG编码失败: %v", err)
			return "", err
		}
		imageData = buf.Bytes()
	}

	logDebug("编码后大小: %d bytes", len(imageData))

	if m.remoteScreen != nil && atomic.LoadInt32(&m.remoteScreen.viewerCount) > 0 {
		seq := atomic.AddInt64(&m.remoteScreen.FrameSeq, 1)
		screenshotFrame := &Screenshot{
			Data:      imageData,
			Width:     bounds.Dx(),
			Height:    bounds.Dy(),
			Format:    m.format,
			Timestamp: now,
			FrameType: FrameFull,
			Sequence:  seq,
		}

		select {
		case m.remoteScreen.encodeQueue <- screenshotFrame:
			logDebug("远程屏幕帧已入队: 序列=%d", seq)
		default:
			atomic.AddInt64(&m.remoteScreen.framesDropped, 1)
		}
	}

	ext := m.format
	if ext == "webp" {
		ext = "webp"
	} else {
		ext = "jpg"
	}
	tempFilename := fmt.Sprintf("temp_snap_%d.%s", now.Unix(), ext)

	if err := os.WriteFile(tempFilename, imageData, 0644); err != nil {
		logError("保存临时文件失败: %v", err)
		return "", err
	}

	if lastScreenshotPath != "" {
		if _, err := os.Stat(lastScreenshotPath); err == nil {
			if m.phashDetector.AreSimilar(lastScreenshotPath, tempFilename) {
				logDebug("屏幕内容无变化，丢弃重复截图")
				os.Remove(tempFilename)

				m.statsMu.Lock()
				if val, ok := m.stats["skipped_similar"].(int); ok {
					m.stats["skipped_similar"] = val + 1
				} else {
					m.stats["skipped_similar"] = 1
				}
				m.statsMu.Unlock()
				return "", nil
			}
		}
	}

	m.statsMu.Lock()
	if val, ok := m.stats["screenshots_taken"].(int); ok {
		m.stats["screenshots_taken"] = val + 1
	} else {
		m.stats["screenshots_taken"] = 1
	}
	m.statsMu.Unlock()

	if m.healthMonitor != nil {
		m.healthMonitor.UpdateStatus("screenshot", HealthHealthy, "截图成功", nil)
	}

	finalFilename := fmt.Sprintf("screenshot_%s.%s", now.Format("20060102_150405"), ext)
	task := &UploadTask{
		ImageData:    imageData,
		Filename:     finalFilename,
		EmployeeID:   m.employeeID,
		ClientID:     m.clientID,
		Timestamp:    now.Format("2006-01-02 15:04:05"),
		ComputerName: m.systemInfo.GetComputerName(),
		WindowsUser:  m.systemInfo.GetWindowsUser(),
		Format:       m.format,
		Encrypted:    m.encryptionEnabled,
	}

	if m.uploadQueue != nil && m.uploadQueue.Enqueue(task) {
		logDebug("任务已加入上传队列: %s", finalFilename)
		os.Remove(tempFilename)

		if m.healthMonitor != nil {
			m.healthMonitor.UpdateStatus("upload", HealthHealthy, "", nil)
		}
		if m.watchdog != nil {
			m.watchdog.Heartbeat("upload")
		}
		return finalFilename, nil
	}

	logDebug("任务未加入队列，保留临时文件: %s", tempFilename)
	return tempFilename, nil
}

func (m *MonitorClient) heartbeatSender() {
	ticker := time.NewTicker(60 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			if atomic.LoadInt32(&m.offlineMode) == 0 && m.enableHeartbeat && m.apiClient != nil && m.clientID != "" {
				m.sendHeartbeat()
			}
		case <-m.stopCh:
			return
		}
	}
}

func (m *MonitorClient) sendHeartbeat() bool {
	if m.apiClient == nil || m.clientID == "" {
		return false
	}

	start := time.Now()

	stats := m.GetStats()
	queueStats := make(map[string]interface{})
	if m.uploadQueue != nil {
		queueStats = m.uploadQueue.GetStats()
	}

	healthSummary := make(map[string]interface{})
	if m.healthMonitor != nil {
		healthSummary = m.healthMonitor.GetSummary()
	}

	heartbeatData := map[string]interface{}{
		"status":         "online",
		"timestamp":      time.Now().UTC().Format(time.RFC3339),
		"client_stats":   stats,
		"queue_stats":    queueStats,
		"health_summary": healthSummary,
		"paused":         atomic.LoadInt32(&m.paused) == 1,
		"offline_mode":   atomic.LoadInt32(&m.offlineMode) == 1,
		"ip_address":     m.systemInfo.GetIPAddress(),
	}

	_, err := m.apiClient.Post(fmt.Sprintf("/api/client/%s/heartbeat", m.clientID), heartbeatData)
	if err != nil {
		logDebug("心跳失败: %v", err)
		if m.errorRecovery != nil {
			m.errorRecovery.ReportError(err, "heartbeat", nil)
		}
		if m.healthMonitor != nil {
			m.healthMonitor.UpdateStatus("heartbeat", HealthDegraded, err.Error(), nil)
		}
		return false
	}

	elapsed := time.Since(start).Milliseconds()

	m.statsMu.Lock()
	m.stats["last_heartbeat"] = time.Now().Unix()
	m.statsMu.Unlock()

	if m.healthMonitor != nil {
		m.healthMonitor.UpdateStatus("heartbeat", HealthHealthy, fmt.Sprintf("延迟: %dms", elapsed), map[string]interface{}{"response_time": float64(elapsed)})
	}

	if m.watchdog != nil {
		m.watchdog.Heartbeat("heartbeat")
	}

	logDebug("心跳成功 (%dms)", elapsed)
	return true
}

func (m *MonitorClient) networkMonitor() {
	session := &http.Client{Timeout: 10 * time.Second}
	checkInterval := 20 * time.Second
	consecutiveFailures := 0

	for {
		select {
		case <-m.stopCh:
			return
		default:
		}

		if !m.checkBasicNetwork() {
			if atomic.LoadInt32(&m.offlineMode) == 0 {
				logWarn("网络不可用")
				atomic.StoreInt32(&m.offlineMode, 1)
			}
			time.Sleep(10 * time.Second)
			continue
		}

		currentServer := m.serverURLs[m.currentServerIndex]

		resp, err := session.Get(currentServer + "/health")
		if err == nil && resp.StatusCode == 200 {
			if atomic.LoadInt32(&m.offlineMode) == 1 {
				logInfo("网络恢复")
				atomic.StoreInt32(&m.offlineMode, 0)
				go m.RegisterWithServer(true)
			}
			m.currentServer = currentServer
			consecutiveFailures = 0
			checkInterval = 20 * time.Second

			if m.apiClient != nil {
				m.apiClient.BaseURL = currentServer
			}
		} else {
			consecutiveFailures++
			logDebug("服务器检测失败: %v", err)

			if consecutiveFailures >= 3 {
				m.switchServer()
				consecutiveFailures = 0
			}
		}

		if consecutiveFailures > 0 {
			checkInterval = time.Duration(float64(checkInterval) * 1.5)
			if checkInterval > 120*time.Second {
				checkInterval = 120 * time.Second
			}
		}

		time.Sleep(minDuration(checkInterval, 60*time.Second))
	}
}

func (m *MonitorClient) checkBasicNetwork() bool {
	conn, err := net.DialTimeout("tcp", "8.8.8.8:53", 3*time.Second)
	if err != nil {
		return false
	}
	conn.Close()
	return true
}

func (m *MonitorClient) switchServer() {
	oldIndex := m.currentServerIndex
	m.currentServerIndex = (m.currentServerIndex + 1) % len(m.serverURLs)
	newServer := m.serverURLs[m.currentServerIndex]

	logInfo("切换服务器: %d → %d (%s)", oldIndex, m.currentServerIndex, newServer)

	m.currentServer = newServer
	if m.apiClient != nil {
		m.apiClient.BaseURL = newServer
	}
}

func (m *MonitorClient) batchUploader() {
	ticker := time.NewTicker(30 * time.Minute)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			if atomic.LoadInt32(&m.offlineMode) == 0 && m.enableBatchUpload {
				m.uploadScreenshotsBatch()
			}
		case <-m.stopCh:
			return
		}
	}
}

func (m *MonitorClient) uploadScreenshotsBatch() bool {
	pattern := fmt.Sprintf("screenshot_*.%s", m.format)
	files, _ := filepath.Glob(pattern)

	screenshots := make([]string, 0)
	now := time.Now()

	for _, file := range files {
		info, err := os.Stat(file)
		if err != nil {
			continue
		}
		fileAge := now.Sub(info.ModTime())
		fileSize := info.Size()

		if fileAge > 10*time.Minute && fileSize < 10*1024*1024 {
			screenshots = append(screenshots, file)
		}
	}

	if len(screenshots) == 0 {
		return false
	}

	logInfo("批量上传 %d 个截图", len(screenshots))

	deleted := 0
	for _, screenshot := range screenshots {
		if err := os.Remove(screenshot); err == nil {
			deleted++
		}
	}

	m.statsMu.Lock()
	if val, ok := m.stats["screenshots_uploaded"].(int); ok {
		m.stats["screenshots_uploaded"] = val + len(screenshots)
	} else {
		m.stats["screenshots_uploaded"] = len(screenshots)
	}
	m.stats["last_upload_time"] = time.Now().Unix()
	m.statsMu.Unlock()

	logInfo("批量上传成功 (%d/%d)", deleted, len(screenshots))
	return true
}

func (m *MonitorClient) TestMode() {
	fmt.Println("\n" + strings.Repeat("=", 60))
	fmt.Println("测试模式 - 直接创建截图文件（不注册）")
	fmt.Println(strings.Repeat("=", 60))

	m.initSubsystems()
	fmt.Println("1. 子系统初始化完成")

	if m.uploadQueue != nil {
		m.uploadQueue.Start()
		fmt.Println("2. 上传队列已启动")
	}

	m.clientID = "test_client_001"
	m.employeeID = "test_employee_001"
	m.employeeName = "测试员工"

	fmt.Printf("使用测试ID: %s\n", m.clientID)
	fmt.Println(strings.Repeat("-", 60))

	fmt.Println("3. 正在创建截图...")

	timestamp := time.Now().Format("20060102_150405")
	filename := fmt.Sprintf("test_screenshot_%s.%s", timestamp, m.format)

	content := fmt.Sprintf("Test screenshot created at %s\n", time.Now().Format("2006-01-02 15:04:05"))
	content += fmt.Sprintf("Client ID: %s\n", m.clientID)
	content += fmt.Sprintf("Employee: %s\n", m.employeeName)
	content += fmt.Sprintf("Computer: %s\n", m.systemInfo.GetComputerName())
	content += fmt.Sprintf("User: %s\n", m.systemInfo.GetWindowsUser())

	if err := os.WriteFile(filename, []byte(content), 0644); err != nil {
		fmt.Printf("❌ 创建文件失败: %v\n", err)
		return
	}

	fmt.Printf("✅ 文件创建成功: %s\n", filename)
	if info, err := os.Stat(filename); err == nil {
		fmt.Printf("   文件大小: %d bytes\n", info.Size())
		fmt.Printf("   创建时间: %s\n", info.ModTime().Format("2006-01-02 15:04:05"))
	}

	task := &UploadTask{
		ImageData:    []byte(content),
		Filename:     filename,
		EmployeeID:   m.employeeID,
		ClientID:     m.clientID,
		Timestamp:    time.Now().Format("2006-01-02 15:04:05"),
		ComputerName: m.systemInfo.GetComputerName(),
		WindowsUser:  m.systemInfo.GetWindowsUser(),
		Format:       m.format,
		Encrypted:    m.encryptionEnabled,
	}

	if m.uploadQueue != nil && m.uploadQueue.Enqueue(task) {
		fmt.Println("✅ 任务已加入上传队列")
	} else {
		fmt.Println("⚠️ 任务未加入队列，文件已保留")
	}

	fmt.Println("\n等待上传处理...")
	time.Sleep(2 * time.Second)

	fmt.Println("\n" + strings.Repeat("=", 60))
	fmt.Println("测试完成！")
}

func (m *MonitorClient) QuickTest() {
	fmt.Println("\n" + strings.Repeat("=", 60))
	fmt.Println("快速测试 - 直接创建测试文件")
	fmt.Println(strings.Repeat("=", 60))

	m.initSubsystems()

	if m.clientID == "" {
		m.clientID = "test_client_001"
	}
	if m.employeeID == "" {
		m.employeeID = "test_employee_001"
	}
	if m.employeeName == "" {
		m.employeeName = "测试员工"
	}

	fmt.Printf("使用测试ID: %s\n", m.clientID)
	fmt.Printf("使用员工: %s\n", m.employeeName)

	timestamp := time.Now().Format("20060102_150405")
	filename := fmt.Sprintf("test_screenshot_%s.%s", timestamp, m.format)

	fmt.Printf("\n正在创建测试文件: %s\n", filename)

	content := fmt.Sprintf("Test screenshot created at %s\n", time.Now().Format("2006-01-02 15:04:05"))
	content += fmt.Sprintf("Client ID: %s\n", m.clientID)
	content += fmt.Sprintf("Employee: %s\n", m.employeeName)
	content += fmt.Sprintf("Computer: %s\n", m.systemInfo.GetComputerName())
	content += fmt.Sprintf("User: %s\n", m.systemInfo.GetWindowsUser())
	content += strings.Repeat("=", 50) + "\n"
	content += "This is a test file created by the monitoring client.\n"

	if err := os.WriteFile(filename, []byte(content), 0644); err != nil {
		fmt.Printf("❌ 创建文件失败: %v\n", err)
		return
	}

	fmt.Printf("✅ 文件创建成功: %s\n", filename)

	if info, err := os.Stat(filename); err == nil {
		fmt.Printf("   文件大小: %d bytes\n", info.Size())
		fmt.Printf("   创建时间: %s\n", info.ModTime().Format("2006-01-02 15:04:05"))
	}

	fmt.Println("\n当前目录的测试文件:")
	files, _ := filepath.Glob("test_*")
	for _, f := range files {
		if info, err := os.Stat(f); err == nil {
			fmt.Printf("  - %s (%d bytes)\n", f, info.Size())
		}
	}

	fmt.Println("\n" + strings.Repeat("=", 60))
	fmt.Println("测试完成！文件已创建在当前目录")
}

func maxInt64(a, b int64) int64 {
	if a > b {
		return a
	}
	return b
}