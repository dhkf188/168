// client_recovery.go - 增强崩溃恢复
package main

import (
	"runtime/debug"
	"sync"
	"time"
)

type CrashRecovery struct {
    components     map[string]*ComponentRecovery
    mu             sync.RWMutex
    globalRecovery func(interface{})
}

type ComponentRecovery struct {
    Name           string
    LastPanic      time.Time
    PanicCount     int
    RecoveryFunc   func()
    CooldownPeriod time.Duration
    MaxPanics      int
}

func NewCrashRecovery(globalRecovery func(interface{})) *CrashRecovery {
    return &CrashRecovery{
        components:     make(map[string]*ComponentRecovery),
        globalRecovery: globalRecovery,
    }
}

func (c *CrashRecovery) RegisterComponent(name string, recoveryFunc func(), cooldown time.Duration) {
    c.mu.Lock()
    defer c.mu.Unlock()
    
    c.components[name] = &ComponentRecovery{
        Name:           name,
        RecoveryFunc:   recoveryFunc,
        CooldownPeriod: cooldown,
        MaxPanics:      5,
    }
}

func (c *CrashRecovery) Wrap(name string, fn func()) {
    defer func() {
        if r := recover(); r != nil {
            c.handlePanic(name, r)
        }
    }()
    fn()
}

func (c *CrashRecovery) handlePanic(name string, panicValue interface{}) {
    stack := debug.Stack()
    logError("组件 %s 发生崩溃: %v\n堆栈:\n%s", name, panicValue, string(stack))
    
    c.mu.Lock()
    recovery, exists := c.components[name]
    c.mu.Unlock()
    
    if !exists {
        if c.globalRecovery != nil {
            c.globalRecovery(panicValue)
        }
        return
    }
    
    recovery.PanicCount++
    recovery.LastPanic = time.Now()
    
    if recovery.PanicCount >= recovery.MaxPanics {
        logError("组件 %s 崩溃次数过多 (%d), 停止恢复", name, recovery.PanicCount)
        return
    }
    
    // 指数退避恢复
    delay := time.Duration(1<<uint(recovery.PanicCount-1)) * time.Second
    if delay > 30*time.Second {
        delay = 30 * time.Second
    }
    
    logInfo("将在 %v 后尝试恢复组件: %s", delay, name)
    time.AfterFunc(delay, recovery.RecoveryFunc)
}