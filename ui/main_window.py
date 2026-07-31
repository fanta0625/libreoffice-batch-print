# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import os
import random
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QTableWidget, QTableWidgetItem, QFileDialog, QMessageBox,
    QAbstractItemView, QHeaderView,QLineEdit,QSpinBox,QProgressBar,QCheckBox,QComboBox,QListView
)
from PySide6.QtCore import Qt,QThread, QMutex, QTimer,QSize,QRegularExpression
from PySide6.QtGui import QColor,QFont,QIcon,QRegularExpressionValidator

from models.file_model import FileItem, PrintParams,PresentationPrintOptions,ExcelPrintOptions,ExcelPrintMode
from services.file_service import FileService
from services.stats_service import StatsService
from services.task_manager import task_manager,TaskStatus
from ui.components import CustomHeaderView, CustomDelegateCell,CenteredCheckBoxDelegate
from ui.settings_dialog import SettingsDialog
from config.settings import STYLESHEET, FLAT_FILE_TYPES
from utils.paper_utils import DocumentHelper
from utils.status_type import StatusType
from utils.custom_message_box import CustomMessageBox
from utils.i18n import _
from functools import partial

from log.logger import get_logger
logger = get_logger("MainWindow")

class MainWindow(QMainWindow):
    def __init__(self,initial_files=None):
        super().__init__()
        logger.info("MainWindow initialization")
        self.setWindowTitle(_("MainWindow", "window_title"))
        self.setGeometry(100, 100, 900, 600)
        self.center()
        self.setStyleSheet(STYLESHEET)

        # 用于暂存启动时的错误信息
        self._pending_invalid_files_message = None

        # 用于顺序处理的队列和状态 ---
        self.pending_rows = []          # 待处理的行号列表
        self.is_processing = False      # 是否正在处理（锁）
        self.current_timer = None       # 存储当前活跃的定时器，方便清理

        # 数据模型
        self.file_items: list[FileItem] = []
        self.current_file_list = []
        self.header_checkbox_state = Qt.CheckState.Checked

        # 状态栏 (显示 LO 连接状态)
        self.status_bar_label = QLabel(_("MainWindow", "status_initializing"))
        self.status_bar_label.setObjectName("statusLabel")
        self.status_bar_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        self.init_ui()

        # 连接任务管理器信号
        task_manager.status_message.connect(self.update_status_bar)
        task_manager.page_count_ready.connect(self.on_page_count_ready)
        task_manager.task_status_changed.connect(self.on_task_status_update)

        # 如果有初始文件，延迟加载以等待 UI 显示
        if initial_files:
            logger.info(f"Received  {len(initial_files)} initial files at startup")
            QTimer.singleShot(500, lambda: self.add_files_list(initial_files))

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10) # 底部留给状态栏

        # 列表容器
        list_container = QWidget()
        list_container.setObjectName("listContainer")
        list_layout = QVBoxLayout(list_container)
        list_layout.setContentsMargins(10, 10, 10, 10)
        list_layout.setSpacing(10)

        # 工具栏
        toolbar_layout = QHBoxLayout()
        self.btn_add = QPushButton(_("MainWindow", "btn_add_file"))
        self.btn_add.setObjectName("btnAddFile")
        self.btn_add.setIcon(QIcon(":/images/resources/add.png"))
        self.btn_add.setIconSize(QSize(18,18))

        self.btn_folder = QPushButton(_("MainWindow", "btn_add_folder"))
        self.btn_folder.setObjectName("btnAddFolder")
        self.btn_folder.setIcon(QIcon(":/images/resources/folder.png"))
        self.btn_folder.setIconSize(QSize(19,20))

        self.btn_del = QPushButton(_("MainWindow", "btn_delete_selected"))
        self.btn_del.setObjectName("btnDelFile")
        self.btn_del.setIcon(QIcon(":/images/resources/dustbin.png"))
        self.btn_del.setIconSize(QSize(20,19))
        for btn in [self.btn_add, self.btn_folder, self.btn_del]:
            btn.setCursor(Qt.PointingHandCursor)

        self.btn_add.clicked.connect(lambda: self.add_files('file'))
        self.btn_folder.clicked.connect(lambda: self.add_files('folder'))
        self.btn_del.clicked.connect(self.delete_selected)

        toolbar_layout.addWidget(self.btn_add)
        toolbar_layout.addWidget(self.btn_folder)
        toolbar_layout.addWidget(self.btn_del)
        toolbar_layout.addStretch()

        self.list_status_label = QLabel(_("MainWindow", "list_status_ready").format(count=0))
        self.list_status_label.setObjectName("listStatusLabel")
        toolbar_layout.addWidget(self.list_status_label)

        list_layout.addLayout(toolbar_layout)
        # list_layout.addWidget(self.list_status_label)

        self.file_table = self.create_file_table()
        list_layout.addWidget(self.file_table)

        main_layout.addWidget(list_container, 1)

        # 底部按钮
        bottom_container = QWidget()
        bottom_container.setObjectName("bottomContainer")
        bottom_layout = QHBoxLayout(bottom_container)
        bottom_layout.setContentsMargins(5, 3, 0, 10)
        bottom_layout.addWidget(self.status_bar_label)
        bottom_layout.addStretch()

        self.btn_print = QPushButton(_("MainWindow", "btn_print"))
        self.btn_print.setObjectName("btnPrint")
        self.btn_print.setMinimumSize(110, 36)
        self.btn_print.setCursor(Qt.PointingHandCursor)
        self.btn_print.clicked.connect(self.start_batch_print)
        self.btn_print.setEnabled(False)

        self.btn_close = QPushButton(_("MainWindow", "btn_cancel"))
        self.btn_close.setObjectName("btnClose")
        self.btn_close.setMinimumSize(80, 36)
        self.btn_close.setCursor(Qt.PointingHandCursor)
        self.btn_close.clicked.connect(self.close)

        bottom_layout.addWidget(self.btn_print)
        bottom_layout.addWidget(self.btn_close)
        main_layout.addWidget(bottom_container)

    def create_file_table(self):
        table = QTableWidget()
        headers = [ 
            _("MainWindow", "header_checkbox"),
            _("MainWindow", "header_filename"),
            _("MainWindow", "header_total_pages"),
            _("MainWindow", "header_print_range"),
            _("MainWindow", "header_copies"),
            _("MainWindow", "header_status"),
            _("MainWindow", "header_actions")
        ]
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)

        header = CustomHeaderView(Qt.Orientation.Horizontal, table)
        table.setHorizontalHeader(header)

        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Interactive)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.Fixed)
        header.setSectionResizeMode(6, QHeaderView.Fixed)

        table.setColumnWidth(0, 50)
        table.setColumnWidth(2, 70)
        table.setColumnWidth(3, 120)
        table.setColumnWidth(4, 90)
        table.setColumnWidth(5, 160)
        table.setColumnWidth(6, 80)

        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.NoSelection)
        table.setFocusPolicy(Qt.NoFocus) 
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.setMouseTracking(True)
        # table.setAlternatingRowColors(True)
        table.setShowGrid(False)
        table.verticalHeader().setDefaultSectionSize(50)

        self.header_checkbox = QCheckBox(table)
        self.header_checkbox.resize(40, 50)
        table.setCellWidget(0,0,self.header_checkbox)
        self.header_checkbox.setStyleSheet("margin-left:13px;margin-top:12px;")
        self.header_checkbox.setChecked(False)
        self.header_checkbox.stateChanged.connect(self.on_header_checkbox_changed)

        QTimer.singleShot(100, lambda: header.viewport().update())

        table.setItemDelegateForColumn(0, CenteredCheckBoxDelegate(table))

        table.itemChanged.connect(self.on_item_changed)

        return table

    def center(self):
        """将窗口移动到屏幕中央"""
        frame_geometry = self.frameGeometry()
        # 获取包含当前窗口的屏幕的中心点
        screen_center = self.screen().availableGeometry().center()
        frame_geometry.moveCenter(screen_center)
        self.move(frame_geometry.topLeft())

    def eventFilter(self, source, event):
        if (source is self.file_table.viewport() 
            and event.type() == event.MouseMove):
            pos = event.pos()
            row = self.file_table.rowAt(pos.y())
            if row != self.hover_row:
                old_row = self.hover_row
                self.hover_row = row
                # 刷新旧行和新行
                if old_row >= 0:
                    self.file_table.viewport().update(
                        self.file_table.visualRect(self.file_table.model().index(old_row, 0))
                    )
                if row >= 0:
                    self.file_table.viewport().update(
                        self.file_table.visualRect(self.file_table.model().index(row, 0))
                    )
        return super().eventFilter(source, event)

    def on_item_changed(self, item: QTableWidgetItem):
        # 更新 header checkbox status
        if item.column() == 0:
            QTimer.singleShot(100, self.refresh_ui_status) 

    def update_status_bar(self, res):
        self.status_bar_label.setText(_("LoStatus",f"{res.message}"))
        self.status_bar_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        if res.type == StatusType.ERROR:
            self.status_bar_label.setStyleSheet("color: #d9534f;")
        elif res.type == StatusType.SUCCESS:
            self.status_bar_label.setStyleSheet("color: #28a745;")
        else:
            self.status_bar_label.setStyleSheet("color: #0078D4;")

    def add_files(self, mode):
        logger.debug(f"User triggered add file operation: mode={mode}")
        files = []
        if mode == 'file':
            file_filter = DocumentHelper.getFileFilter()
            files, _filter = QFileDialog.getOpenFileNames(self, _("MainWindow", "dialog_select_document"), "", file_filter)
        elif mode == 'folder':
            folder = QFileDialog.getExistingDirectory(self, _("MainWindow", "dialog_select_folder"))
            if folder:
                files = FileService.scan_folder(folder)
        
        if files:
            logger.info(f"User added {len(files)} files")
            self.add_files_list(files)

    def add_files_list(self, files):
        if not files:
            return

        start_row = self.file_table.rowCount()
        
        # 用于存储校验通过的有效文件
        valid_files = []
        # 用于存储校验失败的文件及其原因
        invalid_files = {}

        for i, path in enumerate(files):
            if any(item.file_path == path for item in self.file_items):
                continue

            # 指纹校验
            is_valid, message = DocumentHelper.check_file_type(path)
            if is_valid:
                valid_files.append(path)
            else:
                invalid_files[path] = message

        # 处理有效文件
        for i, path in enumerate(valid_files):
            row_id = start_row + i
            f_type = FileService.get_file_type(path)
            new_item = FileItem(row_id=row_id, file_path=path, file_name=os.path.basename(path), file_type=f_type, total_pages=0)
            if f_type == FLAT_FILE_TYPES[2]:
                new_item.params.document_options = PresentationPrintOptions()
            elif f_type == FLAT_FILE_TYPES[3]:
                new_item.params.document_options = ExcelPrintOptions()
            self.current_file_list.append(path)
            self.file_items.append(new_item)
            self.insert_row_to_table(new_item, is_loading=True)

        # 刷新 UI
        self.refresh_ui_status()

        # 如果有非法文件，弹窗提示用户
        if invalid_files:
            msg_lines = [_("MainWindow","file_validation_summary",count=len(invalid_files))]
            for path, reason in list(invalid_files.items())[:5]:
                msg_lines.append(_("MainWindow","file_validation_item",name=os.path.basename(path),reason= reason))

            if len(invalid_files) > 5:
                msg_lines.append(_("MainWindow","file_validation_more",count=len(invalid_files) - 5))

            if self.isVisible():
                title = _("MainWindow", "message_title_warning")
                CustomMessageBox(QMessageBox.Icon.Warning,title,"\n".join(msg_lines),QMessageBox.StandardButton.Ok,self).exec()
            else:
                self._pending_invalid_files_message = "\n".join(msg_lines)

            # 同时记录日志
            logger.warning(f"指纹校验拦截了 {len(invalid_files)} 个文件: {invalid_files}")

    def showEvent(self, event):
        super().showEvent(event)
        if self._pending_invalid_files_message is not None:
            QTimer.singleShot(100, self._show_pending_error_dialog)

    def _show_pending_error_dialog(self):
        if self._pending_invalid_files_message:
            CustomMessageBox(
                QMessageBox.Icon.Warning,
                _("MainWindow", "message_title_warning"),
                self._pending_invalid_files_message,
                QMessageBox.StandardButton.Ok,
                self
            ).exec()
            self._pending_invalid_files_message = None

    def getCheckedCount(self):
        total_rows = self.file_table.rowCount()
        checked_count = 0
        # 统计选中情况
        for r in range(total_rows):
            item = self.file_table.item(r, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                checked_count += 1

        return checked_count

    def updateHeaderCheckState(self):
        total_rows = self.file_table.rowCount()
        checked_count = self.getCheckedCount()
        new_state = Qt.CheckState.Unchecked
        if checked_count == 0:
            new_state = Qt.CheckState.Unchecked
        elif checked_count == total_rows:
            new_state = Qt.CheckState.Checked
        else:
            new_state = Qt.CheckState.PartiallyChecked
        # 阻塞信号防止触发 on_header_checkbox_changed
        self.header_checkbox.blockSignals(True)
        self.header_checkbox.setCheckState(new_state)
        self.header_checkbox.blockSignals(False)

    def insert_row_to_table(self, item: FileItem,is_loading=False):
        row = self.file_table.rowCount()
        self.file_table.insertRow(row)

        # Checkbox
        check_item = QTableWidgetItem()
        check_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        check_item.setCheckState(Qt.CheckState.Checked)
        check_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.file_table.setItem(row, 0, check_item)

        # Filename
        name_item = QTableWidgetItem(item.file_name)
        name_item.setFlags(Qt.ItemIsEnabled)
        name_item.setToolTip(item.file_path)
        name_item.setData(Qt.UserRole,item)
        self.file_table.setItem(row, 1, name_item)

        # Pages
        # page_item = QTableWidgetItem("⏳ ..." if is_loading else str(item.total_pages))
        # page_item.setFlags(Qt.ItemIsEnabled)
        # page_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        # page_item.setForeground(QColor("#999") if is_loading else QColor("#333"))
        # page_item.setData(Qt.UserRole, item.file_path) # 存储路径以便后续更新
        # self.file_table.setItem(row, 2, page_item)
        container = QWidget()
        container_layout = QHBoxLayout(container)
        container_layout.setContentsMargins(10, 5, 10, 5) # 设置边距，让进度条不要太贴边
        container_layout.setSpacing(0)
        container_layout.setAlignment(Qt.AlignmentFlag.AlignCenter) # 关键：布局内控件居中
        
        # 创建进度条
        progress_bar = QProgressBar()
        progress_bar.setRange(0, 100) # 设置范围 0-100
        progress_bar.setValue(0) # 初始值为 0
        progress_bar.setTextVisible(False)
        progress_bar.setFixedWidth(60) # 固定宽度，防止表格列宽被撑开
        progress_bar.setMaximumHeight(10)
        progress_bar.setObjectName(f"progress_row_{row}")
        container_layout.addWidget(progress_bar)

        # 存储进度条
        self.file_table.setCellWidget(row, 2, container)
        if is_loading:
            self.pending_rows.append(row) 
            self.process_next_row()       

        # Range
        if item.file_type != FLAT_FILE_TYPES[3]:
            range_edit = QLineEdit("1-?")
            range_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
            range_edit.setStyleSheet("border: 1px solid #eee; background: #fafafa;")
            validator = QRegularExpressionValidator(QRegularExpression(r"[0-9,\-\?]*"))
            range_edit.setValidator(validator)
            range_edit.setMaximumWidth(90)
            range_edit.setEnabled(False) # 页码未知前禁用
            range_edit.textChanged.connect(partial(self.update_range_edit, row))
            self.file_table.setCellWidget(row, 3, CustomDelegateCell(range_edit))
        else:
            # Excel 文件的处理：插入 Sheet 表单下拉列表
            combo_box = QComboBox()
            combo_box.setView(QListView())
            combo_box.addItem(_("MainWindow","all_worksheets"))
            combo_box.setCurrentIndex(0) 
            
            # 动态读取并添加 Excel 中的真实 Sheet 名称
            if hasattr(item, 'sheet_names') and isinstance(item.sheet_names, list):
                for sheet_name in item.sheet_names:
                    combo_box.addItem(sheet_name)
            # 样式与布局调整
            combo_box.setStyleSheet("border: 1px solid #eee; background: #fafafa;")
            combo_box.setMinimumWidth(90)
            combo_box.setMaximumWidth(150)
            # 绑定事件
            combo_box.currentIndexChanged.connect(partial(self.update_sheet_combo, row))
            self.file_table.setCellWidget(row, 3, CustomDelegateCell(combo_box))


        # Copies
        spin_box = QSpinBox()
        spin_box.setRange(1, 999)
        spin_box.setValue(item.params.copies)
        spin_box.valueChanged.connect(partial(self.update_spin_box, row))
        spin_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        spin_box.setStyleSheet("border: 1px solid #eee; background: #fafafa;")
        self.file_table.setCellWidget(row, 4, CustomDelegateCell(spin_box))

        # Status
        status_item = QTableWidgetItem(item.status)
        status_item.setForeground(QColor("#999"))
        status_item.setFont(QFont("", 9)) 
        status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        status_item.setFlags(Qt.ItemIsEnabled)
        self.file_table.setItem(row, 5, status_item)

        # Actions
        op_widget = QWidget()
        op_layout = QHBoxLayout(op_widget)
        op_layout.setContentsMargins(4, 4, 4, 4)

        btn_set = QPushButton("")
        btn_set.setIcon(QIcon(":/images/resources/setting.png"))
        btn_set.setObjectName("btnSet")
        btn_set.setIconSize(QSize(16,16))
        btn_set.clicked.connect(lambda checked, r=row: self.open_settings_dialog(item.file_path))

        btn_del = QPushButton("")
        btn_del.setIcon(QIcon(":/images/resources/dustbin.png"))
        btn_del.setObjectName("btnDel")
        btn_del.setIconSize(QSize(19,19))
        btn_del.clicked.connect(lambda checked, r=row: self.remove_row(item))

        op_layout.addWidget(btn_set)
        op_layout.addWidget(btn_del)
        op_layout.addStretch()
        self.file_table.setCellWidget(row, 6, op_widget)

        # 如果 LO 就绪，触发异步获取页码
        if is_loading:
            task_manager.get_page_count_async(item.file_path)

    def process_next_row(self):
        """
        队列调度器：如果当前空闲且队列不为空，则处理下一行。
        """
        # 如果正在处理，或者队列为空，直接返回
        if self.is_processing or not self.pending_rows:
            return

        # 锁定状态，取出下一行
        self.is_processing = True
        next_row = self.pending_rows.pop(0) # 取出第一个
        
        # 获取该行的进度条
        widget = self.file_table.cellWidget(next_row, 2)
        if widget and widget.layout():
            progress_bar = widget.layout().itemAt(0).widget()
            # 启动该行的模拟
            self.start_simulated_progress_single(next_row, progress_bar)

    def start_simulated_progress_single(self, row, progress_bar):
        """
        启动单行的模拟进度。
        注意：此方法被调度器调用，不再管理全局列表，只管理自己的定时器。
        """
        # 清理旧的定时器
        if self.current_timer and self.current_timer.isActive():
            self.current_timer.stop()

        # 为进度条挂载状态属性
        progress_bar.current_value = 0
        progress_bar.is_finished = False

        timer = QTimer(self)
        self.current_timer = timer

        def update_frame():
            # 检查是否被外部标记为结束
            if progress_bar.is_finished:
                timer.stop()
                self._release_lock_and_continue() # 释放锁，处理下一行
                return

            progress_bar.current_value += random.randint(5,10)
            if progress_bar.current_value >= 90:
                pass
            elif progress_bar.current_value > 5:
                progress_bar.setValue(progress_bar.current_value)

        timer.timeout.connect(update_frame)
        timer.start(50)

    def finish_simulated_progress(self, row, column, final_value):
        # 查找该单元格的控件
        widget = self.file_table.cellWidget(row, column)
        if widget and widget.layout():
            progress_bar = widget.layout().itemAt(0).widget()
            if hasattr(progress_bar, 'is_finished') and not progress_bar.is_finished:
                progress_bar.is_finished = True # 标记停止动画
                progress_bar.setValue(100) # 强制设为100%
                
                # 延迟 200ms 后替换为文本
                QTimer.singleShot(200, lambda: self._replace_progress_with_text(row, column, final_value))

    def _replace_progress_with_text(self, row, column, text):
        """
        内部方法：移除进度条控件，替换为普通文本项。
        """
        # 移除旧控件
        self.file_table.removeCellWidget(row, column)
        
        # 创建新文本项
        text_item = QTableWidgetItem(str(text))
        text_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        text_item.setFlags(Qt.ItemIsEnabled)
        
        # 根据数值设置颜色
        color = QColor("#d9534f") if text == 0 or str(text).lower() == 'error' else QColor("#000000")
        text_item.setForeground(color)
        
        self.file_table.setItem(row, column, text_item)
        self._release_lock_and_continue()

    def _release_lock_and_continue(self):
        """
        内部方法：释放处理锁，并尝试处理下一行。
        """
        self.is_processing = False
        # 递归调用调度器
        self.process_next_row()

    def update_spin_box(self,row,text):

        file_item = self.file_table.item(row, 1).data(Qt.UserRole)
        if file_item:
            file_item.params.copies = text
            self.refresh_ui_status()

    def update_range_edit(self, row, text):
        
        if not text or text == "1-?":
            return
        
        file_item = self.file_table.item(row, 1).data(Qt.UserRole)
        if file_item:
            file_item.page_range = file_item.params.page_range = text
            self.refresh_ui_status()

    def update_sheet_combo(self,row,text):
        name_item = self.file_table.item(row, 1) 
        if not name_item:return
        file_item = name_item.data(Qt.UserRole)
        for item in self.file_items:
            if item == file_item:
                item.params.document_options.sheet_index = int(text)-1
                item.params.document_options.print_mode = (
                    ExcelPrintMode.ENTIRE_WORKBOOK if int(text) == 0 
                    else ExcelPrintMode.ACTIVE_SHEET
                )
        task_manager.get_page_count_async(file_item.file_path,int(text)-1)
    def on_page_count_ready(self, file_path, result):
        """槽函数：接收后台传来的页码"""
        page_count,sheet_names = result
        # 查找对应的行
        for r in range(self.file_table.rowCount()):
            item = self.file_table.item(r, 1)
            if item and item.data(Qt.UserRole).file_path == file_path:
                # 更新 Model
                current_file_item = item.data(Qt.UserRole)
                current_file_item.total_pages = page_count
                # 停止模拟并显示结果
                self.finish_simulated_progress(r, 2, page_count if page_count > 0 else "Err")
                # 更新 Range 输入框
                range_widget = self.file_table.cellWidget(r, 3)
                range_edit = range_widget.layout().itemAt(0).widget()
                if current_file_item.file_type == FLAT_FILE_TYPES[3] and sheet_names:
                    previous_selected_text = range_edit.currentText()
                    range_edit.blockSignals(True)
                    range_edit.clear()
                    range_edit.addItem(_("MainWindow","all_worksheets"))
                    for name in sheet_names:
                        range_edit.addItem(name)
                    # 恢复选中项
                    index_to_restore = range_edit.findText(previous_selected_text)
                    if index_to_restore != -1:
                        range_edit.setCurrentIndex(index_to_restore)
                    range_edit.blockSignals(False)
                else:
                    if page_count > 0:
                        range_edit.setText(f"1-{page_count}")
                        range_edit.setEnabled(True)
                    else:
                        range_edit.setText("Err")
                        range_edit.setEnabled(False)
                        # range_edit.setStyleSheet("border: 1px solid #eee; background: #fff; color: #999;")    
                # 刷新底部状态栏统计
                self.refresh_ui_status()

    def remove_row(self, file_item):
        """通过file_path,删除行"""
        row_to_remove = None
        for row in range(self.file_table.rowCount()):
            current_item = self.file_table.item(row,1).data(Qt.UserRole)
            if current_item == file_item:
                row_to_remove = row
                break

        if row_to_remove is None:return

        self.file_items = [item for item in self.file_items if item != file_item]
        self.current_file_list = [p for p in self.current_file_list if p != file_item.file_path]
        self.file_table.removeRow(row_to_remove)
        self.refresh_ui_status()

    def on_header_checkbox_changed(self,state):
        check_state = Qt.CheckState(state)
        if check_state == Qt.CheckState.PartiallyChecked:
            target_state = Qt.CheckState.Checked
            self.header_checkbox.setCheckState(Qt.CheckState.Checked)  # 转为全选
        else:
            target_state = check_state
        
        self.header_checkbox_state = target_state
        # 遍历所有行，设置复选框
        for row in range(self.file_table.rowCount()):
            item = self.file_table.item(row, 0)
            if item:
                item.setCheckState(target_state)   
        self.refresh_ui_status()

    def open_settings_dialog(self, path):
        logger.debug(f"Open the settings dialog: {os.path.basename(path)}")
        target_item = next((item for item in self.file_items if item.file_path == path), None)

        if target_item:
            dialog = SettingsDialog(target_item.row_id, target_item.file_type, self.file_items, self)
            dialog.exec()

    def delete_selected(self):
        rows_to_delete = []
        for r in range(self.file_table.rowCount()):
            item = self.file_table.item(r, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                file_item = self.file_table.item(r, 1).data(Qt.UserRole)
                rows_to_delete.append((r,file_item))
        # 进行逆序排序        
        rows_to_delete.sort(key=lambda x: x[0], reverse=True)
        for row, file_item in rows_to_delete:
            self.remove_row(file_item)
        logger.info(f"User deleted {len(rows_to_delete)} selected files")

    def update_file_params(self, row_id: int, params: PrintParams):
        # 更新 Model 和 View
        for item in self.file_items:
            if item.row_id == row_id:
                item.params = params
                break
        self.refresh_ui_status()

    def refresh_ui_status(self):
        # 更新header_checkbox status
        self.updateHeaderCheckState()
        # 计算统计
        selected_items = []
        for r in range(self.file_table.rowCount()):
            check_item = self.file_table.item(r, 0)
            if check_item and check_item.checkState() == Qt.CheckState.Checked:
                name_item = self.file_table.item(r, 1)
                if name_item:
                    file_item = name_item.data(Qt.UserRole)
                    selected_items.append(file_item)
        stats = StatsService.calculate_for_selection(selected_items)

        total = len(self.file_items)
        status_text = ""
        if stats['count'] > 0:
            status_text = _("MainWindow", "stats_summary", total=total, selected=stats['count'], 
                          pages=stats['pages'], sheets=stats['sheets'])
        else:
            status_text = _("MainWindow", "message_no_files_selected")

        self.list_status_label.setText(status_text)
        self.btn_print.setEnabled(stats['count'] > 0)

        # 更新表头状态
        if total == 0: new_state = Qt.CheckState.Unchecked
        elif stats['count'] == 0: new_state = Qt.CheckState.Unchecked
        elif stats['count'] == total: new_state = Qt.CheckState.Checked
        else: new_state = Qt.CheckState.PartiallyChecked

        if new_state != self.header_checkbox_state:
            self.header_checkbox_state = new_state
            # self.header_delegate.isChecked = new_state
            self.file_table.horizontalHeader().viewport().update()

    def start_batch_print(self):
        # 收集选中项
        selected_items = []
        for r in range(self.file_table.rowCount()):
            check_item = self.file_table.item(r, 0)
            if check_item and check_item.checkState() == Qt.CheckState.Checked:
                path = self.file_table.item(r, 1).toolTip()
                item = next((i for i in self.file_items if i.file_path == path), None)

                if item: selected_items.append(item)

        if not selected_items: 
            logger.warning("User tried to print without selecting any files")
            return

        # 检查是否有页码未知的文件
        unknown_pages = [i.file_name for i in selected_items if i.total_pages <= 0]
        if unknown_pages:
            reply = CustomMessageBox(QMessageBox.Icon.Question,_("MainWindow", "message_title_warning"),
                _("MainWindow", "message_unknown_pages_warning", count=len(unknown_pages)),QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,self).exec()
            if reply != QMessageBox.StandardButton.Yes:
                return

        msg = _("MainWindow", "message_confirm_print", count=len(selected_items)) + "\n\n"
        logger.info(f"User started batch printing, total {len(selected_items)} files")
        for item in selected_items:
            msg += f"• {item.file_name} ({item.total_pages}页)\n"
        
        if CustomMessageBox(QMessageBox.Icon.Question,_("MainWindow", "message_title_confirm"),msg
            ,QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,self).exec() == QMessageBox.StandardButton.Yes:
            self.btn_print.setEnabled(False)
            self.btn_print.setText(_("MainWindow", "message_printing"))
            # 执行打印逻辑
            for item in selected_items:
                task_manager.print_file_async(item.file_path,item.params)

    def on_task_status_update(self,result):
        for r in range(self.file_table.rowCount()):
            check_item = self.file_table.item(r, 0)
            file_path = self.file_table.item(r,1).toolTip()
            if check_item and check_item.checkState() == Qt.CheckState.Checked and file_path == result.file_path:
                status_item = self.file_table.item(r, 5)
                if(result.status == TaskStatus.SUCCESS):
                    status_item.setText(_("MainWindow", "message_print_submitted"))
                    status_item.setForeground(QColor("#28a745"))
                    logger.debug(f"Task successful: {os.path.basename(result.file_path)}")
                elif(result.status == TaskStatus.FAILED):
                    status_item.setText(_("MainWindow", "message_print_failed"))
                    status_item.setForeground(QColor("#FF6600"))
                    logger.error(f"Task failed: {os.path.basename(result.file_path)}")
                else:
                    status_item.setText(result.message)
                    logger.info(f"Task: {os.path.basename(result.file_path)} - {result.message}")
                
                status_item.setFont(self.font())

        self.btn_print.setEnabled(True)
        self.btn_print.setText(_("MainWindow", "btn_print"))

    def add_files_from_external(self, file_paths):
        logger.info(f"Received {len(file_paths)} external files via IPC")
        self.add_files_list(file_paths)
        if self.isMinimized():
            self.showNormal() 
        # 激活窗口提醒用户
        self.activateWindow()
        self.raise_()

    def closeEvent(self, event):
        logger.info("Main window closed, cleaning up resources...")
        # 停止活跃的定时器
        if self.current_timer and self.current_timer.isActive():
            self.current_timer.stop()

        # 强制将所有进度条设为完成状态
        for row in range(self.file_table.rowCount()):
            widget = self.file_table.cellWidget(row, 2)
            if widget and widget.layout():
                pb = widget.layout().itemAt(0).widget()
                if hasattr(pb, 'is_finished'):
                    pb.is_finished = True

        # 关闭任务管理器
        task_manager.shutdown()
        
        # 接受关闭事件
        event.accept()

        logger.info("Application Exit!")
