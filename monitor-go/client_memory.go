// client_memory.go - 内存限制器
package main

import (
	"runtime"
	"sync"
	"time"
)

type MemoryLimiter struct {
    maxMemoryMB   int64
    currentUsage  int64
    mu            sync.RWMutex
    gcThreshold   float64
    lastGCTime    time.Time
}

func NewMemoryLimiter(maxMemoryMB int64) *MemoryLimiter {
    return &MemoryLimiter{
        maxMemoryMB: maxMemoryMB,
        gcThreshold: 0.8, // 80%触发GC
    }
}

func (m *MemoryLimiter) CheckAndGC() {
    m.mu.RLock()
    usage := m.currentUsage
    m.mu.RUnlock()
    
    if usage > int64(float64(m.maxMemoryMB)*m.gcThreshold) {
        m.TriggerGC()
    }
}

func (m *MemoryLimiter) TriggerGC() {
    m.mu.Lock()
    defer m.mu.Unlock()
    
    if time.Since(m.lastGCTime) < 30*time.Second {
        return
    }
    
    runtime.GC()
    m.lastGCTime = time.Now()
    
    var memStats runtime.MemStats
    runtime.ReadMemStats(&memStats)
    m.currentUsage = int64(memStats.Alloc / 1024 / 1024)
    
    logInfo("内存限制器: 触发GC, 当前使用 %d MB", m.currentUsage)
}

func (m *MemoryLimiter) CanAllocate(sizeMB int64) bool {
    m.mu.RLock()
    defer m.mu.RUnlock()
    return m.currentUsage+sizeMB < m.maxMemoryMB
}

func (m *MemoryLimiter) UpdateUsage() {
    var memStats runtime.MemStats
    runtime.ReadMemStats(&memStats)
    
    m.mu.Lock()
    m.currentUsage = int64(memStats.Alloc / 1024 / 1024)
    m.mu.Unlock()
}