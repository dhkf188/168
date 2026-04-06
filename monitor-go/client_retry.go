// client_retry.go - 智能重试器
package main

import (
	"math/rand"
	"time"
)

type RetryStrategy int

const (
    RetryFixed RetryStrategy = iota
    RetryLinear
    RetryExponential
    RetryExponentialWithJitter
)

type RetryConfig struct {
    MaxAttempts      int
    InitialDelay     time.Duration
    MaxDelay         time.Duration
    Strategy         RetryStrategy
    Multiplier       float64
    JitterFactor     float64
    ShouldRetryFunc  func(error) bool
}

type Retrier struct {
    config     RetryConfig
    attempt    int
    lastError  error
}

func NewRetrier(config RetryConfig) *Retrier {
    return &Retrier{config: config}
}

func (r *Retrier) Reset() {
    r.attempt = 0
    r.lastError = nil
}

func (r *Retrier) NextDelay() time.Duration {
    var delay time.Duration
    
    switch r.config.Strategy {
    case RetryFixed:
        delay = r.config.InitialDelay
    case RetryLinear:
        delay = r.config.InitialDelay * time.Duration(r.attempt+1)
    case RetryExponential:
        delay = r.config.InitialDelay * time.Duration(1<<uint(r.attempt))
    case RetryExponentialWithJitter:
        base := r.config.InitialDelay * time.Duration(1<<uint(r.attempt))
        jitter := time.Duration(float64(base) * r.config.JitterFactor * rand.Float64())
        delay = base + jitter
    }
    
    if delay > r.config.MaxDelay {
        delay = r.config.MaxDelay
    }
    return delay
}

func (r *Retrier) ShouldRetry(err error) bool {
    if r.attempt >= r.config.MaxAttempts {
        return false
    }
    
    if r.config.ShouldRetryFunc != nil {
        return r.config.ShouldRetryFunc(err)
    }
    return true
}

func (r *Retrier) Attempt(fn func() error) error {
    r.Reset()
    
    for r.ShouldRetry(r.lastError) {
        err := fn()
        if err == nil {
            return nil
        }
        
        r.lastError = err
        r.attempt++
        
        if r.attempt < r.config.MaxAttempts {
            time.Sleep(r.NextDelay())
        }
    }
    
    return r.lastError
}