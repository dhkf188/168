// client_hardware.go - 硬件识别增强模块（完整修正版）
package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"os/exec"
	"runtime"
	"strings"
	"sync"
	"time"

	"golang.org/x/sys/windows/registry"
)

const (
    maxHardwareCacheSize = 100  // 最大缓存条目数
    maxHardwareCacheAge  = 10 * time.Minute  // 缓存最大存活时间
)

// 预定义错误变量
var (
	ErrHardwareNotSupported = errors.New("当前平台不支持硬件识别")
	ErrWMIQueryFailed       = errors.New("WMI查询失败")
	ErrRegistryAccessFailed = errors.New("注册表访问失败")
	ErrTimeout              = errors.New("硬件查询超时")
)

// 硬件信息缓存
var (
	hardwareCache     = make(map[string]interface{})
	hardwareCacheLock sync.RWMutex
	cacheTTL          = 5 * time.Minute
	cacheTimestamps   = make(map[string]time.Time)
)

// HardwareIdentifier 硬件识别器
type HardwareIdentifier struct {
	mu          sync.RWMutex
	cacheEnable bool
	timeout     time.Duration
}

// HardwareInfo 硬件信息
type HardwareInfo struct {
	CPUID           string   `json:"cpu_id"`
	CPUName         string   `json:"cpu_name"`
	CPUCores        int      `json:"cpu_cores"`
	MotherboardSN   string   `json:"motherboard_sn"`
	MotherboardModel string  `json:"motherboard_model"`
	DiskSerial      string   `json:"disk_serial"`
	DiskModel       string   `json:"disk_model"`
	MacAddresses    []string `json:"mac_addresses"`
	UUID            string   `json:"uuid"`
	BIOSSerial      string   `json:"bios_serial"`
	BIOSVersion     string   `json:"bios_version"`
	Fingerprint     string   `json:"fingerprint"`
	Reliability     float64  `json:"reliability"` // 硬件指纹可信度 0-1
}

// NewHardwareIdentifier 创建硬件识别器
func NewHardwareIdentifier() *HardwareIdentifier {
    h := &HardwareIdentifier{
        cacheEnable: true,
        timeout:     10 * time.Second,
    }
    
    // 启动定时清理goroutine
    go func() {
        ticker := time.NewTicker(5 * time.Minute)
        defer ticker.Stop()
        for range ticker.C {
            h.CleanExpiredCache()
        }
    }()
    
    return h
}

// SetCacheEnable 设置是否启用缓存
func (h *HardwareIdentifier) SetCacheEnable(enable bool) {
	h.cacheEnable = enable
}

// SetTimeout 设置查询超时时间
func (h *HardwareIdentifier) SetTimeout(timeout time.Duration) {
	h.timeout = timeout
}

// GetCPUInfo 获取CPU信息（增强版）
func (h *HardwareIdentifier) GetCPUInfo() string {
	if runtime.GOOS != "windows" {
		return ""
	}

	// 尝试从缓存获取
	if cached := h.getFromCache("cpu_info"); cached != nil {
		return cached.(string)
	}

	var cpuInfo string

	// 方法1: 注册表获取
	k, err := registry.OpenKey(registry.LOCAL_MACHINE,
		`HARDWARE\DESCRIPTION\System\CentralProcessor\0`,
		registry.QUERY_VALUE)
	if err == nil {
		defer k.Close()
		
		// 优先获取处理器名称
		processorName, _, err := k.GetStringValue("ProcessorNameString")
		if err == nil && processorName != "" {
			cpuInfo = processorName
		}
		
		// 如果没有，获取标识符
		if cpuInfo == "" {
			identifier, _, err := k.GetStringValue("Identifier")
			if err == nil && identifier != "" {
				cpuInfo = identifier
			}
		}
	}

	// 方法2: WMI查询（更详细）
	if cpuInfo == "" {
		output, err := h.execPowerShellWithTimeout(`
			Get-WmiObject Win32_Processor | 
			Select-Object -ExpandProperty Name
		`)
		if err == nil && output != "" {
			cpuInfo = strings.TrimSpace(output)
		}
	}

	// 缓存结果
	if cpuInfo != "" {
		h.setCache("cpu_info", cpuInfo)
	}

	return cpuInfo
}

// GetCPUID 获取CPU序列号（增强版）
func (h *HardwareIdentifier) GetCPUID() string {
	if runtime.GOOS != "windows" {
		return ""
	}

	if cached := h.getFromCache("cpu_id"); cached != nil {
		return cached.(string)
	}

	var cpuID string

	// 方法1: 注册表获取UniqueID
	k, err := registry.OpenKey(registry.LOCAL_MACHINE,
		`HARDWARE\DESCRIPTION\System\CentralProcessor\0`,
		registry.QUERY_VALUE)
	if err == nil {
		defer k.Close()
		uniqueID, _, err := k.GetStringValue("UniqueID")
		if err == nil && uniqueID != "" {
			cpuID = uniqueID
		}
	}

	// 方法2: WMI获取ProcessorId
	if cpuID == "" {
		output, err := h.execPowerShellWithTimeout(`
			Get-WmiObject Win32_Processor | 
			Select-Object -ExpandProperty ProcessorId
		`)
		if err == nil && output != "" && output != "0000000000000000" {
			cpuID = strings.TrimSpace(output)
		}
	}

	// 方法3: 基于CPU特征生成指纹（备用）
	if cpuID == "" {
		cpuInfo := h.GetCPUInfo()
		if cpuInfo != "" {
			// 结合CPU名称、核心数等信息生成唯一标识
			coreCount := h.GetCPUCoreCount()
			combined := fmt.Sprintf("%s|%d", cpuInfo, coreCount)
			hash := sha256.Sum256([]byte(combined))
			cpuID = hex.EncodeToString(hash[:])[:16]
		}
	}

	if cpuID != "" {
		h.setCache("cpu_id", cpuID)
	}

	return cpuID
}

// GetCPUCoreCount 获取CPU核心数
func (h *HardwareIdentifier) GetCPUCoreCount() int {
	if runtime.GOOS != "windows" {
		return runtime.NumCPU()
	}

	if cached := h.getFromCache("cpu_cores"); cached != nil {
		return cached.(int)
	}

	coreCount := runtime.NumCPU() // 默认值

	// 通过WMI获取物理核心数
	output, err := h.execPowerShellWithTimeout(`
		Get-WmiObject Win32_Processor | 
		Measure-Object -Property NumberOfCores -Sum | 
		Select-Object -ExpandProperty Sum
	`)
	if err == nil && output != "" {
		var count int
		if _, err := fmt.Sscanf(output, "%d", &count); err == nil && count > 0 {
			coreCount = count
		}
	}

	h.setCache("cpu_cores", coreCount)
	return coreCount
}

// GetMotherboardSerial 获取主板序列号（增强版）
func (h *HardwareIdentifier) GetMotherboardSerial() string {
	if runtime.GOOS != "windows" {
		return ""
	}

	if cached := h.getFromCache("motherboard_serial"); cached != nil {
		return cached.(string)
	}

	var serial string

	// 方法1: 注册表获取
	k, err := registry.OpenKey(registry.LOCAL_MACHINE,
		`HARDWARE\DESCRIPTION\System\BIOS`,
		registry.QUERY_VALUE)
	if err == nil {
		defer k.Close()
		
		// 尝试多个可能的键值
		keys := []string{
			"SystemSerialNumber",
			"BaseBoardSerialNumber",
			"SerialNumber",
		}
		
		for _, key := range keys {
			val, _, err := k.GetStringValue(key)
			if err == nil && val != "" && val != "To be filled by O.E.M." && val != "Default string" {
				serial = val
				break
			}
		}
	}

	// 方法2: WMI查询
	if serial == "" {
		output, err := h.execPowerShellWithTimeout(`
			$baseboard = Get-WmiObject Win32_BaseBoard
			if ($baseboard.SerialNumber -and $baseboard.SerialNumber -notmatch 'To be filled|Default') {
				$baseboard.SerialNumber
			} else {
				Get-WmiObject Win32_BIOS | Select-Object -ExpandProperty SerialNumber
			}
		`)
		if err == nil && output != "" && !strings.Contains(output, "To be filled") {
			serial = strings.TrimSpace(output)
		}
	}

	if serial != "" {
		h.setCache("motherboard_serial", serial)
	}

	return serial
}

// GetMotherboardModel 获取主板型号
func (h *HardwareIdentifier) GetMotherboardModel() string {
	if runtime.GOOS != "windows" {
		return ""
	}

	if cached := h.getFromCache("motherboard_model"); cached != nil {
		return cached.(string)
	}

	var model string

	// 注册表获取
	k, err := registry.OpenKey(registry.LOCAL_MACHINE,
		`HARDWARE\DESCRIPTION\System\BIOS`,
		registry.QUERY_VALUE)
	if err == nil {
		defer k.Close()
		baseBoardProduct, _, err := k.GetStringValue("BaseBoardProduct")
		if err == nil && baseBoardProduct != "" {
			model = baseBoardProduct
		}
	}

	// WMI查询
	if model == "" {
		output, err := h.execPowerShellWithTimeout(`
			Get-WmiObject Win32_BaseBoard | 
			Select-Object -ExpandProperty Product
		`)
		if err == nil && output != "" {
			model = strings.TrimSpace(output)
		}
	}

	if model != "" {
		h.setCache("motherboard_model", model)
	}

	return model
}

// GetDiskSerial 获取硬盘序列号（增强版）
func (h *HardwareIdentifier) GetDiskSerial() string {
	if runtime.GOOS != "windows" {
		return ""
	}

	if cached := h.getFromCache("disk_serial"); cached != nil {
		return cached.(string)
	}

	var serial string

	// 方法1: WMI获取物理媒体序列号
	output, err := h.execPowerShellWithTimeout(`
		Get-WmiObject Win32_PhysicalMedia | 
		Where-Object {$_.SerialNumber -and $_.SerialNumber -notmatch '^\s*$'} | 
		Select-Object -First 1 -ExpandProperty SerialNumber
	`)
	if err == nil && output != "" {
		serial = strings.TrimSpace(output)
	}

	// 方法2: 通过磁盘驱动器获取
	if serial == "" {
		output, err := h.execPowerShellWithTimeout(`
			Get-WmiObject Win32_DiskDrive | 
			Where-Object {$_.SerialNumber -and $_.SerialNumber -notmatch '^\s*$'} | 
			Select-Object -First 1 -ExpandProperty SerialNumber
		`)
		if err == nil && output != "" {
			serial = strings.TrimSpace(output)
		}
	}

	// 方法3: 注册表解析
	if serial == "" {
		k, err := registry.OpenKey(registry.LOCAL_MACHINE,
			`SYSTEM\CurrentControlSet\Services\Disk\Enum`,
			registry.QUERY_VALUE)
		if err == nil {
			defer k.Close()
			serial = h.parseDiskSerialFromRegistry(k)
		}
	}

	// 清理序列号（去除特殊字符）
	serial = strings.TrimSpace(serial)
	serial = strings.Trim(serial, "\x00")
	
	if serial != "" {
		h.setCache("disk_serial", serial)
	}

	return serial
}

// parseDiskSerialFromRegistry 从注册表解析磁盘序列号
func (h *HardwareIdentifier) parseDiskSerialFromRegistry(k registry.Key) string {
	values, err := k.ReadValueNames(0)
	if err != nil {
		return ""
	}
	
	for _, val := range values {
		data, _, err := k.GetStringValue(val)
		if err != nil {
			continue
		}
		
		// 解析格式如: IDE\DiskWDC_WD10EZEX-00WN4A0_________________________WD-WCC6Y5HJVV7U
		parts := strings.Split(data, "\\")
		if len(parts) < 2 {
			continue
		}
		
		diskInfo := parts[len(parts)-1]
		
		// 提取序列号（通常在最后一个下划线之后）
		lastUnderscore := strings.LastIndex(diskInfo, "_")
		if lastUnderscore > 0 && lastUnderscore < len(diskInfo)-1 {
			serial := diskInfo[lastUnderscore+1:]
			// 验证序列号格式（通常包含字母数字）
			if len(serial) >= 4 && !strings.ContainsAny(serial, "&%$#") {
				return serial
			}
		}
	}
	
	return ""
}

// GetDiskModel 获取磁盘型号
func (h *HardwareIdentifier) GetDiskModel() string {
	if runtime.GOOS != "windows" {
		return ""
	}

	if cached := h.getFromCache("disk_model"); cached != nil {
		return cached.(string)
	}

	var model string

	output, err := h.execPowerShellWithTimeout(`
		Get-WmiObject Win32_DiskDrive | 
		Where-Object {$_.Model -and $_.Model -notmatch '^\s*$'} | 
		Select-Object -First 1 -ExpandProperty Model
	`)
	if err == nil && output != "" {
		model = strings.TrimSpace(output)
	}

	if model != "" {
		h.setCache("disk_model", model)
	}

	return model
}

// GetSystemUUID 获取系统UUID（增强版）
func (h *HardwareIdentifier) GetSystemUUID() string {
	if runtime.GOOS != "windows" {
		return ""
	}

	if cached := h.getFromCache("system_uuid"); cached != nil {
		return cached.(string)
	}

	var uuid string

	// 方法1: 注册表MachineGuid
	k, err := registry.OpenKey(registry.LOCAL_MACHINE,
		`SOFTWARE\Microsoft\Cryptography`,
		registry.QUERY_VALUE)
	if err == nil {
		defer k.Close()
		machineGuid, _, err := k.GetStringValue("MachineGuid")
		if err == nil && machineGuid != "" {
			uuid = machineGuid
		}
	}

	// 方法2: WMI获取UUID
	if uuid == "" {
		output, err := h.execPowerShellWithTimeout(`
			Get-WmiObject Win32_ComputerSystemProduct | 
			Select-Object -ExpandProperty UUID
		`)
		if err == nil && output != "" && output != "00000000-0000-0000-0000-000000000000" {
			uuid = strings.TrimSpace(output)
		}
	}

	if uuid != "" {
		h.setCache("system_uuid", uuid)
	}

	return uuid
}

// GetBIOSInfo 获取BIOS信息
func (h *HardwareIdentifier) GetBIOSInfo() (serial, version string) {
	if runtime.GOOS != "windows" {
		return "", ""
	}

	if cached := h.getFromCache("bios_serial"); cached != nil {
		serial = cached.(string)
	}
	if cached := h.getFromCache("bios_version"); cached != nil {
		version = cached.(string)
	}
	if serial != "" && version != "" {
		return
	}

	// 从注册表获取
	k, err := registry.OpenKey(registry.LOCAL_MACHINE,
		`HARDWARE\DESCRIPTION\System\BIOS`,
		registry.QUERY_VALUE)
	if err == nil {
		defer k.Close()
		
		if serial == "" {
			s, _, _ := k.GetStringValue("SystemSerialNumber")
			serial = s
		}
		if version == "" {
			v, _, _ := k.GetStringValue("BIOSVersion")
			if len(v) > 0 {
				version = v
			}
		}
	}

	// WMI查询
	if serial == "" || version == "" {
		output, err := h.execPowerShellWithTimeout(`
			$bios = Get-WmiObject Win32_BIOS
			Write-Output "$($bios.SerialNumber)|$($bios.SMBIOSBIOSVersion)"
		`)
		if err == nil && output != "" {
			parts := strings.SplitN(output, "|", 2)
			if len(parts) == 2 {
				if serial == "" {
					serial = parts[0]
				}
				if version == "" {
					version = parts[1]
				}
			}
		}
	}

	if serial != "" {
		h.setCache("bios_serial", serial)
	}
	if version != "" {
		h.setCache("bios_version", version)
	}

	return
}

// GetAllMacAddresses 获取所有MAC地址（增强版）
func (h *HardwareIdentifier) GetAllMacAddresses() []string {
	if runtime.GOOS != "windows" {
		return []string{}
	}

	if cached := h.getFromCache("mac_addresses"); cached != nil {
		return cached.([]string)
	}

	macs := make([]string, 0)
	macSet := make(map[string]bool)

	// 方法1: 使用已有的SystemInfoCollector
	collector := NewSystemInfoCollector()
	mac := collector.GetMacAddress()
	if mac != "" && mac != "00:00:00:00:00:00" {
		macSet[strings.ToUpper(mac)] = true
	}

	// 方法2: PowerShell获取所有网卡
	output, err := h.execPowerShellWithTimeout(`
		Get-NetAdapter | 
		Where-Object {$_.Status -eq 'Up' -and $_.MacAddress} | 
		Select-Object -ExpandProperty MacAddress
	`)
	if err == nil {
		for _, line := range strings.Split(output, "\n") {
			line = strings.TrimSpace(strings.ToUpper(line))
			if line != "" && line != "00:00:00:00:00:00" {
				macSet[line] = true
			}
		}
	}

	// 方法3: 通过WMI获取
	output, err = h.execPowerShellWithTimeout(`
		Get-WmiObject Win32_NetworkAdapterConfiguration | 
		Where-Object {$_.MACAddress -and $_.IPEnabled} | 
		Select-Object -ExpandProperty MACAddress
	`)
	if err == nil {
		for _, line := range strings.Split(output, "\n") {
			line = strings.TrimSpace(strings.ToUpper(line))
			if line != "" && line != "00:00:00:00:00:00" {
				macSet[line] = true
			}
		}
	}

	// 转换为切片
	for mac := range macSet {
		macs = append(macs, mac)
	}

	if len(macs) > 0 {
		h.setCache("mac_addresses", macs)
	}

	return macs
}

// GetHardwareFingerprint 获取硬件指纹（增强版）
func (h *HardwareIdentifier) GetHardwareFingerprint() (string, float64) {
	if cached := h.getFromCache("fingerprint"); cached != nil {
		if fp, ok := cached.(*fingerprintCache); ok {
			return fp.fingerprint, fp.reliability
		}
	}

	components := make(map[string]string)
	reliability := 0.0
	totalWeight := 0.0

	// 定义硬件组件的权重
	hwComponents := []struct {
		name   string
		getter func() string
		weight float64
	}{
		{"cpuid", h.GetCPUID, 0.25},
		{"motherboard_sn", h.GetMotherboardSerial, 0.25},
		{"system_uuid", h.GetSystemUUID, 0.20},
		{"disk_serial", h.GetDiskSerial, 0.15},
		{"bios_serial", func() string { s, _ := h.GetBIOSInfo(); return s }, 0.15},
	}

	validComponents := make([]string, 0)

	for _, comp := range hwComponents {
		value := comp.getter()
		if value != "" {
			components[comp.name] = value
			validComponents = append(validComponents, value)
			reliability += comp.weight
			totalWeight += comp.weight
		}
	}

	// 归一化可信度
	if totalWeight > 0 {
		reliability = reliability / totalWeight
	}

	// 如果硬件组件不够，使用MAC地址补充
	if len(validComponents) < 2 {
		macs := h.GetAllMacAddresses()
		if len(macs) > 0 {
			validComponents = append(validComponents, strings.Join(macs, "|"))
			reliability = reliability * 0.5 // 降低可信度
		}
	}

	// 生成指纹
	fingerprintStr := strings.Join(validComponents, "|")
	hash := sha256.Sum256([]byte(fingerprintStr))
	fingerprint := hex.EncodeToString(hash[:])

	// 缓存结果
	h.setCache("fingerprint", &fingerprintCache{
		fingerprint: fingerprint,
		reliability: reliability,
	})

	return fingerprint, reliability
}

// GetCompleteHardwareInfo 获取完整硬件信息
func (h *HardwareIdentifier) GetCompleteHardwareInfo() *HardwareInfo {
	biosSerial, biosVersion := h.GetBIOSInfo()
	fingerprint, reliability := h.GetHardwareFingerprint()
	
	info := &HardwareInfo{
		CPUID:            h.GetCPUID(),
		CPUName:          h.GetCPUInfo(),
		CPUCores:         h.GetCPUCoreCount(),
		MotherboardSN:    h.GetMotherboardSerial(),
		MotherboardModel: h.GetMotherboardModel(),
		DiskSerial:       h.GetDiskSerial(),
		DiskModel:        h.GetDiskModel(),
		MacAddresses:     h.GetAllMacAddresses(),
		UUID:             h.GetSystemUUID(),
		BIOSSerial:       biosSerial,
		BIOSVersion:      biosVersion,
		Fingerprint:      fingerprint,
		Reliability:      reliability,
	}
	
	return info
}

// execPowerShellWithTimeout 带超时的PowerShell执行
func (h *HardwareIdentifier) execPowerShellWithTimeout(command string) (string, error) {
	ctx, cancel := context.WithTimeout(context.Background(), h.timeout)
	defer cancel()
	
	cmd := exec.CommandContext(ctx, "powershell", "-NoProfile", "-NonInteractive", "-Command", command)
	output, err := cmd.Output()
	
	if ctx.Err() == context.DeadlineExceeded {
		return "", ErrTimeout
	}
	
	if err != nil {
		return "", fmt.Errorf("%w: %v", ErrWMIQueryFailed, err)
	}
	
	return strings.TrimSpace(string(output)), nil
}

// getFromCache 从缓存获取数据
func (h *HardwareIdentifier) getFromCache(key string) interface{} {
	if !h.cacheEnable {
		return nil
	}
	
	hardwareCacheLock.RLock()
	defer hardwareCacheLock.RUnlock()
	
	// 检查是否过期
	if timestamp, ok := cacheTimestamps[key]; ok {
		if time.Since(timestamp) > cacheTTL {
			return nil
		}
	}
	
	return hardwareCache[key]
}

// setCache 设置缓存
func (h *HardwareIdentifier) setCache(key string, value interface{}) {
    if !h.cacheEnable {
        return
    }
    
    hardwareCacheLock.Lock()
    defer hardwareCacheLock.Unlock()
    
    // 限制缓存大小
    if len(hardwareCache) >= maxHardwareCacheSize {
        // 删除最旧的条目
        var oldestKey string
        var oldestTime time.Time
        first := true
        
        for k, ts := range cacheTimestamps {
            if first || ts.Before(oldestTime) {
                oldestKey = k
                oldestTime = ts
                first = false
            }
        }
        
        if oldestKey != "" {
            delete(hardwareCache, oldestKey)
            delete(cacheTimestamps, oldestKey)
            logDebug("硬件缓存已满，删除旧条目: %s", oldestKey)
        }
    }
    
    hardwareCache[key] = value
    cacheTimestamps[key] = time.Now()
}

// ClearCache 清除缓存
func (h *HardwareIdentifier) ClearCache() {
	hardwareCacheLock.Lock()
	defer hardwareCacheLock.Unlock()
	
	hardwareCache = make(map[string]interface{})
	cacheTimestamps = make(map[string]time.Time)
}

// GetHardwareSummary 获取硬件摘要（用于快速展示）
func (h *HardwareIdentifier) GetHardwareSummary() map[string]string {
	info := h.GetCompleteHardwareInfo()
	
	summary := make(map[string]string)
	summary["cpu"] = info.CPUName
	summary["motherboard"] = info.MotherboardModel
	summary["disk"] = info.DiskModel
	summary["fingerprint"] = info.Fingerprint[:16] + "..."
	
	if info.Reliability > 0.7 {
		summary["reliability"] = "高"
	} else if info.Reliability > 0.4 {
		summary["reliability"] = "中"
	} else {
		summary["reliability"] = "低"
	}
	
	return summary
}

// fingerprintCache 指纹缓存结构
type fingerprintCache struct {
	fingerprint string
	reliability float64
}

// CleanExpiredCache 清理过期缓存
func (h *HardwareIdentifier) CleanExpiredCache() {
    if !h.cacheEnable {
        return
    }
    
    hardwareCacheLock.Lock()
    defer hardwareCacheLock.Unlock()
    
    now := time.Now()
    expiredKeys := make([]string, 0)
    
    for key, ts := range cacheTimestamps {
        if now.Sub(ts) > maxHardwareCacheAge {
            expiredKeys = append(expiredKeys, key)
        }
    }
    
    for _, key := range expiredKeys {
        delete(hardwareCache, key)
        delete(cacheTimestamps, key)
    }
    
    if len(expiredKeys) > 0 {
        logDebug("清理过期硬件缓存: %d条", len(expiredKeys))
    }
}