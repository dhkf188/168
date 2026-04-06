package main

import (
	"bufio"
	"fmt"
	"os"
	"runtime"
	"strings"
	"time"

	"golang.org/x/sys/windows/registry"
)

// 语言检测（兼容所有 Windows 版本）
func detectLanguage() string {
    if runtime.GOOS == "windows" {
        // 方法1：通过环境变量
        lang := os.Getenv("LANG")
        if lang != "" {
            lang = strings.ToLower(lang)
            if strings.HasPrefix(lang, "zh") {
                return "zh"
            }
            if strings.HasPrefix(lang, "vi") {
                return "vi"
            }
        }
        
        // 方法2：通过注册表获取系统语言
        k, err := registry.OpenKey(registry.CURRENT_USER, 
            `Control Panel\International`, 
            registry.READ)
        if err == nil {
            defer k.Close()
            
            locale, _, err := k.GetStringValue("LocaleName")
            if err == nil {
                if strings.HasPrefix(locale, "zh") {
                    return "zh"
                }
                if strings.HasPrefix(locale, "vi") {
                    return "vi"
                }
            }
        }
    }
    return "en"
}

// 多语言文本
func getText(key string) string {
    lang := detectLanguage()
    
    texts := map[string]map[string]string{
        "title": {
            "zh": "员工监控系统",
            "vi": "Hệ thống giám sát nhân viên",
            "en": "Employee Monitor System",
        },
        "first_config": {
            "zh": "首次配置",
            "vi": "Cấu hình lần đầu",
            "en": "First Time Setup",
        },
        "name_prompt": {
            "zh": "请输入您的姓名",
            "vi": "Vui lòng nhập tên của bạn",
            "en": "Please enter your name",
        },
        "press_enter": {
            "zh": "请输入姓名后按 [Enter] 键确认",
            "vi": "Vui lòng nhập tên và nhấn [Enter] để xác nhận",
            "en": "Please enter your name and press [Enter] to confirm",
        },
        "default": {
            "zh": "默认",
            "vi": "Mặc định",
            "en": "Default",
        },
        "success": {
            "zh": "已设置员工姓名",
            "vi": "Đã đặt tên nhân viên",
            "en": "Employee name set",
        },
        "auto_hide": {
            "zh": "程序将在3秒后启动，控制台将自动隐藏",
            "vi": "Chương trình sẽ khởi động sau 3 giây, console sẽ tự động ẩn",
            "en": "Program will start in 3 seconds, console will auto-hide",
        },
        "system_info": {
            "zh": "系统信息",
            "vi": "Thông tin hệ thống",
            "en": "System Info",
        },
        "computer_name": {
            "zh": "计算机名",
            "vi": "Tên máy tính",
            "en": "Computer name",
        },
        "user_name": {
            "zh": "用户名",
            "vi": "Tên người dùng",
            "en": "Username",
        },
        "hardware_info": {
            "zh": "硬件信息",
            "vi": "Thông tin phần cứng",
            "en": "Hardware Info",
        },
        "cpu": {
            "zh": "CPU",
            "vi": "CPU",
            "en": "CPU",
        },
        "motherboard": {
            "zh": "主板",
            "vi": "Bo mạch chủ",
            "en": "Motherboard",
        },
        "disk": {
            "zh": "磁盘",
            "vi": "Đĩa cứng",
            "en": "Disk",
        },
        "fingerprint": {
            "zh": "硬件指纹",
            "vi": "Dấu vân tay phần cứng",
            "en": "Hardware Fingerprint",
        },
        "reliability": {
            "zh": "可信度",
            "vi": "Độ tin cậy",
            "en": "Reliability",
        },
        "unknown": {
            "zh": "无法获取",
            "vi": "Không thể lấy",
            "en": "Unknown",
        },
        "high": {
            "zh": "高",
            "vi": "Cao",
            "en": "High",
        },
        "medium": {
            "zh": "中",
            "vi": "Trung bình",
            "en": "Medium",
        },
        "low": {
            "zh": "低",
            "vi": "Thấp",
            "en": "Low",
        },
    }
    
    if m, ok := texts[key]; ok {
        if t, ok := m[lang]; ok {
            return t
        }
        return texts[key]["en"]
    }
    return key
}

// hideConsole 隐藏控制台窗口（使用 client_win.go 中的函数）
func hideConsole() {
    if runtime.GOOS == "windows" {
        hwnd := GetConsoleWindow()
        if hwnd != 0 {
            ShowWindow(hwnd, 0) // SW_HIDE = 0
        }
    }
}

// 绘制分隔线
func drawLine(char string, length int) {
    for i := 0; i < length; i++ {
        fmt.Print(char)
    }
    fmt.Println()
}

// 居中文本辅助函数
func centerText(text string, width int) string {
    textLen := len([]rune(text))
    if textLen >= width {
        return text
    }
    padding := (width - textLen) / 2
    return strings.Repeat(" ", padding) + text
}

// GetEmployeeNameGUI 获取员工姓名（多语言版本）
func GetEmployeeNameGUI() string {
    // 清屏
    fmt.Print("\033[2J\033[H")
    
    width := 50
    
    // 标题
    fmt.Println()
    drawLine("=", width)
    fmt.Printf("%s\n", centerText(getText("title"), width))
    drawLine("=", width)
    fmt.Println()
    fmt.Printf("  %s\n", centerText(getText("first_config"), width))
    fmt.Println()
    drawLine("-", width)
    
    // 系统信息
    fmt.Println()
    fmt.Printf("  %s:\n", getText("system_info"))
    computerName, _ := os.Hostname()
    fmt.Printf("    %s: %s\n", getText("computer_name"), computerName)
    userName := os.Getenv("USERNAME")
    if userName == "" {
        userName = os.Getenv("USER")
    }
    fmt.Printf("    %s: %s\n", getText("user_name"), userName)
    
    // 硬件信息
    fmt.Println()
    fmt.Printf("  %s:\n", getText("hardware_info"))
    
    // 安全获取硬件信息
    func() {
        defer func() {
            if r := recover(); r != nil {
                fmt.Printf("    %s: %s\n", getText("cpu"), getText("unknown"))
                fmt.Printf("    %s: %s\n", getText("motherboard"), getText("unknown"))
                fmt.Printf("    %s: %s\n", getText("disk"), getText("unknown"))
            }
        }()
        
        identifier := NewHardwareIdentifier()
        info := identifier.GetCompleteHardwareInfo()
        
        if info != nil {
            cpuName := info.CPUName
            if len(cpuName) > 35 {
                cpuName = cpuName[:32] + "..."
            }
            if cpuName == "" {
                cpuName = getText("unknown")
            }
            fmt.Printf("    %s: %s\n", getText("cpu"), cpuName)
            
            mb := info.MotherboardModel
            if mb == "" {
                mb = getText("unknown")
            }
            fmt.Printf("    %s: %s\n", getText("motherboard"), mb)
            
            disk := info.DiskModel
            if disk == "" {
                disk = getText("unknown")
            }
            fmt.Printf("    %s: %s\n", getText("disk"), disk)
            
            fingerprint := info.Fingerprint
            if len(fingerprint) > 20 {
                fingerprint = fingerprint[:17] + "..."
            }
            if fingerprint == "" {
                fingerprint = getText("unknown")
            }
            fmt.Printf("    %s: %s\n", getText("fingerprint"), fingerprint)
            
            reliabilityText := getText("low")
            if info.Reliability > 0.7 {
                reliabilityText = getText("high")
            } else if info.Reliability > 0.4 {
                reliabilityText = getText("medium")
            }
            fmt.Printf("    %s: %s (%.0f%%)\n", getText("reliability"), reliabilityText, info.Reliability*100)
        }
    }()
    
    fmt.Println()
    drawLine("-", width)
    
    // 姓名输入 - 国际化版本
    fmt.Println()
    
    defaultName := userName
    if defaultName == "" {
        defaultName = "Employee"
    }
    
    // 显示输入提示（国际化）
    fmt.Printf("  %s (%s: %s):\n", getText("name_prompt"), getText("default"), defaultName)
    fmt.Printf("  %s\n", getText("press_enter"))
    fmt.Print("  → ")
    
    // 强制刷新输出缓冲区
    os.Stdout.Sync()
    
    // 创建读取器并读取输入
    reader := bufio.NewReader(os.Stdin)
    
    // 读取输入
    name, _ := reader.ReadString('\n')
    name = strings.TrimSpace(name)
    
    if name == "" {
        name = defaultName
    }
    
    // 完成
    fmt.Println()
    drawLine("=", width)
    fmt.Printf("  ✓ %s: %s\n", getText("success"), name)
    drawLine("=", width)
    
    fmt.Println()
    fmt.Printf("  %s\n", getText("auto_hide"))
    fmt.Println()
    
    time.Sleep(3 * time.Second)
    hideConsole()
    
    return name
}

// 兼容旧代码
type FirstRunDialog struct{}

func NewFirstRunDialog() *FirstRunDialog {
    return &FirstRunDialog{}
}

func (d *FirstRunDialog) Run() string {
    return GetEmployeeNameGUI()
}