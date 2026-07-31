# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
from PySide6.QtCore import Qt, QRect, QSize, QEvent, QModelIndex, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QMouseEvent
from PySide6.QtWidgets import (QStyledItemDelegate, QHeaderView, QWidget, QHBoxLayout, QCheckBox,QStyleOptionButton,
    QStyle,QApplication,QVBoxLayout, QSpinBox, QComboBox, QLabel, QGroupBox,QFormLayout,QListView)
from models.file_model import NUpLayout,NUpPreset,LayoutDirection
from config.settings import FLAT_FILE_TYPES
from utils.i18n import _

class CheckBoxHeaderDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.isChecked = Qt.CheckState.Unchecked
        self.hovered_section = -1

    def paint(self, painter, option, index):
        sys.stdout.flush()
        painter.save()
        is_hovered = (index.column() == self.hovered_section)
        if is_hovered: painter.fillRect(option.rect, QColor("#eef"))
        else: painter.fillRect(option.rect, option.palette.window())

        cb_size = QSize(18, 18)
        cb_rect = QRect(option.rect.x() + (option.rect.width() - cb_size.width()) // 2,
                        option.rect.y() + (option.rect.height() - cb_size.height()) // 2,
                        cb_size.width(), cb_size.height())
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor("#999"), 1.5)
        painter.setPen(pen)
        painter.setBrush(QBrush(Qt.white))

        if self.isChecked == Qt.CheckState.Checked:
            painter.setBrush(QBrush(QColor("#0078D4")))
            painter.setPen(QPen(QColor("#0078D4"), 1.5))
        elif self.isChecked == Qt.CheckState.PartiallyChecked:
            painter.setBrush(QBrush(QColor("#0078D4")))
            painter.setPen(QPen(QColor("#0078D4"), 1.5))

        painter.drawRoundedRect(cb_rect.adjusted(1, 1, -1, -1), 4, 4)

        if self.isChecked == Qt.CheckState.Checked:
            painter.setPen(QPen(Qt.white, 2.5))
            path = [(cb_rect.left()+5, cb_rect.center().y()+3), (cb_rect.left()+8, cb_rect.bottom()-5), (cb_rect.right()-5, cb_rect.top()+5)]
            painter.drawLine(path[0], path[1])
            painter.drawLine(path[1], path[2])
        elif self.isChecked == Qt.CheckState.PartiallyChecked:
            painter.setPen(QPen(Qt.white, 2.5))
            painter.drawLine(cb_rect.left()+5, cb_rect.center().y(), cb_rect.right()-5, cb_rect.center().y())
        painter.restore()

    def editorEvent(self, event, model, option, index):
        if event.type() == QEvent.Type.MouseButtonPress: return True
        return super().editorEvent(event, model, option, index)

class CustomHeaderView(QHeaderView):
    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.delegate = None
        self.setMouseTracking(True)
    def set_delegate(self, delegate): self.delegate = delegate
    def mouseMoveEvent(self, event):
        pos = event.pos()
        logical_idx = self.logicalIndexAt(pos)
        if self.delegate and self.delegate.hovered_section != logical_idx:
            self.delegate.hovered_section = logical_idx
            self.viewport().update()
        super().mouseMoveEvent(event)
    def leaveEvent(self, event):
        if self.delegate and self.delegate.hovered_section != -1:
            self.delegate.hovered_section = -1
            self.viewport().update()
        super().leaveEvent(event)

class CustomDelegateCell(QWidget):
    def __init__(self, widget, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 3, 5, 3)
        layout.addWidget(widget)
        self.widget = widget

class CenteredCheckBoxDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        if index.column() == 0:  # 仅处理第一列
            # 获取复选框状态
            check_state = Qt.CheckState(index.data(Qt.CheckStateRole))
            checked = check_state == Qt.CheckState.Checked

            # 准备样式选项
            opt = QStyleOptionButton()
            opt.state = QStyle.State_Enabled
            if checked:
                opt.state |= QStyle.State_On
            else:
                opt.state |= QStyle.State_Off

            # 计算复选框居中位置
            style = QApplication.style()
            size = style.pixelMetric(QStyle.PM_IndicatorWidth)
            rect = option.rect
            x = rect.x() + (rect.width() - size) // 2
            y = rect.y() + (rect.height() - size) // 2
            opt.rect = QRect(x, y, size, size)

            # 绘制复选框
            style.drawControl(QStyle.CE_CheckBox, opt, painter)
        else:
            super().paint(painter, option, index)

    def editorEvent(self, event, model, option, index):
        """处理鼠标事件，实现点击切换状态"""
        if index.column() == 0 and event.type() == QMouseEvent.MouseButtonRelease:
            # 只处理鼠标释放事件，避免误触
            rect = option.rect
            # 计算点击区域是否在复选框范围内
            style = QApplication.style()
            size = style.pixelMetric(QStyle.PM_IndicatorWidth)
            x = rect.x() + (rect.width() - size) // 2
            y = rect.y() + (rect.height() - size) // 2
            check_rect = QRect(x, y, size, size)
            
            if check_rect.contains(event.pos()):
                # 切换状态
                current = Qt.CheckState(index.data(Qt.CheckStateRole))
                new_state = Qt.CheckState.Unchecked if current == Qt.CheckState.Checked else Qt.CheckState.Checked
                success = model.setData(index, new_state, Qt.CheckStateRole)
                if success:
                    # 获取视图
                    table_widget = option.widget
                    if table_widget:
                        # 通过行和列获取真实的 item，并强制设置其状态
                        item = table_widget.item(index.row(), index.column())
                        if item:item.setCheckState(new_state)        
                return success
        return super().editorEvent(event, model, option, index)

    def createEditor(self, parent, option, index):
        # 不需要编辑器，返回 None
        return None

class NUpSettingsWidget(QWidget):
    """统一的 N-Up (拼版) 设置组件"""
    
    # 当任何内部控件的值发生变化时发出此信号
    settingsChanged = Signal()

    def __init__(self, parent=None,file_type:str=None):
        super().__init__(parent)
        self.file_type = file_type
        self._ = _
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self): 
        # 预设选择
        form_layout = QFormLayout(self)
        form_layout.setContentsMargins(0,0,0,0)
        form_layout.setSpacing(12)
        grid_layout = QHBoxLayout()
        grid_layout.setSpacing(10)
        self.combo_nup = QComboBox()
        self.combo_nup.setView(QListView())
        self.combo_nup.setObjectName(f"nup_{self.file_type}")
        label_nup = label_order = None
        if self.file_type is not FLAT_FILE_TYPES[2]:
            for preset in NUpPreset:
                if self.file_type in [FLAT_FILE_TYPES[0],FLAT_FILE_TYPES[1]] and preset != NUpPreset.THREE_UP:
                    self.combo_nup.addItem(_("SettingsDialog", preset.label), preset.page_count)
                    label_nup = QLabel(_("SettingsDialog", "nup_preset_text"))
                    label_order = QLabel(_("SettingsDialog", "nup_order_text"))
                elif self.file_type == FLAT_FILE_TYPES[3] and (preset not in [NUpPreset.CUSTOM,NUpPreset.THREE_UP]) :
                    self.combo_nup.addItem(f"{preset.page_count}", preset.page_count)
                    label_nup = QLabel(_("SettingsDialog", "label_nup_preset"))
                    label_order = QLabel(_("SettingsDialog", "label_nup_order"))
        # else:
        #     for slides_count in HandoutSlidesPerPage:
        #         self.combo_nup.addItem(str(slides_count.value), slides_count)
        #         label_desc = QLabel(_("SettingsDialog", "label_nup_preset"))
        #         label_order = QLabel(_("SettingsDialog", "label_nup_order"))

        
        grid_layout.addWidget(label_nup)
        grid_layout.addWidget(self.combo_nup, 1)

        self.spin_rows = QSpinBox()
        self.spin_rows.setRange(1, 100)
        self.spin_rows.setValue(1)
        self.spin_rows.setEnabled(False)
        self.spin_rows.setObjectName(f"nup_rows_{self.file_type}")
        label_rows = QLabel(_("SettingsDialog", "label_nup_rows"))
        self.spin_cols = QSpinBox()
        self.spin_cols.setRange(1, 100)
        self.spin_cols.setValue(1)
        self.spin_cols.setEnabled(False)
        self.spin_cols.setObjectName(f"nup_cols_{self.file_type}")
        label_cols = QLabel(_("SettingsDialog", "label_nup_cols"))
        # 自定义行列
        if self.file_type in [FLAT_FILE_TYPES[0],FLAT_FILE_TYPES[1]]:
            grid_layout.addSpacing(20)
            grid_layout.addWidget(self.spin_rows)
            grid_layout.addWidget(label_rows)
            grid_layout.addWidget(self.spin_cols)
            grid_layout.addWidget(label_cols)
        form_layout.addRow(grid_layout)
        
        # 排序方式与边框
        dir_layout = QHBoxLayout()
        dir_layout.setSpacing(10)
        self.combo_dir = QComboBox()
        self.combo_dir.setView(QListView())
        self.combo_dir.setObjectName(f"nup_order_{self.file_type}")
        for dir_opt in list(LayoutDirection)[:4]:
            self.combo_dir.addItem(_("LayoutDirection", dir_opt.value), dir_opt)
        dir_layout.addWidget(label_order)
        dir_layout.addWidget(self.combo_dir,1)
        dir_layout.addSpacing(25)
        self.chk_border = QCheckBox(_("SettingsDialog", "label_nup_border"))
        self.chk_border.setChecked(False)
        dir_layout.addWidget(self.chk_border)
        form_layout.addRow(dir_layout)
        
    def _connect_signals(self):
        """将所有控件的变化统一转发给 settingsChanged 信号"""
        self.combo_nup.currentIndexChanged.connect(self._on_preset_changed)
        self.spin_rows.valueChanged.connect(lambda: self.settingsChanged.emit())
        self.spin_cols.valueChanged.connect(lambda: self.settingsChanged.emit())
        self.combo_dir.currentIndexChanged.connect(lambda: self.settingsChanged.emit())
        self.chk_border.toggled.connect(lambda: self.settingsChanged.emit())

    def _on_preset_changed(self, index):
        preset_value = self.combo_nup.currentData()
        if preset_value is None:
            return
            
        # 阻断 spin 控件的信号，防止在程序修改值时触发 settingsChanged
        self.spin_rows.blockSignals(True)
        self.spin_cols.blockSignals(True)
            
        try:
            self.spin_cols.setEnabled(preset_value==-1)
            self.spin_rows.setEnabled(preset_value==-1)
            if preset_value != -1:
                rows, cols = NUpLayout.get_layout_info(preset_value)
                self.spin_rows.setValue(rows)
                self.spin_cols.setValue(cols)
                self.settingsChanged.emit()
        finally:
            # 恢复 spin 控件的信号
            self.spin_rows.blockSignals(False)
            self.spin_cols.blockSignals(False)

    # --- 安全地加载数据 ---
    def load_params(self, nup_layout):
        """
        从数据对象加载到 UI，自动处理 blockSignals 防止触发更新逻辑
        """
        if not nup_layout:
            return
            
        # 批量阻断所有子控件的信号
        controls = [self.combo_nup, self.spin_rows, self.spin_cols, self.combo_dir, self.chk_border]
        
        for ctrl in controls:
            ctrl.blockSignals(True)
            
        try:
            idx = self.combo_nup.findData(nup_layout.preset_value)
            if idx >= 0:
                self.combo_nup.setCurrentIndex(idx)
            self.spin_rows.setValue(nup_layout.rows)
            self.spin_cols.setValue(nup_layout.cols)
            dir_idx = self.combo_dir.findData(nup_layout.direction)
            if dir_idx >= 0:
                self.combo_dir.setCurrentIndex(dir_idx)
                
            self.chk_border.setChecked(nup_layout.draw_border)
        finally:
            for ctrl in controls:
                ctrl.blockSignals(False)

    # --- 安全地提取数据 ---
    def get_params(self):
        """
        从 UI 读取当前状态，返回一个 NUpLayout 对象
        """
        return NUpLayout(
            enabled=True,
            preset_value=self.combo_nup.currentData(),
            rows=self.spin_rows.value(),
            cols=self.spin_cols.value(),
            direction=self.combo_dir.currentData(),
            draw_border=self.chk_border.isChecked()
        )
