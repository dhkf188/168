# client_gui.py（多语言优化版）
"""
客户端图形界面 - 首次运行配置窗口（多语言版）
"""

import tkinter as tk
from tkinter import ttk, messagebox
from ttkthemes import ThemedTk
import socket
import getpass
import locale


class FirstRunDialog:
    """首次运行配置对话框（多语言版）"""

    # 配置常量
    WINDOW_WIDTH = 580  # 加宽以容纳多语言文本
    WINDOW_HEIGHT = 520  # 加高以容纳多语言文本
    THEME = "arc"
    DEFAULT_FONT = "微软雅黑"

    def __init__(self):
        self.root = ThemedTk(theme=self.THEME)
        self.root.title("员工监控系统 - 首次配置")
        self.root.geometry(f"{self.WINDOW_WIDTH}x{self.WINDOW_HEIGHT}")
        self.root.resizable(False, False)

        # 检测系统语言
        self.system_lang = self.detect_language()

        # 设置窗口图标
        try:
            self.root.iconbitmap(default="icon.ico")
        except:
            pass

        self.center_window()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.employee_name = None
        self.result = None

        # 获取系统信息
        self.computer_name = socket.gethostname()
        self.windows_user = getpass.getuser()

        self.setup_styles()
        self.setup_ui()

    def detect_language(self):
        """检测系统语言"""
        try:
            # 获取系统语言
            lang, _ = locale.getdefaultlocale()
            if lang:
                if lang.startswith("zh"):
                    return "zh"  # 中文
                elif lang.startswith("vi"):
                    return "vi"  # 越南语
                elif lang.startswith("en"):
                    return "en"  # 英语
        except:
            pass
        return "en"  # 默认英语

    def center_window(self):
        """窗口居中"""
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() - self.WINDOW_WIDTH) // 2
        y = (self.root.winfo_screenheight() - self.WINDOW_HEIGHT) // 2
        self.root.geometry(f"+{x}+{y}")

    def setup_styles(self):
        """设置自定义样式"""
        style = ttk.Style()

        style.configure(
            "Title.TLabel", font=(self.DEFAULT_FONT, 18, "bold"), foreground="#333"
        )

        style.configure("Desc.TLabel", font=(self.DEFAULT_FONT, 10), foreground="#666")

        style.configure("Info.TLabel", font=("Consolas", 10), foreground="#555")

        # 确定按钮样式
        style.configure(
            "Confirm.TButton", font=(self.DEFAULT_FONT, 11, "bold"), padding=8
        )

        style.configure("Cancel.TButton", font=(self.DEFAULT_FONT, 11), padding=8)

    def setup_ui(self):
        """设置UI界面"""
        main_frame = ttk.Frame(self.root, padding="30")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 标题
        title_label = ttk.Label(
            main_frame, text=self.get_text("title"), style="Title.TLabel"
        )
        title_label.pack(pady=(0, 15))

        # 说明文字
        desc_label = ttk.Label(
            main_frame,
            text=self.get_text("description"),
            style="Desc.TLabel",
            justify="center",
        )
        desc_label.pack(pady=(0, 25))

        # 姓名输入区域
        input_frame = ttk.LabelFrame(
            main_frame, text=self.get_text("employee_info"), padding="15"
        )
        input_frame.pack(fill=tk.X, pady=(0, 20))

        # 姓名标签 - 使用多行显示
        name_label_text = self.get_text("name_label")
        name_label = ttk.Label(
            input_frame,
            text=name_label_text,
            font=(self.DEFAULT_FONT, 10),
            justify=tk.LEFT,
        )
        name_label.grid(row=0, column=0, sticky=tk.W, pady=(0, 10))

        self.name_var = tk.StringVar(value=self.windows_user)

        self.name_entry = ttk.Entry(
            input_frame,
            textvariable=self.name_var,
            font=(self.DEFAULT_FONT, 11),
            width=35,  # 加宽输入框
        )
        self.name_entry.grid(row=1, column=0, sticky=tk.W, pady=(0, 5))
        self.name_entry.focus()
        self.name_entry.select_range(0, tk.END)

        # 提示信息 - 三语言
        hint_text = self.get_text("name_hint")
        hint_label = ttk.Label(
            input_frame,
            text=hint_text,
            font=(self.DEFAULT_FONT, 9),
            foreground="#999",
        )
        hint_label.grid(row=2, column=0, sticky=tk.W)

        # 系统信息区域
        info_frame = ttk.LabelFrame(
            main_frame, text=self.get_text("system_info"), padding="15"
        )
        info_frame.pack(fill=tk.X, pady=(0, 25))

        info_text = f"{self.get_text('computer_name')}：{self.computer_name}\n{self.get_text('user_name')}：{self.windows_user}"

        info_label = ttk.Label(
            info_frame, text=info_text, style="Info.TLabel", justify=tk.LEFT
        )
        info_label.pack(anchor=tk.W)

        self.remember_var = tk.BooleanVar(value=True)
        remember_check = ttk.Checkbutton(
            input_frame,
            text="记住此姓名，不再显示",
            variable=self.remember_var,
        )
        remember_check.grid(row=3, column=0, sticky=tk.W, pady=(10, 0))

        # 按钮区域
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X)

        # 取消按钮（左）
        cancel_btn = ttk.Button(
            button_frame,
            text=self.get_text("cancel"),
            style="Cancel.TButton",
            command=self.on_cancel,
            width=12,
        )
        cancel_btn.pack(side=tk.LEFT)

        # 确定按钮（右）- 显示三语言
        confirm_btn = ttk.Button(
            button_frame,
            text=self.get_text("confirm"),
            style="Confirm.TButton",
            command=self.on_confirm,
            width=18,  # 加宽以适应多语言
        )
        confirm_btn.pack(side=tk.RIGHT)

        # 绑定事件
        self.root.bind("<Return>", lambda e: self.on_confirm())
        self.root.bind("<Escape>", lambda e: self.on_cancel())

    def get_text(self, key, lang=None):
        """获取指定语言的文本"""
        texts = {
            # 窗口标题
            "window_title": {
                "zh": "员工监控系统 - 首次配置",
                "vi": "Hệ thống giám sát nhân viên - Cấu hình lần đầu",
                "en": "Employee Monitoring System - First Setup",
            },
            # 标题
            "title": {
                "zh": "🎉 欢迎使用员工监控系统",
                "vi": "🎉 Chào mừng đến với Hệ thống giám sát nhân viên",
                "en": "🎉 Welcome to Employee Monitoring System",
            },
            # 说明文字
            "description": {
                "zh": "首次运行需要配置员工信息\n这些信息将用于员工识别，可在后台管理系统中修改",
                "vi": "Cần cấu hình thông tin nhân viên khi chạy lần đầu\nThông tin này sẽ được dùng để nhận dạng nhân viên, có thể sửa trong hệ thống quản lý",
                "en": "First run requires employee information\nThis information will be used for employee identification and can be modified in the admin system",
            },
            # 员工信息标签
            "employee_info": {
                "zh": "员工信息",
                "vi": "Thông tin nhân viên",
                "en": "Employee Information",
            },
            # 姓名标签
            "name_label": {"zh": "您的姓名", "vi": "Tên của bạn", "en": "Your name"},
            # 姓名提示
            "name_hint": {
                "zh": "例如：张三",
                "vi": "Ví dụ：Nguyễn Văn A",
                "en": "Example：John Smith",
            },
            # 系统信息
            "system_info": {
                "zh": "系统信息",
                "vi": "Thông tin hệ thống",
                "en": "System Information",
            },
            # 计算机名
            "computer_name": {
                "zh": "计算机名",
                "vi": "Tên máy tính",
                "en": "Computer name",
            },
            # 用户名
            "user_name": {"zh": "用户名", "vi": "Tên người dùng", "en": "Username"},
            # 按钮
            "confirm": {"zh": "确定", "vi": "Xác nhận", "en": "Confirm"},
            "cancel": {"zh": "取消", "vi": "Hủy", "en": "Cancel"},
            # 警告消息
            "warning_title": {"zh": "提示", "vi": "Thông báo", "en": "Warning"},
            "name_empty": {
                "zh": "请输入您的姓名",
                "vi": "Vui lòng nhập tên của bạn",
                "en": "Please enter your name",
            },
            "name_too_short": {
                "zh": "姓名至少需要2个字符",
                "vi": "Tên phải có ít nhất 2 ký tự",
                "en": "Name must be at least 2 characters",
            },
            "confirm_exit": {
                "zh": "是否退出配置？\n\n退出后将使用默认名称，您可以在后台修改。",
                "vi": "Bạn có muốn thoát cấu hình？\n\nSau khi thoát sẽ sử dụng tên mặc định, bạn có thể sửa trong hệ thống quản lý。",
                "en": "Exit configuration？\n\nDefault name will be used, you can modify it in the admin system。",
            },
        }

        if lang is None:
            lang = self.system_lang

        return texts.get(key, {}).get(lang, texts[key]["en"])

    def on_confirm(self):
        """确定按钮点击"""
        name = self.name_var.get().strip()

        if not name:
            messagebox.showwarning(
                self.get_text("warning_title"), self.get_text("name_empty")
            )
            self.name_entry.focus()
            return

        if len(name) < 2:
            messagebox.showwarning(
                self.get_text("warning_title"), self.get_text("name_too_short")
            )
            self.name_entry.focus()
            self.name_entry.select_range(0, tk.END)
            return

        self.employee_name = name
        self.result = name
        self.remember = self.remember_var.get()  # 保存选择
        self.root.quit()
        self.root.destroy()

    def on_cancel(self):
        """取消按钮点击"""
        if messagebox.askyesno(
            self.get_text("warning_title"), self.get_text("confirm_exit")
        ):
            self.result = None
            self.root.quit()
            self.root.destroy()

    def on_closing(self):
        """窗口关闭事件"""
        self.on_cancel()

    def run(self):
        """运行对话框"""
        self.root.mainloop()
        try:
            self.root.destroy()
        except:
            pass
        return self.result


def get_employee_name_gui():
    """通过GUI获取员工姓名"""
    try:
        dialog = FirstRunDialog()
        return dialog.run()
    except Exception as e:
        print(f"GUI界面启动失败: {e}")
        return None


if __name__ == "__main__":
    name = get_employee_name_gui()
    if name:
        print(f"✅ 输入的姓名: {name}")
    else:
        print("❌ 用户取消")
