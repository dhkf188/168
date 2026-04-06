// client_gui_walk.go - 图形化首次配置对话框 (Walk实现)
//go:build windows
// +build windows

package main

import (
	"fmt"
	"os"
	"sync"
	"time"

	"github.com/lxn/walk"
	. "github.com/lxn/walk/declarative"
)

// FirstRunDialogGUI 图形化首次运行配置对话框
type FirstRunDialogGUI struct {
    dialog        *walk.Dialog
    nameEdit      *walk.LineEdit
    rememberCheck *walk.CheckBox
    employeeName  string
    result        string
    mu            sync.Mutex
    hardwareInfo  *HardwareInfo      // 使用 client_hardware.go 中的 HardwareInfo
    okButton      *walk.PushButton
    cancelButton  *walk.PushButton
}

// NewFirstRunDialogGUI 创建图形化配置对话框
func NewFirstRunDialogGUI() *FirstRunDialogGUI {
    return &FirstRunDialogGUI{}
}

// Run 运行图形化对话框
func (d *FirstRunDialogGUI) Run() string {
    // 确保在主线程中运行（walk 需要在主线程）
    result := make(chan string, 1)
    
    // 在 goroutine 中运行，但 walk 需要消息循环
    go func() {
        var dialog *walk.Dialog
        var nameEdit *walk.LineEdit
        var rememberCheck *walk.CheckBox
        var okButton *walk.PushButton
        var cancelButton *walk.PushButton
        
        // 获取硬件信息
        identifier := NewHardwareIdentifier()
        d.hardwareInfo = identifier.GetCompleteHardwareInfo()
        
        hostname, _ := os.Hostname()
        windowsUser := os.Getenv("USERNAME")
        
        // 创建对话框
        err := Dialog{
            AssignTo: &dialog,
            Title:    GetText("config_title"),
            MinSize:  Size{Width: 550, Height: 500},
            Size:     Size{Width: 600, Height: 550},
            Layout:   VBox{},
            Children: []Widget{
                Label{
                    Text: GetText("config_welcome"),
                    Font: Font{PointSize: 12, Bold: true},
                },
                HSpacer{},
                GroupBox{
                    Title:  GetText("config_employee_info"),
                    Layout: Grid{Columns: 2, MarginsZero: false, Spacing: 5},
                    Children: []Widget{
                        Label{Text: GetText("config_name") + ":"},
                        LineEdit{
                            AssignTo: &nameEdit,
                            MinSize:  Size{Width: 250, Height: 0},
                            OnKeyPress: func(key walk.Key) {
                                if key == walk.KeyReturn {
                                    d.handleOK(okButton, dialog, nameEdit)
                                }
                            },
                        },
                        Label{Text: ""},
                        CheckBox{
                            AssignTo: &rememberCheck,
                            Text:     GetText("config_remember"),
                            Checked:  true,
                        },
                    },
                },
                GroupBox{
                    Title:  GetText("config_system_info"),
                    Layout: Grid{Columns: 2, MarginsZero: false},
                    Children: []Widget{
                        Label{Text: GetText("config_computer_name") + ":"},
                        Label{Text: hostname},
                        Label{Text: GetText("config_user_name") + ":"},
                        Label{Text: windowsUser},
                    },
                },
                d.createHardwareGroupBox(),
                Composite{
                    Layout: HBox{Spacing: 10},
                    Children: []Widget{
                        HSpacer{},
                        PushButton{
                            AssignTo: &okButton,
                            Text:     GetText("ok"),
                            MinSize:  Size{Width: 80, Height: 0},
                            OnClicked: func() {
                                d.handleOK(okButton, dialog, nameEdit)
                            },
                        },
                        PushButton{
                            AssignTo: &cancelButton,
                            Text:     GetText("cancel"),
                            MinSize:  Size{Width: 80, Height: 0},
                            OnClicked: func() {
                                dialog.Cancel()
                            },
                        },
                        HSpacer{},
                    },
                },
                VSpacer{Size: 10},
            },
            DefaultButton: &okButton,
            CancelButton:  &cancelButton,
        }.Create(nil)
        
        if err != nil {
            logError("创建对话框失败: %v", err)
            result <- ""
            return
        }
        
        d.dialog = dialog
        d.nameEdit = nameEdit
        d.rememberCheck = rememberCheck
        d.okButton = okButton
        d.cancelButton = cancelButton
        
        if nameEdit != nil {
            nameEdit.SetFocus()
        }
        
        // 运行对话框
        ret := dialog.Run()
        
        if ret == walk.DlgCmdOK {
            result <- d.result
        } else {
            result <- ""
        }
    }()
    
    // 等待结果，超时 60 秒
    select {
    case name := <-result:
        return name
    case <-time.After(60 * time.Second):
        logError("对话框超时")
        return ""
    }
}

// handleOK 处理OK按钮点击
func (d *FirstRunDialogGUI) handleOK(okButton *walk.PushButton, dialog *walk.Dialog, nameEdit *walk.LineEdit) {
    if nameEdit == nil {
        return
    }
    
    name := nameEdit.Text()
    if name == "" {
        walk.MsgBox(dialog, GetText("config_title"), 
            "姓名不能为空，请输入您的姓名。", 
            walk.MsgBoxIconError)
        return
    }
    
    d.mu.Lock()
    d.employeeName = name
    d.result = name
    d.mu.Unlock()
    
    // 保存配置
    if d.rememberCheck != nil && d.rememberCheck.Checked() {
        // 配置将在主程序中保存
    }
    
    dialog.Accept()
}

// createHardwareGroupBox 创建硬件信息区域
func (d *FirstRunDialogGUI) createHardwareGroupBox() Widget {
    reliabilityText := "低"
    if d.hardwareInfo.Reliability > 0.7 {
        reliabilityText = "高"
    } else if d.hardwareInfo.Reliability > 0.4 {
        reliabilityText = "中"
    }
    
    fingerprintShort := d.hardwareInfo.Fingerprint
    if len(fingerprintShort) > 16 {
        fingerprintShort = fingerprintShort[:16] + "..."
    }
    
    cpuNameShort := d.hardwareInfo.CPUName
    if len(cpuNameShort) > 40 {
        cpuNameShort = cpuNameShort[:37] + "..."
    }
    
    return GroupBox{
        Title:  GetText("hardware_info"),
        Layout: Grid{Columns: 2, MarginsZero: false, Spacing: 5},
        Children: []Widget{
            Label{Text: GetText("hardware_cpu") + ":"},
            Label{Text: cpuNameShort},
            Label{Text: GetText("hardware_motherboard") + ":"},
            Label{Text: d.hardwareInfo.MotherboardModel},
            Label{Text: GetText("hardware_disk") + ":"},
            Label{Text: d.hardwareInfo.DiskModel},
            Label{Text: GetText("hardware_fingerprint") + ":"},
            Label{Text: fingerprintShort},
            Label{Text: GetText("hardware_reliability") + ":"},
            Label{Text: fmt.Sprintf("%s (%.0f%%)", reliabilityText, d.hardwareInfo.Reliability*100)},
        },
    }
}