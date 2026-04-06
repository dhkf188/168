// client_autostart.go - 开机自启管理模块（完整版）
package main

import (
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"time"
	"unsafe"

	"golang.org/x/sys/windows"
	"golang.org/x/sys/windows/registry"
)

// 预定义错误变量
var (
	ErrUnsupportedPlatform = errors.New("当前平台不支持开机自启")
	ErrRegistryAccess      = errors.New("无法访问注册表")
	ErrShortcutCreation    = errors.New("创建快捷方式失败")
)

// AutoStartManager 开机自启管理器
type AutoStartManager struct {
	appName     string
	exePath     string
	useRegistry bool // 是否使用注册表方式（默认true）
}

// NewAutoStartManager 创建开机自启管理器
func NewAutoStartManager(appName string) *AutoStartManager {
	exePath, err := os.Executable()
	if err != nil {
		exePath = os.Args[0] // 降级方案
	}

	// 获取绝对路径，避免相对路径问题
	if absPath, err := filepath.Abs(exePath); err == nil {
		exePath = absPath
	}

	return &AutoStartManager{
		appName:     appName,
		exePath:     exePath,
		useRegistry: true,
	}
}

// SetUseRegistry 设置是否使用注册表方式（false则使用快捷方式）
func (a *AutoStartManager) SetUseRegistry(use bool) {
	a.useRegistry = use
}

// EnableAutoStart 启用开机自启
func (a *AutoStartManager) EnableAutoStart() error {
	if runtime.GOOS != "windows" {
		return ErrUnsupportedPlatform
	}

	// 验证可执行文件是否存在
	if _, err := os.Stat(a.exePath); err != nil {
		return fmt.Errorf("可执行文件不存在: %v", err)
	}

	var err error
	if a.useRegistry {
		err = a.enableRegistryAutoStart()
	} else {
		err = a.CreateStartupShortcut()
	}

	if err != nil {
		return fmt.Errorf("启用开机自启失败: %v", err)
	}

	logInfo("✅ 已启用开机自启: %s", a.appName)
	return nil
}

// enableRegistryAutoStart 通过注册表启用开机自启
func (a *AutoStartManager) enableRegistryAutoStart() error {
	keyPath := `SOFTWARE\Microsoft\Windows\CurrentVersion\Run`

	k, err := registry.OpenKey(registry.CURRENT_USER, keyPath, registry.SET_VALUE)
	if err != nil {
		return fmt.Errorf("%w: %v", ErrRegistryAccess, err)
	}
	defer k.Close()

	// 使用环境变量或相对路径优化命令行
	cmdLine := a.buildCommandLine()

	return k.SetStringValue(a.appName, cmdLine)
}

// buildCommandLine 构建命令行参数
func (a *AutoStartManager) buildCommandLine() string {
	// 检查是否可以使用相对路径或环境变量
	appData := os.Getenv("APPDATA")
	if appData != "" && strings.HasPrefix(a.exePath, appData) {
		// 如果程序在AppData目录下，使用环境变量
		relPath := strings.TrimPrefix(a.exePath, appData)
		return fmt.Sprintf(`%%APPDATA%%%s -silent`, relPath)
	}

	return fmt.Sprintf(`"%s" -silent`, a.exePath)
}

// DisableAutoStart 禁用开机自启
func (a *AutoStartManager) DisableAutoStart() error {
	if runtime.GOOS != "windows" {
		return nil
	}

	var errs []error

	// 同时清理注册表和快捷方式，确保彻底禁用
	if err := a.disableRegistryAutoStart(); err != nil && !errors.Is(err, registry.ErrNotExist) {
		errs = append(errs, err)
	}

	if err := a.RemoveStartupShortcut(); err != nil && !os.IsNotExist(err) {
		errs = append(errs, err)
	}

	if len(errs) > 0 {
		return fmt.Errorf("禁用开机自启时发生错误: %v", errs)
	}

	logInfo("✅ 已禁用开机自启: %s", a.appName)
	return nil
}

// disableRegistryAutoStart 从注册表删除开机自启
func (a *AutoStartManager) disableRegistryAutoStart() error {
	keyPath := `SOFTWARE\Microsoft\Windows\CurrentVersion\Run`

	k, err := registry.OpenKey(registry.CURRENT_USER, keyPath, registry.SET_VALUE)
	if err != nil {
		return fmt.Errorf("%w: %v", ErrRegistryAccess, err)
	}
	defer k.Close()

	return k.DeleteValue(a.appName)
}

// IsAutoStartEnabled 检查是否已启用开机自启
func (a *AutoStartManager) IsAutoStartEnabled() (bool, error) {
	if runtime.GOOS != "windows" {
		return false, nil
	}

	// 检查注册表
	if enabled, err := a.isRegistryAutoStartEnabled(); err == nil && enabled {
		return true, nil
	}

	// 检查快捷方式
	return a.isStartupShortcutExists()
}

// isRegistryAutoStartEnabled 检查注册表中是否已启用
func (a *AutoStartManager) isRegistryAutoStartEnabled() (bool, error) {
	keyPath := `SOFTWARE\Microsoft\Windows\CurrentVersion\Run`

	k, err := registry.OpenKey(registry.CURRENT_USER, keyPath, registry.QUERY_VALUE)
	if err != nil {
		return false, nil
	}
	defer k.Close()

	_, _, err = k.GetStringValue(a.appName)
	if err == registry.ErrNotExist {
		return false, nil
	}
	return err == nil, err
}

// GetAutoStartCommand 获取开机自启命令
func (a *AutoStartManager) GetAutoStartCommand() (string, error) {
	if runtime.GOOS != "windows" {
		return "", ErrUnsupportedPlatform
	}

	keyPath := `SOFTWARE\Microsoft\Windows\CurrentVersion\Run`

	k, err := registry.OpenKey(registry.CURRENT_USER, keyPath, registry.QUERY_VALUE)
	if err != nil {
		return "", err
	}
	defer k.Close()

	val, _, err := k.GetStringValue(a.appName)
	return val, err
}

// CreateStartupShortcut 创建启动快捷方式
func (a *AutoStartManager) CreateStartupShortcut() error {
	startupFolder, err := a.getStartupFolder()
	if err != nil {
		return err
	}

	shortcutPath := filepath.Join(startupFolder, a.appName+".lnk")

	// 如果快捷方式已存在，先删除
	os.Remove(shortcutPath)

	// 使用更简洁的PowerShell脚本
	psScript := fmt.Sprintf(`
		$WScriptShell = New-Object -ComObject WScript.Shell
		$Shortcut = $WScriptShell.CreateShortcut('%s')
		$Shortcut.TargetPath = '%s'
		$Shortcut.Arguments = '-silent'
		$Shortcut.WorkingDirectory = '%s'
		$Shortcut.IconLocation = '%s'
		$Shortcut.Save()
	`, shortcutPath, a.exePath, filepath.Dir(a.exePath), a.exePath)

	cmd := exec.Command("powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", psScript)

	// 设置超时，避免卡死
	done := make(chan error, 1)
	go func() {
		done <- cmd.Run()
	}()

	select {
	case err := <-done:
		if err != nil {
			return fmt.Errorf("%w: %v", ErrShortcutCreation, err)
		}
	case <-time.After(5 * time.Second):
		return fmt.Errorf("%w: 超时", ErrShortcutCreation)
	}

	logInfo("✅ 已创建启动快捷方式: %s", shortcutPath)
	return nil
}

// RemoveStartupShortcut 删除启动快捷方式
func (a *AutoStartManager) RemoveStartupShortcut() error {
	startupFolder, err := a.getStartupFolder()
	if err != nil {
		return nil // 获取启动文件夹失败，忽略错误
	}

	shortcutPath := filepath.Join(startupFolder, a.appName+".lnk")
	if err := os.Remove(shortcutPath); err != nil && !os.IsNotExist(err) {
		return fmt.Errorf("删除快捷方式失败: %v", err)
	}

	logInfo("✅ 已删除启动快捷方式")
	return nil
}

// isStartupShortcutExists 检查快捷方式是否存在
func (a *AutoStartManager) isStartupShortcutExists() (bool, error) {
	startupFolder, err := a.getStartupFolder()
	if err != nil {
		return false, nil
	}

	shortcutPath := filepath.Join(startupFolder, a.appName+".lnk")
	_, err = os.Stat(shortcutPath)
	if err == nil {
		return true, nil
	}
	if os.IsNotExist(err) {
		return false, nil
	}
	return false, err
}

// getStartupFolder 获取启动文件夹路径
func (a *AutoStartManager) getStartupFolder() (string, error) {
	if runtime.GOOS != "windows" {
		return "", ErrUnsupportedPlatform
	}

	// 使用 Windows API 获取启动文件夹（更可靠）
	const CSIDL_STARTUP = 0x0007
	buf := make([]uint16, 1024)

	ret := SHGetFolderPathW(0, CSIDL_STARTUP, 0, 0, &buf[0])
	if ret != 0 {
		// 降级方案：使用环境变量
		startupFolder := filepath.Join(os.Getenv("APPDATA"),
			"Microsoft", "Windows", "Start Menu", "Programs", "Startup")
		if _, err := os.Stat(startupFolder); err != nil {
			return "", fmt.Errorf("无法获取启动文件夹路径")
		}
		return startupFolder, nil
	}

	return windows.UTF16ToString(buf), nil
}

// ToggleAutoStart 切换开机自启状态
func (a *AutoStartManager) ToggleAutoStart() error {
	enabled, err := a.IsAutoStartEnabled()
	if err != nil {
		return err
	}

	if enabled {
		return a.DisableAutoStart()
	}
	return a.EnableAutoStart()
}

// GetAutoStartMethod 获取当前使用的自启方式
func (a *AutoStartManager) GetAutoStartMethod() string {
	if enabled, _ := a.isRegistryAutoStartEnabled(); enabled {
		return "registry"
	}
	if exists, _ := a.isStartupShortcutExists(); exists {
		return "shortcut"
	}
	return "none"
}

// RepairAutoStart 修复开机自启（如果自启存在但命令无效）
func (a *AutoStartManager) RepairAutoStart() error {
	enabled, err := a.IsAutoStartEnabled()
	if err != nil {
		return err
	}

	if !enabled {
		return a.EnableAutoStart()
	}

	// 验证自启命令是否有效
	cmdLine, err := a.GetAutoStartCommand()
	if err == nil && cmdLine != "" {
		// 检查命令中引用的可执行文件是否存在
		if !a.validateCommandLine(cmdLine) {
			logWarn("开机自启命令无效，重新设置")
			if err := a.DisableAutoStart(); err != nil {
				return err
			}
			return a.EnableAutoStart()
		}
	}

	return nil
}

// validateCommandLine 验证命令行是否有效
func (a *AutoStartManager) validateCommandLine(cmdLine string) bool {
	// 提取可执行文件路径
	// 处理带引号的路径
	if strings.HasPrefix(cmdLine, "\"") {
		endQuote := strings.Index(cmdLine[1:], "\"")
		if endQuote > 0 {
			exePath := cmdLine[1 : endQuote+1]
			_, err := os.Stat(exePath)
			return err == nil
		}
	} else {
		// 无引号的情况
		parts := strings.Fields(cmdLine)
		if len(parts) > 0 {
			// 移除可能的参数
			exePath := parts[0]
			// 处理环境变量
			if strings.HasPrefix(exePath, "%") && strings.HasSuffix(exePath, "%") {
				// 简单处理 %APPDATA% 等环境变量
				envVar := strings.Trim(exePath, "%")
				if envValue := os.Getenv(envVar); envValue != "" {
					exePath = envValue + strings.TrimPrefix(strings.TrimPrefix(cmdLine, exePath), " ")
				}
			}
			_, err := os.Stat(exePath)
			return err == nil
		}
	}
	return false
}

// GetAutoStartInfo 获取自启详细信息
func (a *AutoStartManager) GetAutoStartInfo() map[string]interface{} {
	info := make(map[string]interface{})

	enabled, _ := a.IsAutoStartEnabled()
	info["enabled"] = enabled
	info["method"] = a.GetAutoStartMethod()

	if cmdLine, err := a.GetAutoStartCommand(); err == nil {
		info["command"] = cmdLine
		info["command_valid"] = a.validateCommandLine(cmdLine)
	}

	info["exe_path"] = a.exePath
	info["exe_exists"] = a.exePathExists()

	return info
}

// exePathExists 检查可执行文件是否存在
func (a *AutoStartManager) exePathExists() bool {
	_, err := os.Stat(a.exePath)
	return err == nil
}

// SetAutoStartDelay 设置延迟启动（创建带延迟的启动任务）
func (a *AutoStartManager) SetAutoStartDelay(delaySeconds int) error {
	if runtime.GOOS != "windows" {
		return ErrUnsupportedPlatform
	}

	if delaySeconds <= 0 {
		return a.RemoveDelayedStart()
	}

	// 使用 schtasks 创建延迟启动任务
	taskName := a.appName + "_DelayedStart"

	// 先删除已存在的任务
	a.RemoveDelayedStart()

	// 构建 schtasks 命令
	cmdLine := fmt.Sprintf(`schtasks /create /tn "%s" /tr "\"%s\" -silent" /sc onlogon /delay %s /f`,
		taskName, a.exePath, formatDelay(delaySeconds))

	cmd := exec.Command("cmd", "/c", cmdLine)
	output, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("创建延迟启动任务失败: %v, 输出: %s", err, string(output))
	}

	logInfo("✅ 已设置延迟启动: %d秒", delaySeconds)
	return nil
}

// RemoveDelayedStart 移除延迟启动任务
func (a *AutoStartManager) RemoveDelayedStart() error {
	taskName := a.appName + "_DelayedStart"
	cmdLine := fmt.Sprintf(`schtasks /delete /tn "%s" /f`, taskName)

	cmd := exec.Command("cmd", "/c", cmdLine)
	if err := cmd.Run(); err != nil {
		// 任务不存在不算错误
		return nil
	}

	logInfo("✅ 已删除延迟启动任务")
	return nil
}

// formatDelay 格式化延迟时间（秒转分钟或秒格式）
func formatDelay(seconds int) string {
	if seconds <= 60 {
		return fmt.Sprintf("PT%dS", seconds)
	}
	minutes := seconds / 60
	remainingSeconds := seconds % 60
	if remainingSeconds > 0 {
		return fmt.Sprintf("PT%dM%dS", minutes, remainingSeconds)
	}
	return fmt.Sprintf("PT%dM", minutes)
}

// CreateTaskSchedulerTask 使用任务计划程序创建开机启动（更可靠的方式）
func (a *AutoStartManager) CreateTaskSchedulerTask(delaySeconds int) error {
	if runtime.GOOS != "windows" {
		return ErrUnsupportedPlatform
	}

	taskName := a.appName

	// 构建 XML 任务定义
	xmlTemplate := `<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Employee Monitor Auto Start</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <Delay>%s</Delay>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>%s</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>true</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <DisallowStartOnRemoteAppSession>false</DisallowStartOnRemoteAppSession>
    <UseUnifiedSchedulingEngine>true</UseUnifiedSchedulingEngine>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>"%s"</Command>
      <Arguments>-silent</Arguments>
      <WorkingDirectory>%s</WorkingDirectory>
    </Exec>
  </Actions>
</Task>`

	delayStr := formatDelay(delaySeconds)
	if delaySeconds <= 0 {
		delayStr = "PT0S"
	}

	username := os.Getenv("USERNAME")
	workingDir := filepath.Dir(a.exePath)

	xmlContent := fmt.Sprintf(xmlTemplate, delayStr, username, a.exePath, workingDir)

	// 创建临时XML文件
	tempFile := filepath.Join(os.TempDir(), fmt.Sprintf("autostart_%d.xml", time.Now().UnixNano()))
	if err := os.WriteFile(tempFile, []byte(xmlContent), 0644); err != nil {
		return fmt.Errorf("创建临时XML文件失败: %v", err)
	}
	defer os.Remove(tempFile)

	// 导入任务
	cmdLine := fmt.Sprintf(`schtasks /create /tn "%s" /xml "%s" /f`, taskName, tempFile)
	cmd := exec.Command("cmd", "/c", cmdLine)
	output, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("创建任务计划失败: %v, 输出: %s", err, string(output))
	}

	logInfo("✅ 已通过任务计划程序启用开机自启: %s", taskName)
	return nil
}

// RemoveTaskSchedulerTask 删除任务计划程序中的任务
func (a *AutoStartManager) RemoveTaskSchedulerTask() error {
	taskName := a.appName
	cmdLine := fmt.Sprintf(`schtasks /delete /tn "%s" /f`, taskName)

	cmd := exec.Command("cmd", "/c", cmdLine)
	if err := cmd.Run(); err != nil {
		// 任务不存在不算错误
		return nil
	}

	logInfo("✅ 已删除任务计划: %s", taskName)
	return nil
}

// SHGetFolderPathW Windows API 函数
func SHGetFolderPathW(hwnd uintptr, csidl int32, hToken uintptr, dwFlags uint32, pszPath *uint16) int32 {
	ret, _, _ := procSHGetFolderPathW.Call(
		hwnd,
		uintptr(csidl),
		hToken,
		uintptr(dwFlags),
		uintptr(unsafe.Pointer(pszPath)),
	)
	return int32(ret)
}

// Windows API 函数声明
var (
	modShell32           = windows.NewLazySystemDLL("shell32.dll")
	procSHGetFolderPathW = modShell32.NewProc("SHGetFolderPathW")
)