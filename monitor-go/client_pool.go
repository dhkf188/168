// client_pool.go - 连接池管理
package main

import (
	"sync"
	"time"
)

type PooledConnection struct {
    Conn       interface{}
    LastUsed   time.Time
    InUse      bool
    CreatedAt  time.Time
    IdleCount  int
}

type ConnectionPool struct {
    mu           sync.RWMutex
    pool         map[string]*PooledConnection
    maxSize      int
    idleTimeout  time.Duration
    maxLifetime  time.Duration
    cleanupTick  *time.Ticker
    stopCh       chan struct{}
}

func NewConnectionPool(maxSize int, idleTimeout, maxLifetime time.Duration) *ConnectionPool {
    p := &ConnectionPool{
        pool:        make(map[string]*PooledConnection),
        maxSize:     maxSize,
        idleTimeout: idleTimeout,
        maxLifetime: maxLifetime,
        stopCh:      make(chan struct{}),
    }
    
    p.startCleanup()
    return p
}

func (p *ConnectionPool) startCleanup() {
    p.cleanupTick = time.NewTicker(30 * time.Second)
    go func() {
        for {
            select {
            case <-p.cleanupTick.C:
                p.cleanup()
            case <-p.stopCh:
                p.cleanupTick.Stop()
                return
            }
        }
    }()
}

func (p *ConnectionPool) cleanup() {
    p.mu.Lock()
    defer p.mu.Unlock()
    
    now := time.Now()
    for key, conn := range p.pool {
        if conn.InUse {
            continue
        }
        
        // 清理空闲超时的连接
        if now.Sub(conn.LastUsed) > p.idleTimeout {
            p.closeConnection(conn)
            delete(p.pool, key)
            continue
        }
        
        // 清理生命周期超时的连接
        if now.Sub(conn.CreatedAt) > p.maxLifetime {
            p.closeConnection(conn)
            delete(p.pool, key)
        }
    }
}

func (p *ConnectionPool) closeConnection(conn *PooledConnection) {
    // 实际关闭逻辑由具体连接类型实现
}