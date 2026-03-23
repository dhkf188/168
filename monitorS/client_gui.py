#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
员工监控系统 - 图形界面（多语言版）
"""

import tkinter as tk
from tkinter import ttk, messagebox
import socket
import getpass
import logging

from client_i18n import get_text, I18nManager


class FirstRunDialog:
    """首次运行配置对话框（多语言版）"""

    WINDOW_WIDTH = 580
    WINDOW_HEIGHT = 520
    THEME = "arc"
    DEFAULT_FONT = "微软雅黑"

    def __init__(self):
        self.logger = logging.getLogger(__name__)

        # 创建主窗口
        self.root = tk.Tk()
        self.root.title(get_text("config_title"))
        self.root.geometry(f"{self.WINDOW_WIDTH}x{self.WINDOW_HEIGHT}")
        self.root.resizable(False, False)

        # 设置窗口图标
        try:
            self.root.iconbitmap(default="icon.ico")
        except:
            pass

        self.center_window()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.employee_name = None
        self.result = None
        self.remember = True

        # 获取系统信息
        self.computer_name = socket.gethostname()
        self.windows_user = getpass.getuser()

        self.setup_styles()
        self.setup_ui()

    def center_window(self):
        """窗口居中"""
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() - self.WINDOW_WIDTH) // 2
        y = (self.root.winfo_screenheight() - self.WINDOW_HEIGHT) // 2
        self.root.geometry(f"+{x}+{y}")

    def setup_styles(self):
        """设置样式"""
        style = ttk.Style()

        style.configure(
            "Title.TLabel",
            font=(self.DEFAULT_FONT, 18, "bold"),
            foreground="#333"
        )

        style.configure(
            "Desc.TLabel",
            font=(self.DEFAULT_FONT, 10),
            foreground="#666"
        )

        style.configure(
            "Info.TLabel",
            font=("Consolas", 10),
            foreground="#555"
        )

        style.configure(
            "Confirm.TButton",
            font=(self.DEFAULT_FONT, 11, "bold"),
            padding=8
        )

        style.configure(
            "Cancel.TButton",
            font=(self.DEFAULT_FONT, 11),
            padding=8
        )

    def setup_ui(self):
        """设置UI"""
        main_frame = ttk.Frame(self.root, padding="30")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 标题
        title_label = ttk.Label(
            main_frame,
            text=get_text("config_welcome"),
            style="Title.TLabel"
        )
        title_label.pack(pady=(0, 15))

        # 说明
        desc_label = ttk.Label(
            main_frame,
            text=get_text("config_description"),
            style="Desc.TLabel",
            justify="center"
        )
        desc_label.pack(pady=(0, 25))

        # 输入区域
        input_frame = ttk.LabelFrame(
            main_frame,
            text=get_text("config_employee_info"),
            padding="15"
        )
        input_frame.pack(fill=tk.X, pady=(0, 20))

        # 姓名标签
        name_label = ttk.Label(
            input_frame,
            text=get_text("config_name"),
            font=(self.DEFAULT_FONT, 10),
            justify=tk.LEFT
        )
        name_label.grid(row=0, column=0, sticky=tk.W, pady=(0, 10))

        self.name_var = tk.StringVar(value=self.windows_user)

        self.name_entry = ttk.Entry(
            input_frame,
            textvariable=self.name_var,
            font=(self.DEFAULT_FONT, 11),
            width=35
        )
        self.name_entry.grid(row=1, column=0, sticky=tk.W, pady=(0, 5))
        self.name_entry.focus()
        self.name_entry.select_range(0, tk.END)

        # 提示
        hint_label = ttk.Label(
            input_frame,
            text=get_text("config_name_hint"),
            font=(self.DEFAULT_FONT, 9),
            foreground="#999"
        )
        hint_label.grid(row=2, column=0, sticky=tk.W)

        # 系统信息
        info_frame = ttk.LabelFrame(
            main_frame,
            text=get_text("config_system_info"),
            padding="15"
        )
        info_frame.pack(fill=tk.X, pady=(0, 25))

        info_text = (
            f"{get_text('config_computer_name')}：{self.computer_name}\n"
            f"{get_text('config_user_name')}：{self.windows_user}"
        )

        info_label = ttk.Label(
            info_frame,
            text=info_text,
            style="Info.TLabel",
            justify=tk.LEFT
        )
        info_label.pack(anchor=tk.W)

        # 记住选项
        self.remember_var = tk.BooleanVar(value=True)
        remember_check = ttk.Checkbutton(
            input_frame,
            text=get_text("config_remember"),
            variable=self.remember_var,
        )
        remember_check.grid(row=3, column=0, sticky=tk.W, pady=(10, 0))

        # 按钮
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X)

        cancel_btn = ttk.Button(
            button_frame,
            text=get_text("cancel"),
            style="Cancel.TButton",
            command=self.on_cancel,
            width=12,
        )
        cancel_btn.pack(side=tk.LEFT)

        confirm_btn = ttk.Button(
            button_frame,
            text=get_text("confirm"),
            style="Confirm.TButton",
            command=self.on_confirm,
            width=18,
        )
        confirm_btn.pack(side=tk.RIGHT)

        # 绑定事件
        self.root.bind("<Return>", lambda e: self.on_confirm())
        self.root.bind("<Escape>", lambda e: self.on_cancel())

    def on_confirm(self):
        """确定"""
        name = self.name_var.get().strip()

        if not name:
            messagebox.showwarning(
                get_text("config_warning_title"),
                get_text("config_warning_name_empty")
            )
            self.name_entry.focus()
            return

        if len(name) < 2:
            messagebox.showwarning(
                get_text("config_warning_title"),
                get_text("config_warning_name_short")
            )
            self.name_entry.focus()
            self.name_entry.select_range(0, tk.END)
            return

        self.employee_name = name
        self.result = name
        self.remember = self.remember_var.get()
        self.root.quit()
        self.root.destroy()

    def on_cancel(self):
        """取消"""
        if messagebox.askyesno(
            get_text("config_warning_title"),
            get_text("config_confirm_exit")
        ):
            self.result = None
            self.root.quit()
            self.root.destroy()

    def on_closing(self):
        """关闭窗口"""
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
        logging.getLogger(__name__).error(f"GUI启动失败: {e}")
        return None


if __name__ == "__main__":
    name = get_employee_name_gui()
    if name:
        print(f"✅ 输入的姓名: {name}")
    else:
        print("❌ 用户取消")