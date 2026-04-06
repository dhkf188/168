// client_win.go - Windows API 调用（完整版）
package main

import (
    "syscall"
    "unsafe"
)

var (
    user32 = syscall.NewLazyDLL("user32.dll")
    
    getForegroundWindow      = user32.NewProc("GetForegroundWindow")
    getWindowTextW           = user32.NewProc("GetWindowTextW")
    getWindowThreadProcessId = user32.NewProc("GetWindowThreadProcessId")
    isIconic                 = user32.NewProc("IsIconic")
    getWindowRect            = user32.NewProc("GetWindowRect")
    showWindow               = user32.NewProc("ShowWindow")
)

var (
    kernel32           = syscall.NewLazyDLL("kernel32.dll")
    getConsoleWindow   = kernel32.NewProc("GetConsoleWindow")
)

// ForegroundWindowInfo 前台窗口信息
type ForegroundWindowInfo struct {
    HWND   uintptr
    PID    uint32
    Title  string
    Width  int
    Height int
}

// GetForegroundWindowInfo 获取前台窗口信息
func GetForegroundWindowInfo() *ForegroundWindowInfo {
    hwnd, _, _ := getForegroundWindow.Call()
    if hwnd == 0 {
        return nil
    }
    
    // 检查窗口是否最小化
    isMinimized, _, _ := isIconic.Call(hwnd)
    if isMinimized != 0 {
        return nil
    }
    
    var pid uint32
    getWindowThreadProcessId.Call(hwnd, uintptr(unsafe.Pointer(&pid)))
    
    titleBuf := make([]uint16, 512)
    getWindowTextW.Call(hwnd, uintptr(unsafe.Pointer(&titleBuf[0])), 512)
    title := syscall.UTF16ToString(titleBuf)
    
    if title == "" {
        return nil
    }
    
    // 获取窗口尺寸
    var rect struct{ Left, Top, Right, Bottom int32 }
    getWindowRect.Call(hwnd, uintptr(unsafe.Pointer(&rect)))
    width := int(rect.Right - rect.Left)
    height := int(rect.Bottom - rect.Top)
    
    return &ForegroundWindowInfo{
        HWND:   hwnd,
        PID:    pid,
        Title:  title,
        Width:  width,
        Height: height,
    }
}

// IsWindowMinimized 检查窗口是否最小化
func IsWindowMinimized(hwnd uintptr) bool {
    result, _, _ := isIconic.Call(hwnd)
    return result != 0
}

// GetConsoleWindow 获取控制台窗口句柄
func GetConsoleWindow() uintptr {
    ret, _, _ := getConsoleWindow.Call()
    return ret
}

// ShowWindow 显示/隐藏窗口
func ShowWindow(hwnd uintptr, nCmdShow int) {
    showWindow.Call(hwnd, uintptr(nCmdShow))
}
