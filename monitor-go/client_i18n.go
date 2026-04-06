// client_i18n.go - 国际化管理器（完整重构版）
package main

import (
	"fmt"
	"os"
	"runtime"
	"strings"
	"sync"
	"syscall"
)

// I18nManager 国际化管理器
type I18nManager struct {
	currentLang string
	texts       map[string]map[string]string
	cache       map[string]string
	mu          sync.RWMutex
}

// 语言常量
const (
	LangZH = "zh"
	LangVI = "vi"
	LangEN = "en"
)

var (
	globalI18n     *I18nManager
	i18nOnce       sync.Once
)

// GetI18nManager 获取全局国际化管理器
func GetI18nManager() *I18nManager {
	i18nOnce.Do(func() {
		globalI18n = NewI18nManager(true)
	})
	return globalI18n
}

// NewI18nManager 创建国际化管理器
func NewI18nManager(autoDetect bool) *I18nManager {
	m := &I18nManager{
		texts: make(map[string]map[string]string),
		cache: make(map[string]string),
	}

	m.loadTexts()

	if autoDetect {
		m.currentLang = m.detectLanguage()
	} else {
		m.currentLang = LangEN
	}

	logInfo("系统语言: %s", m.currentLang)

	return m
}

func (i *I18nManager) loadTexts() {
	// 通用
	i.texts["yes"] = map[string]string{LangZH: "是", LangVI: "Có", LangEN: "Yes"}
	i.texts["no"] = map[string]string{LangZH: "否", LangVI: "Không", LangEN: "No"}
	i.texts["ok"] = map[string]string{LangZH: "确定", LangVI: "Xác nhận", LangEN: "OK"}
	i.texts["cancel"] = map[string]string{LangZH: "取消", LangVI: "Hủy", LangEN: "Cancel"}
	i.texts["close"] = map[string]string{LangZH: "关闭", LangVI: "Đóng", LangEN: "Close"}
	i.texts["save"] = map[string]string{LangZH: "保存", LangVI: "Lưu", LangEN: "Save"}
	i.texts["confirm"] = map[string]string{LangZH: "确认", LangVI: "Xác nhận", LangEN: "Confirm"}

	// 状态
	i.texts["running"] = map[string]string{LangZH: "运行中", LangVI: "Đang chạy", LangEN: "Running"}
	i.texts["stopped"] = map[string]string{LangZH: "已停止", LangVI: "Đã dừng", LangEN: "Stopped"}
	i.texts["paused"] = map[string]string{LangZH: "已暂停", LangVI: "Đã tạm dừng", LangEN: "Paused"}
	i.texts["online"] = map[string]string{LangZH: "在线", LangVI: "Trực tuyến", LangEN: "Online"}
	i.texts["offline"] = map[string]string{LangZH: "离线", LangVI: "Ngoại tuyến", LangEN: "Offline"}

	// 健康状态
	i.texts["healthy"] = map[string]string{LangZH: "健康", LangVI: "Khỏe mạnh", LangEN: "Healthy"}
	i.texts["degraded"] = map[string]string{LangZH: "降级", LangVI: "Suy giảm", LangEN: "Degraded"}
	i.texts["unhealthy"] = map[string]string{LangZH: "异常", LangVI: "Bất thường", LangEN: "Unhealthy"}
	i.texts["unknown"] = map[string]string{LangZH: "未知", LangVI: "Không xác định", LangEN: "Unknown"}

	// 托盘菜单
	i.texts["show_status"] = map[string]string{LangZH: "显示状态", LangVI: "Hiển thị trạng thái", LangEN: "Show Status"}
	i.texts["health_status"] = map[string]string{LangZH: "健康状态", LangVI: "Trạng thái sức khỏe", LangEN: "Health Status"}
	i.texts["pause_monitor"] = map[string]string{LangZH: "暂停监控", LangVI: "Tạm dừng giám sát", LangEN: "Pause Monitoring"}
	i.texts["resume_monitor"] = map[string]string{LangZH: "恢复监控", LangVI: "Tiếp tục giám sát", LangEN: "Resume Monitoring"}
	i.texts["screenshot_now"] = map[string]string{LangZH: "立即截图", LangVI: "Chụp màn hình ngay", LangEN: "Screenshot Now"}
	i.texts["upload_queue"] = map[string]string{LangZH: "上传队列", LangVI: "Hàng đợi tải lên", LangEN: "Upload Queue"}
	i.texts["cleanup_cache"] = map[string]string{LangZH: "清理缓存", LangVI: "Dọn bộ nhớ đệm", LangEN: "Cleanup Cache"}
	i.texts["network_diagnostic"] = map[string]string{LangZH: "网络诊断", LangVI: "Chẩn đoán mạng", LangEN: "Network Diagnostic"}
	i.texts["reconfigure"] = map[string]string{LangZH: "重新配置", LangVI: "Cấu hình lại", LangEN: "Reconfigure"}
	i.texts["autostart"] = map[string]string{LangZH: "开机自启", LangVI: "Tự động khởi động", LangEN: "Auto Start"}
	i.texts["view_log"] = map[string]string{LangZH: "查看日志", LangVI: "Xem nhật ký", LangEN: "View Log"}
	i.texts["exit"] = map[string]string{LangZH: "退出", LangVI: "Thoát", LangEN: "Exit"}

	// 配置对话框
	i.texts["config_title"] = map[string]string{LangZH: "员工监控系统 - 首次配置", LangVI: "Hệ thống giám sát - Cấu hình lần đầu", LangEN: "Monitor System - First Setup"}
	i.texts["config_welcome"] = map[string]string{LangZH: "欢迎使用员工监控系统", LangVI: "Chào mừng bạn", LangEN: "Welcome"}
	i.texts["config_description"] = map[string]string{LangZH: "首次运行需要配置员工信息", LangVI: "Cần cấu hình thông tin nhân viên", LangEN: "First run requires employee info"}
	i.texts["config_employee_info"] = map[string]string{LangZH: "员工信息", LangVI: "Thông tin nhân viên", LangEN: "Employee Info"}
	i.texts["config_name"] = map[string]string{LangZH: "您的姓名", LangVI: "Tên của bạn", LangEN: "Your name"}
	i.texts["config_name_hint"] = map[string]string{LangZH: "例如：张三", LangVI: "Ví dụ: Nguyễn Văn A", LangEN: "e.g., John Smith"}
	i.texts["config_system_info"] = map[string]string{LangZH: "系统信息", LangVI: "Thông tin hệ thống", LangEN: "System Info"}
	i.texts["config_computer_name"] = map[string]string{LangZH: "计算机名", LangVI: "Tên máy tính", LangEN: "Computer name"}
	i.texts["config_user_name"] = map[string]string{LangZH: "用户名", LangVI: "Tên người dùng", LangEN: "Username"}
	i.texts["config_remember"] = map[string]string{LangZH: "记住此姓名", LangVI: "Ghi nhớ tên này", LangEN: "Remember name"}

	// 统计
	i.texts["stats_title"] = map[string]string{LangZH: "运行统计", LangVI: "Thống kê", LangEN: "Statistics"}
	i.texts["stats_uptime"] = map[string]string{LangZH: "运行时间", LangVI: "Thời gian chạy", LangEN: "Uptime"}
	i.texts["stats_screenshots"] = map[string]string{LangZH: "截图数量", LangVI: "Số ảnh", LangEN: "Screenshots"}
	i.texts["stats_skipped"] = map[string]string{LangZH: "跳过相似", LangVI: "Bỏ qua", LangEN: "Skipped"}
	i.texts["stats_uploaded"] = map[string]string{LangZH: "上传成功", LangVI: "Đã tải lên", LangEN: "Uploaded"}
	i.texts["stats_failed"] = map[string]string{LangZH: "上传失败", LangVI: "Thất bại", LangEN: "Failed"}
    i.texts["hardware_info"] = map[string]string{
        LangZH: "硬件信息",
        LangVI: "Thông tin phần cứng",
        LangEN: "Hardware Info",
    }
    i.texts["hardware_cpu"] = map[string]string{
        LangZH: "CPU",
        LangVI: "CPU",
        LangEN: "CPU",
    }
    i.texts["hardware_motherboard"] = map[string]string{
        LangZH: "主板",
        LangVI: "Bo mạch chủ",
        LangEN: "Motherboard",
    }
    i.texts["hardware_disk"] = map[string]string{
        LangZH: "磁盘",
        LangVI: "Đĩa cứng",
        LangEN: "Disk",
    }
    i.texts["hardware_fingerprint"] = map[string]string{
        LangZH: "硬件指纹",
        LangVI: "Dấu vân tay phần cứng",
        LangEN: "Hardware Fingerprint",
    }
    i.texts["hardware_reliability"] = map[string]string{
        LangZH: "可信度",
        LangVI: "Độ tin cậy",
        LangEN: "Reliability",
    }
    
    // 开机自启相关
    i.texts["autostart_enabled"] = map[string]string{
        LangZH: "已启用",
        LangVI: "Đã bật",
        LangEN: "Enabled",
    }
    i.texts["autostart_disabled"] = map[string]string{
        LangZH: "未启用",
        LangVI: "Chưa bật",
        LangEN: "Disabled",
    }
    i.texts["autostart_registry"] = map[string]string{
        LangZH: "注册表方式",
        LangVI: "Phương thức Registry",
        LangEN: "Registry Method",
    }
    i.texts["autostart_shortcut"] = map[string]string{
        LangZH: "快捷方式",
        LangVI: "Lối tắt",
        LangEN: "Shortcut",
    }
    i.texts["autostart_delay"] = map[string]string{
        LangZH: "延迟启动",
        LangVI: "Khởi động trễ",
        LangEN: "Delayed Start",
    }
}

// detectLanguage 检测系统语言

func (i *I18nManager) detectLanguage() string {
    // 方法1: 检查环境变量
    lang := os.Getenv("LANG")
    if lang == "" {
        lang = os.Getenv("LANGUAGE")
    }
    
    // 方法2: Windows 系统使用 GetUserDefaultUILanguage
    if runtime.GOOS == "windows" {
        // 使用 Windows API 获取系统语言
        dll := syscall.NewLazyDLL("kernel32.dll")
        proc := dll.NewProc("GetUserDefaultUILanguage")
        langID, _, _ := proc.Call()
        
        // 语言ID映射
        switch langID {
        case 0x0804: // 中文(简体)
            return LangZH
        case 0x0404: // 中文(繁体)
            return LangZH
        case 0x0422: // 越南语
            return LangVI
        default:
            return LangEN
        }
    }
    
    lang = strings.ToLower(lang)
    if strings.HasPrefix(lang, "zh") {
        return LangZH
    }
    if strings.HasPrefix(lang, "vi") {
        return LangVI
    }
    return LangEN
}

// SetLanguage 设置语言
func (i *I18nManager) SetLanguage(lang string) bool {
	if lang == LangZH || lang == LangVI || lang == LangEN {
		i.mu.Lock()
		i.currentLang = lang
		i.cache = make(map[string]string)
		i.mu.Unlock()
		logInfo("语言已切换: %s", lang)
		return true
	}
	return false
}

// GetText 获取文本
func (i *I18nManager) GetText(key string, args ...interface{}) string {
	i.mu.RLock()
	defer i.mu.RUnlock()

	cacheKey := i.currentLang + ":" + key
	if text, ok := i.cache[cacheKey]; ok {
		if len(args) > 0 {
			return fmt.Sprintf(text, args...)
		}
		return text
	}

	langMap, ok := i.texts[key]
	if !ok {
		return key
	}

	text, ok := langMap[i.currentLang]
	if !ok {
		text = langMap[LangEN]
	}

	i.cache[cacheKey] = text

	if len(args) > 0 {
		return fmt.Sprintf(text, args...)
	}
	return text
}

// GetCurrentLanguage 获取当前语言
func (i *I18nManager) GetCurrentLanguage() string {
	i.mu.RLock()
	defer i.mu.RUnlock()
	return i.currentLang
}

// GetText 全局获取文本函数
func GetText(key string, args ...interface{}) string {
	return GetI18nManager().GetText(key, args...)
}

// SetLanguage 全局设置语言
func SetLanguage(lang string) bool {
	return GetI18nManager().SetLanguage(lang)
}