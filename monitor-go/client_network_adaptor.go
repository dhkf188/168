// client_network_adaptor.go - 完整版

package main

import (
	"sync"
	"sync/atomic"
	"time"
)

type NetworkAdaptor struct {
    mu                  sync.RWMutex
    quality             int32
    lastRTT             int64
    lastBandwidth       int64
    consecutiveFailures int32
    lastAdjustTime      time.Time
    
    // 配置
    minQuality      int32
    maxQuality      int32
    adjustInterval  time.Duration
    qualityStep     int32
    rttThreshold    int64
    enabled         bool
}

func NewNetworkAdaptor() *NetworkAdaptor {
    return &NetworkAdaptor{
        quality:        80,
        minQuality:     20,
        maxQuality:     100,
        adjustInterval: 30 * time.Second,
        qualityStep:    10,
        rttThreshold:   500,
        enabled:        true,
    }
}

func (n *NetworkAdaptor) RecordResponse(rttMs int64, success bool) {
    if !n.enabled {
        return
    }
    atomic.StoreInt64(&n.lastRTT, rttMs)
    
    if !success {
        atomic.AddInt32(&n.consecutiveFailures, 1)
    } else {
        atomic.StoreInt32(&n.consecutiveFailures, 0)
    }
}

func (n *NetworkAdaptor) GetAdjustedQuality() int {
    if !n.enabled {
        return int(atomic.LoadInt32(&n.quality))
    }
    
    n.mu.Lock()
    defer n.mu.Unlock()
    
    now := time.Now()
    if now.Sub(n.lastAdjustTime) < n.adjustInterval {
        return int(atomic.LoadInt32(&n.quality))
    }
    n.lastAdjustTime = now
    
    rtt := atomic.LoadInt64(&n.lastRTT)
    failures := atomic.LoadInt32(&n.consecutiveFailures)
    quality := atomic.LoadInt32(&n.quality)
    
    // 根据RTT调整质量
    if rtt > n.rttThreshold*2 {
        quality = maxInt32(n.minQuality, quality-n.qualityStep*2)
    } else if rtt > n.rttThreshold {
        quality = maxInt32(n.minQuality, quality-n.qualityStep)
    } else if rtt < 100 && quality < n.maxQuality {
        quality = minInt32(n.maxQuality, quality+n.qualityStep/2)
    }
    
    // 根据失败次数调整
    if failures > 3 {
        quality = maxInt32(n.minQuality, quality-n.qualityStep)
    } else if failures == 0 && quality < n.maxQuality {
        quality = minInt32(n.maxQuality, quality+n.qualityStep/4)
    }
    
    atomic.StoreInt32(&n.quality, quality)
    return int(quality)
}

func (n *NetworkAdaptor) GetCurrentQuality() int {
    return int(atomic.LoadInt32(&n.quality))
}

func (n *NetworkAdaptor) SetEnabled(enabled bool) {
    n.enabled = enabled
}

func (n *NetworkAdaptor) IsEnabled() bool {
    return n.enabled
}

func (n *NetworkAdaptor) GetStats() map[string]interface{} {
    return map[string]interface{}{
        "quality":              atomic.LoadInt32(&n.quality),
        "last_rtt":             atomic.LoadInt64(&n.lastRTT),
        "consecutive_failures": atomic.LoadInt32(&n.consecutiveFailures),
        "enabled":              n.enabled,
        "min_quality":          n.minQuality,
        "max_quality":          n.maxQuality,
    }
}

func minInt32(a, b int32) int32 {
    if a < b {
        return a
    }
    return b
}

func maxInt32(a, b int32) int32 {
    if a > b {
        return a
    }
    return b
}