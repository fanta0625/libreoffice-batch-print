# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from PySide6.QtWidgets import QMessageBox, QApplication
from PySide6.QtCore import Qt
from utils.i18n import _

class CustomMessageBox(QMessageBox):
    def __init__(self, icon, title, text, buttons, parent=None):
        super().__init__(icon, title, text, buttons, parent)
        self._ = _
        button_texts = {
            QMessageBox.StandardButton.Ok: _("MainWindow","btn_ok"),
            QMessageBox.StandardButton.Cancel: _("MainWindow","btn_cancel"),
            QMessageBox.StandardButton.Yes: _("MainWindow","btn_yes"),
            QMessageBox.StandardButton.No: _("MainWindow","btn_no"),
            QMessageBox.Abort: _("MainWindow","btn_abort"),
            QMessageBox.Retry: _("MainWindow","btn_retry"),
            QMessageBox.Ignore: _("MainWindow","btn_ignore")
        }

        # 遍历当前对话框包含的所有标准按钮
        standard_buttons = [QMessageBox.StandardButton.Ok, QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.No, 
                            QMessageBox.Abort, QMessageBox.Retry, QMessageBox.Ignore]
        
        for btn_enum in standard_buttons:
            # 检查当前对话框是否包含这个按钮
            if buttons & btn_enum:
                btn_obj = self.button(btn_enum)
                if btn_obj and btn_enum in button_texts:
                    # 设置文本
                    btn_obj.setText(button_texts[btn_enum])
