// client_disk.go - 完整修复版
//go:build windows
// +build windows

package main

import (
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"golang.org/x/sys/windows"
)

// DiskMonitor 磁盘监控器
type DiskMonitor struct {
    cacheDir        string
    warningLevel    int64  // MB
    criticalLevel   int64  // MB
    mu              sync.RWMutex
    lastCheck       time.Time
    onWarning       func(int64)
    onCritical      func(int64)
    running         bool
    stopCh          chan struct{}
}

// NewDiskMonitor 创建磁盘监控器
func NewDiskMonitor(cacheDir string, warningMB, criticalMB int64) *DiskMonitor {
    return &DiskMonitor{
        cacheDir:      cacheDir,
        warningLevel:  warningMB,
        criticalLevel: criticalMB,
        stopCh:        make(chan struct{}),
    }
}

// GetFreeSpace 获取指定路径的剩余空间（MB）
func (d *DiskMonitor) GetFreeSpace() (int64, error) {
    var freeBytesAvailable, totalBytes, totalFreeBytes uint64
    
    // 获取当前目录所在磁盘
    path, err := os.Getwd()
    if err != nil {
        path = d.cacheDir
        if path == "" {
            path = "."
        }
    }
    
    err = windows.GetDiskFreeSpaceEx(windows.StringToUTF16Ptr(path), 
        &freeBytesAvailable, &totalBytes, &totalFreeBytes)
    if err != nil {
        return 0, err
    }
    
    return int64(freeBytesAvailable / 1024 / 1024), nil
}

// GetCacheSize 获取缓存目录大小（MB）
func (d *DiskMonitor) GetCacheSize() (int64, error) {
    var totalSize int64
    
    if d.cacheDir == "" {
        return 0, nil
    }
    
    err := filepath.Walk(d.cacheDir, func(path string, info os.FileInfo, err error) error {
        if err != nil {
            return nil
        }
        if !info.IsDir() && !strings.HasPrefix(filepath.Base(path), ".tmp_") {
            totalSize += info.Size()
        }
        return nil
    })
    
    return totalSize / 1024 / 1024, err
}

// StartMonitoring 启动磁盘监控
func (d *DiskMonitor) StartMonitoring(interval time.Duration) {
    d.mu.Lock()
    if d.running {
        d.mu.Unlock()
        return
    }
    d.running = true
    d.mu.Unlock()
    
    go func() {
        ticker := time.NewTicker(interval)
        defer ticker.Stop()
        
        for {
            select {
            case <-ticker.C:
                d.check()
            case <-d.stopCh:
                return
            }
        }
    }()
}

// StopMonitoring 停止磁盘监控
func (d *DiskMonitor) StopMonitoring() {
    d.mu.Lock()
    defer d.mu.Unlock()
    
    if !d.running {
        return
    }
    d.running = false
    close(d.stopCh)
}

// check 检查磁盘空间
func (d *DiskMonitor) check() {
    freeMB, err := d.GetFreeSpace()
    if err != nil {
        return
    }
    
    // 检查严重阈值
    if freeMB < d.criticalLevel && d.onCritical != nil {
        d.onCritical(freeMB)
        return
    }
    
    // 检查警告阈值
    if freeMB < d.warningLevel && d.onWarning != nil {
        d.onWarning(freeMB)
    }
}

// emergencyCleanup 紧急清理
func (d *DiskMonitor) emergencyCleanup() {
    if d.cacheDir == "" {
        return
    }
    
    // 删除最旧的缓存文件
    files, err := filepath.Glob(filepath.Join(d.cacheDir, "*.json"))
    if err != nil {
        return
    }
    
    // 收集文件信息
    type fileInfo struct {
        path string
        mod  time.Time
    }
    var fileList []fileInfo
    
    for _, f := range files {
        info, err := os.Stat(f)
        if err != nil {
            continue
        }
        fileList = append(fileList, fileInfo{f, info.ModTime()})
    }
    
    // 按修改时间排序（冒泡排序）
    for i := 0; i < len(fileList)-1; i++ {
        for j := i + 1; j < len(fileList); j++ {
            if fileList[i].mod.After(fileList[j].mod) {
                fileList[i], fileList[j] = fileList[j], fileList[i]
            }
        }
    }
    
    // 删除30%的最旧文件
    deleteCount := len(fileList) * 30 / 100
    if deleteCount < 1 {
        deleteCount = 1
    }
    if deleteCount > len(fileList) {
        deleteCount = len(fileList)
    }
    
    for i := 0; i < deleteCount; i++ {
        os.Remove(fileList[i].path)
    }
}