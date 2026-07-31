# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import os
import sys
import argparse
from PySide6.QtWidgets import QApplication

class ContextMenuHandler:
    """处理从右键菜单传入的文件"""

    @staticmethod
    def parse_arguments():
        """解析命令行参数"""
        parser = argparse.ArgumentParser(description='LibreOffice批量打印工具')
        parser.add_argument('files', nargs='+', help='要打印的文件列表')
        parser.add_argument('--silent', action='store_true',
                           help='静默打印，不显示界面')
        parser.add_argument('--printer', help='指定打印机名称')
        parser.add_argument('--copies', type=int, default=1, help='打印份数')

        return parser.parse_args()

    @staticmethod
    def is_called_from_context_menu():
        """判断是否从右键菜单调用"""
        # 检查特定环境变量（Windows资源管理器）
        if os.name == 'nt':
            return len(sys.argv) > 1 and os.path.exists(sys.argv[1])

        # Linux Nautilus
        if 'NAUTILUS_SCRIPT_SELECTED_FILE_PATHS' in os.environ:
            return True

        return len(sys.argv) > 1

    def handle(self):
        """主处理逻辑"""
        args = self.parse_arguments()

        if args.silent:
            # 静默模式：直接打印，不显示界面
            self.print_silently(args.files, args.printer, args.copies)
        else:
            # 显示界面模式
            self.show_gui(args.files)

    def print_silently(self, files, printer, copies):
        """静默打印"""
        # 启动LibreOffice服务
        manager = LibreOfficeManager()
        if not manager.ensure_running():
            print("无法启动LibreOffice")
            return

        # 连接并打印
        printer_client = LibreOfficePrinter()
        if printer_client.connect():
            for file_path in files:
                printer_client.print_document(file_path, printer, copies)

        # 清理
        manager.stop_office()

    def show_gui(self, files):
        """显示打印界面"""
        app = QApplication(sys.argv)

        # 创建主窗口并传入文件列表
        window = BatchPrintWindow(files)
        window.show()

        sys.exit(app.exec())


# 程序入口
if __name__ == "__main__":
    handler = ContextMenuHandler()

    # 如果是从命令行直接运行的
    if len(sys.argv) > 1:
        handler.handle()
    else:
        # 正常启动GUI（无文件参数）
        app = QApplication(sys.argv)
        window = BatchPrintWindow()
        window.show()
        sys.exit(app.exec())
