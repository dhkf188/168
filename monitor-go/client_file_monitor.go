// client_file_monitor.go - 文件监控器（实时采集版）
package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

// FileOperation 文件操作记录
type FileOperation struct {
	Operation     string    `json:"operation"`      // create, modify, delete
	FilePath      string    `json:"file_path"`
	FileName      string    `json:"file_name"`
	FileType      string    `json:"file_type"`
	FileSize      int64     `json:"file_size"`
	IsDirectory   bool      `json:"is_directory"`
	OperationTime time.Time `json:"operation_time"`
	EmployeeID    string    `json:"employee_id"`
	ClientID      string    `json:"client_id"`
}

// FileMonitor 文件监控器
type FileMonitor struct {
	client           *MonitorClient
	watchDirs        []string
	ignoreDirs       []string
	ignoreExtensions []string
	reportInterval   time.Duration
	lastReportTime   time.Time
	running          int32
	mu               sync.RWMutex
	stopCh           chan struct{}
	wg               sync.WaitGroup

	// 目录快照
	snapshots  map[string]*DirSnapshot
	snapshotMu sync.RWMutex

	// 待上报的操作记录
	pendingOperations []FileOperation
	maxPendingSize    int
}

// DirSnapshot 目录快照
type DirSnapshot struct {
	Files map[string]FileInfo
	Time  time.Time
}

// FileInfo 文件信息
type FileInfo struct {
	Name    string
	Size    int64
	ModTime time.Time
	IsDir   bool
}

// NewFileMonitor 创建文件监控器
func NewFileMonitor(client *MonitorClient) *FileMonitor {
	userHome, _ := os.UserHomeDir()

	watchDirs := []string{
		filepath.Join(userHome, "Desktop"),
		filepath.Join(userHome, "Documents"),
		filepath.Join(userHome, "Downloads"),
		filepath.Join(userHome, "Pictures"),
		filepath.Join(userHome, "Videos"),
		filepath.Join(userHome, "Music"),
	}

	existingDirs := make([]string, 0)
	for _, dir := range watchDirs {
		if info, err := os.Stat(dir); err == nil && info.IsDir() {
			existingDirs = append(existingDirs, dir)
		}
	}

	return &FileMonitor{
		client: client,
		watchDirs: existingDirs,
		ignoreDirs: []string{
			filepath.Join(userHome, "AppData"),
			filepath.Join(userHome, "Application Data"),
			filepath.Join(userHome, "Local Settings"),
			filepath.Join(userHome, "Cookies"),
			filepath.Join(userHome, "Cache"),
			filepath.Join(userHome, "Temp"),
		},
		ignoreExtensions: []string{".tmp", ".temp", ".log", ".cache", ".bak", ".lnk", ".lock"},
		reportInterval:   120 * time.Second, // 2分钟上报一次
		stopCh:           make(chan struct{}),
		snapshots:        make(map[string]*DirSnapshot),
		pendingOperations: make([]FileOperation, 0, 1000),
		maxPendingSize:   10000,
	}
}

// StartMonitoring 启动文件监控
func (f *FileMonitor) StartMonitoring() {
	if !atomic.CompareAndSwapInt32(&f.running, 0, 1) {
		return
	}

	logInfo("📁 [文件] 文件监控器启动 [上报间隔: %v, 实时扫描模式]", f.reportInterval)
	
	// 初始化快照
	f.takeInitialSnapshot()
	
	f.wg.Add(1)
	go f.monitorLoop()
}

// StopMonitoring 停止文件监控
func (f *FileMonitor) StopMonitoring() {
	if !atomic.CompareAndSwapInt32(&f.running, 1, 0) {
		return
	}

	logInfo("📁 [文件] 文件监控器停止中...")
	close(f.stopCh)

	// 保存所有未上报的操作
	f.flushPendingOperations()

	done := make(chan struct{})
	go func() {
		f.wg.Wait()
		close(done)
	}()

	select {
	case <-done:
		logInfo("📁 [文件] 文件监控器已停止")
	case <-time.After(5 * time.Second):
		logWarn("📁 [文件] 文件监控器停止超时")
	}
}

// flushPendingOperations 刷新所有待上报操作（停止时调用）
func (f *FileMonitor) flushPendingOperations() {
	f.mu.Lock()
	defer f.mu.Unlock()

	if len(f.pendingOperations) > 0 {
		logInfo("📁 [文件] 停止时保存 %d 条待上报操作", len(f.pendingOperations))
		f.saveBatchToCache(f.pendingOperations)
		f.pendingOperations = f.pendingOperations[:0]
	}
}

func (f *FileMonitor) monitorLoop() {
	defer f.wg.Done()

	logInfo("📁 [文件] 文件监控循环已启动")
	ticker := time.NewTicker(10 * time.Second) // 每10秒扫描一次变化
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			if atomic.LoadInt32(&f.client.running) == 0 {
				return
			}
			f.scanForChanges()
			f.collectAndReport()
		case <-f.stopCh:
			return
		}
	}
}

// takeInitialSnapshot 拍摄初始快照
func (f *FileMonitor) takeInitialSnapshot() {
	for _, dir := range f.watchDirs {
		snapshot := f.scanDirectory(dir)
		if snapshot != nil {
			f.snapshotMu.Lock()
			f.snapshots[dir] = snapshot
			f.snapshotMu.Unlock()
			logDebug("📁 [文件] 已拍摄初始快照: %s (%d 个文件)", dir, len(snapshot.Files))
		}
	}
}

// scanForChanges 扫描目录变化
func (f *FileMonitor) scanForChanges() {
	for _, dir := range f.watchDirs {
		f.scanDirectoryChanges(dir)
	}
}

// scanDirectory 扫描目录
func (f *FileMonitor) scanDirectory(dir string) *DirSnapshot {
	snapshot := &DirSnapshot{
		Files: make(map[string]FileInfo),
		Time:  time.Now(),
	}

	err := filepath.Walk(dir, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return nil
		}

		if f.shouldIgnore(path) {
			if info.IsDir() {
				return filepath.SkipDir
			}
			return nil
		}

		relPath, _ := filepath.Rel(dir, path)
		snapshot.Files[relPath] = FileInfo{
			Name:    info.Name(),
			Size:    info.Size(),
			ModTime: info.ModTime(),
			IsDir:   info.IsDir(),
		}

		return nil
	})

	if err != nil {
		logDebug("📁 [文件] 扫描目录失败 %s: %v", dir, err)
		return nil
	}

	return snapshot
}

// scanDirectoryChanges 扫描目录变化并记录
func (f *FileMonitor) scanDirectoryChanges(dir string) {
	f.snapshotMu.RLock()
	oldSnapshot, exists := f.snapshots[dir]
	f.snapshotMu.RUnlock()

	if !exists {
		return
	}

	newSnapshot := f.scanDirectory(dir)
	if newSnapshot == nil {
		return
	}

	operations := make([]FileOperation, 0)

	// 检测新增和修改的文件
	for path, newFile := range newSnapshot.Files {
		if newFile.IsDir {
			continue
		}

		if oldFile, ok := oldSnapshot.Files[path]; ok {
			// 检查是否修改（修改时间变化或大小变化）
			if !oldFile.ModTime.Equal(newFile.ModTime) || oldFile.Size != newFile.Size {
				operations = append(operations, FileOperation{
					Operation:     "modify",
					FilePath:      filepath.Join(dir, path),
					FileName:      newFile.Name,
					FileType:      filepath.Ext(newFile.Name),
					FileSize:      newFile.Size,
					IsDirectory:   false,
					OperationTime: time.Now(),
				})
				logDebug("📁 [文件] 检测到修改: %s", filepath.Join(dir, path))
			}
		} else {
			// 新增文件
			operations = append(operations, FileOperation{
				Operation:     "create",
				FilePath:      filepath.Join(dir, path),
				FileName:      newFile.Name,
				FileType:      filepath.Ext(newFile.Name),
				FileSize:      newFile.Size,
				IsDirectory:   false,
				OperationTime: time.Now(),
			})
			logDebug("📁 [文件] 检测到新增: %s", filepath.Join(dir, path))
		}
	}

	// 检测删除的文件
	for path, oldFile := range oldSnapshot.Files {
		if oldFile.IsDir {
			continue
		}
		if _, ok := newSnapshot.Files[path]; !ok {
			operations = append(operations, FileOperation{
				Operation:     "delete",
				FilePath:      filepath.Join(dir, path),
				FileName:      oldFile.Name,
				FileType:      filepath.Ext(oldFile.Name),
				FileSize:      oldFile.Size,
				IsDirectory:   false,
				OperationTime: time.Now(),
			})
			logDebug("📁 [文件] 检测到删除: %s", filepath.Join(dir, path))
		}
	}

	// 保存检测到的操作
	if len(operations) > 0 {
		f.mu.Lock()
		for _, op := range operations {
			if len(f.pendingOperations) < f.maxPendingSize {
				f.pendingOperations = append(f.pendingOperations, op)
			} else {
				logWarn("📁 [文件] 待上报队列已满，丢弃操作: %s", op.FilePath)
			}
		}
		f.mu.Unlock()
	}

	// 更新快照
	f.snapshotMu.Lock()
	f.snapshots[dir] = newSnapshot
	f.snapshotMu.Unlock()
}

// shouldIgnore 判断是否应该忽略
func (f *FileMonitor) shouldIgnore(path string) bool {
	pathLower := strings.ToLower(path)

	// 检查忽略目录
	for _, ignoreDir := range f.ignoreDirs {
		if strings.HasPrefix(pathLower, strings.ToLower(ignoreDir)) {
			return true
		}
	}

	// 检查忽略扩展名
	for _, ext := range f.ignoreExtensions {
		if strings.HasSuffix(pathLower, ext) {
			return true
		}
	}

	// 检查隐藏文件
	baseName := filepath.Base(path)
	if strings.HasPrefix(baseName, ".") || strings.HasPrefix(baseName, "~") {
		return true
	}

	// 检查空文件
	if info, err := os.Stat(path); err == nil && info.Size() == 0 {
		return true
	}

	return false
}

// collectAndReport 收集并上报文件操作
func (f *FileMonitor) collectAndReport() {
	currentTime := time.Now()

	// 检查上报间隔
	if currentTime.Sub(f.lastReportTime) < f.reportInterval {
		return
	}

	if f.client.employeeID == "" {
		logDebug("📁 [文件] 上报: employeeID未就绪，跳过")
		return
	}

	logDebug("📁 [文件] 📊 开始收集文件操作数据...")

	f.mu.Lock()
	if len(f.pendingOperations) == 0 {
		f.mu.Unlock()
		logDebug("📁 [文件] 没有文件操作需要上报")
		f.lastReportTime = currentTime
		return
	}

	operations := make([]FileOperation, len(f.pendingOperations))
	copy(operations, f.pendingOperations)
	f.pendingOperations = f.pendingOperations[:0]
	f.mu.Unlock()

	// 过滤有效操作
	validOperations := make([]FileOperation, 0, len(operations))
	for _, op := range operations {
		// 跳过目录操作
		if op.IsDirectory {
			continue
		}

		// 对于非删除操作，验证文件是否存在且大小>0
		if op.Operation != "delete" {
			if info, err := os.Stat(op.FilePath); err == nil {
				op.FileSize = info.Size()
				if op.FileSize == 0 {
					logDebug("📁 [文件] 跳过空文件: %s", op.FilePath)
					continue
				}
			} else {
				// 文件可能已被删除，跳过
				continue
			}
		}

		// 补全ID信息
		op.EmployeeID = f.client.employeeID
		op.ClientID = f.client.clientID
		validOperations = append(validOperations, op)
	}

	if len(validOperations) == 0 {
		logDebug("📁 [文件] 过滤后无有效文件操作")
		f.lastReportTime = currentTime
		return
	}

	logDebug("📁 [文件] 收集到 %d 条文件操作", len(validOperations))

	// 打印所有操作
	for i, op := range validOperations {
		logDebug("📁 [文件]   %d. [%s] %s (大小: %d bytes, 时间: %s)",
			i+1, op.Operation, op.FileName, op.FileSize,
			op.OperationTime.Format("15:04:05"))
	}

	// 上报所有操作
	if len(validOperations) > 0 {
		f.uploadOperationsLocked(validOperations, currentTime)
	} else {
		f.lastReportTime = currentTime
	}
}

// uploadOperationsLocked 上传文件操作记录
func (f *FileMonitor) uploadOperationsLocked(operations []FileOperation, currentTime time.Time) {
	if f.client.offlineMode != 0 {
		logInfo("📁 [文件] 离线模式，文件操作已缓存")
		f.saveBatchToCache(operations)
		return
	}

	if f.client.apiClient == nil {
		logError("📁 [文件] API客户端未初始化")
		f.saveBatchToCache(operations)
		return
	}

	logInfo("📁 [文件] 📤 上报文件操作: %d条", len(operations))

	batchSize := 100
	successCount := 0

	for i := 0; i < len(operations); i += batchSize {
		end := i + batchSize
		if end > len(operations) {
			end = len(operations)
		}

		batch := operations[i:end]

		// 转换为map格式用于上报
		serializable := make([]map[string]interface{}, len(batch))
		for j, op := range batch {
			serializable[j] = map[string]interface{}{
				"employee_id":    op.EmployeeID,
				"client_id":      op.ClientID,
				"operation":      op.Operation,
				"file_path":      op.FilePath,
				"file_name":      op.FileName,
				"file_type":      op.FileType,
				"file_size":      op.FileSize,
				"is_directory":   op.IsDirectory,
				"operation_time": op.OperationTime.Format(time.RFC3339),
			}
		}

		// 添加重试逻辑
		var err error
		for retry := 0; retry < 3; retry++ {
			if retry > 0 {
				logDebug("📁 [文件] 重试上报批次 %d-%d (%d/3)", i, end, retry+1)
				time.Sleep(time.Duration(retry) * time.Second)
			}

			_, err = f.client.apiClient.Post("/api/files/operations", serializable)
			if err == nil {
				break
			}
			logDebug("📁 [文件] 上报失败: %v", err)
		}

		if err != nil {
			logError("📁 [文件] 上报文件操作批次失败: %v", err)
			f.saveBatchToCache(batch)
		} else {
			logInfo("📁 [文件] ✅ 文件操作上报成功: %d条 (批次 %d-%d)", len(batch), i, end)
			successCount += len(batch)
		}
	}

	if successCount > 0 {
		f.lastReportTime = currentTime
	}
}

// saveBatchToCache 保存批次到缓存
func (f *FileMonitor) saveBatchToCache(operations []FileOperation) {
	cacheDir := "cache"
	os.MkdirAll(cacheDir, 0755)

	cacheFile := filepath.Join(cacheDir, fmt.Sprintf("files_%d.json", time.Now().UnixNano()))
	jsonData, err := json.Marshal(operations)
	if err != nil {
		logError("📁 [文件] 序列化失败: %v", err)
		return
	}

	if err := os.WriteFile(cacheFile, jsonData, 0644); err != nil {
		logError("📁 [文件] 保存缓存文件失败: %v", err)
	} else {
		logDebug("📁 [文件] 缓存 %d 条操作到 %s", len(operations), filepath.Base(cacheFile))
	}
}

// 以下方法保留以兼容外部调用，但在实时扫描模式下不再使用
// OnFileCreated 文件创建事件（外部调用）
func (f *FileMonitor) OnFileCreated(filePath string) {
	// 实时扫描模式已自动检测，此方法保留用于兼容
}

// OnFileModified 文件修改事件（外部调用）
func (f *FileMonitor) OnFileModified(filePath string) {
	// 实时扫描模式已自动检测，此方法保留用于兼容
}

// OnFileDeleted 文件删除事件（外部调用）
func (f *FileMonitor) OnFileDeleted(filePath string) {
	// 实时扫描模式已自动检测，此方法保留用于兼容
}