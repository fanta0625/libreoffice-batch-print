# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

# settings_dialog.py
import os
import math
import copy
from enum import Enum
from typing import List, Optional
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTabWidget, 
    QWidget, QGroupBox, QFormLayout, QComboBox, QSpinBox, QCheckBox, 
    QFrame, QMessageBox, QRadioButton, QButtonGroup, QScrollArea, 
    QGridLayout, QLineEdit, QSizePolicy, QFileDialog,QListView
)
from PySide6.QtCore import Qt, Signal, QSize, QRect
from PySide6.QtGui import QFont, QPainter, QColor, QPen, QBrush, QIntValidator

from models.file_model import (
    FileItem, PrintParams, PaperOrientations, DuplexMode, ScalingMode, 
    NUpPreset, LayoutMode, BookletDirection,LayoutDirection,PresentationContentType,
    PresentationPrintOptions,ExcelPrintOptions,ExcelScalingType,ExcelScalePreset)
from config.settings import FLAT_FILE_TYPES, PAPER_SIZES,DEFAULT_PRINTER_ID
from services.uno_connect_service import lo_service
from utils.paper_utils import PaperSizeHelper,PrinterHelper
from ui.DocumentPreviewer import DocumentPreviewer 
from ui.components import NUpSettingsWidget
from utils.i18n import _
from utils.custom_message_box import CustomMessageBox
from log.logger import get_logger

logger = get_logger("SettingsDialog")

class SettingsDialog(QDialog):
    params_updated = Signal(list, object)
    
    def __init__(self, current_row_id, current_type, all_items: List[FileItem], parent=None):
        super().__init__(parent)
        logger.debug(f"Open settings dialog: type={current_type}, rowID={current_row_id}")
        self.current_row_id = current_row_id
        self.current_type = current_type
        self.all_items = all_items
        self.setWindowTitle(_("SettingsDialog", "window_title"))
        self.setMinimumSize(1000, 650)
        self._scale_edit_processed = False
        self.previewer = None
        
        self.grouped_data = {t: [] for t in FLAT_FILE_TYPES}
        for item in self.all_items:
            if item.file_type in self.grouped_data:
                self.grouped_data[item.file_type].append(item)
                
        self.printer_list = lo_service.get_printer_list()
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        # --- 主体布局：左侧配置 + 右侧预览 ---
        content_layout = QHBoxLayout()
        content_layout.setSpacing(20)

        # === 左侧：配置面板 ===
        left_widget = QWidget()
        left_widget.setMaximumWidth(550)
        left_widget.setMinimumWidth(380)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(15)

        # 文件类型 Tabs
        self.tabs = QTabWidget()
        self.tabs.setObjectName("tab_file_type")
        # self.tabs.setStyleSheet("font-size: 14px;")
        for f_type in FLAT_FILE_TYPES:
            tab_widget = self.create_type_tab_content(f_type)
            self.tabs.addTab(tab_widget, f"{f_type}")

        for i, f_type in enumerate(FLAT_FILE_TYPES):
            files_in_type = self.grouped_data.get(f_type, [])
            if len(files_in_type) == 0:
                self.tabs.setTabEnabled(i, False)
            
        index_map = {t: i for i, t in enumerate(FLAT_FILE_TYPES)}
        self.tabs.setCurrentIndex(index_map.get(self.current_type, 0))
        self.tabs.currentChanged.connect(self.on_tab_changed)
        left_layout.addWidget(self.tabs)

        # === 右侧：真实预览面板 ===
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        # right_layout.setSpacing(10)

        # 预览标题栏
        preview_header = QLabel(_("SettingsDialog", "preview_title"))
        preview_header.setObjectName("preview_header")
        right_layout.addWidget(preview_header)

        # 预览绘图区 - 使用 DocumentPreviewer
        self.previewer = DocumentPreviewer()
        right_layout.addWidget(self.previewer, 1)

        content_layout.addWidget(left_widget)
        content_layout.addWidget(right_widget, 1)
        main_layout.addLayout(content_layout)

        # === 全局底部操作区 ===
        footer_frame = QFrame()
        footer_frame.setObjectName("footerFrame")
        footer_frame.setFrameShape(QFrame.StyledPanel)
        footer_layout = QHBoxLayout(footer_frame)
        # footer_layout.setContentsMargins(20, 15, 20, 0)
        footer_layout.addStretch()

        # 按钮 1: 应用到当前
        self.btn_global_apply_single = QPushButton(_("SettingsDialog","btn_apply_single"))
        self.btn_global_apply_single.setObjectName("btnApplySingle")
        self.btn_global_apply_single.setMinimumSize(120, 40)
        if self.current_row_id == -1:
            self.btn_global_apply_single.setEnabled(False)
            self.btn_global_apply_single.setText(_("SettingsDialog","btn_apply_single_disabled")) 
        else:
            self.btn_global_apply_single.clicked.connect(lambda: self.apply_params(scope='single'))

        # 按钮 2: 应用到全部 (动态文本)
        self.btn_global_apply_all = QPushButton(_("SettingsDialog","btn_apply_all"))
        self.btn_global_apply_all.setObjectName("btnApplyAll")
        self.btn_global_apply_all.setMinimumSize(120, 40)
        self.btn_global_apply_all.clicked.connect(lambda: self.apply_params(scope='all'))

        footer_layout.addWidget(self.btn_global_apply_single)
        footer_layout.addWidget(self.btn_global_apply_all)
        main_layout.addWidget(footer_frame)

        # 初始化
        self.load_current_params()
        # self.update_preview()  # 初始化时触发一次
        self.on_tab_changed(self.tabs.currentIndex())

    def on_tab_changed(self, index):
        """当 Tab 切换时，更新底部按钮的文本和状态"""
        if index < 0 or index >= len(FLAT_FILE_TYPES) or not self.tabs.isTabEnabled(index):
            return
            
        current_type = FLAT_FILE_TYPES[index]
        files_in_type = self.grouped_data.get(current_type, [])
        count = len(files_in_type)
        if count > 0:
            first_item = files_in_type[0]
            self.current_row_id = first_item.row_id
            self.current_type = current_type
            logger.debug(f"Context updated to: Type={current_type}, RowID={self.current_row_id}, File={first_item.file_path}")
        self.btn_global_apply_all.setText(_("SettingsDialog","btn_apply_current_type",type=current_type,count=count)) 

        # 更新“应用到当前”按钮状态
        if self.current_row_id != -1:
            target_item = next((i for i in self.all_items if i.row_id == self.current_row_id), None)
            if target_item and target_item.file_type == current_type:
                self.btn_global_apply_single.setEnabled(True)
                self.btn_global_apply_single.setText(_("SettingsDialog","btn_apply_single"))  
            else:
                self.btn_global_apply_single.setEnabled(False)
                self.btn_global_apply_single.setText(_("SettingsDialog","btn_apply_single_wrong_type",type=current_type))  
        else:
            self.btn_global_apply_single.setEnabled(False)
            self.btn_global_apply_single.setText(_("SettingsDialog","btn_apply_single_disabled")) 

        logger.debug(f"Switch the settings tab to: {current_type}")

        self.load_current_params()
        # 切换 Tab 后，重新刷新预览
        self.update_preview()


    def create_type_tab_content(self, f_type):
        """创建单个 Tab 的内容，通过委托给专用方法来构建 UI"""
        container = QWidget()
        container.setMaximumWidth(550)
        container.setMinimumWidth(450)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        files_in_type = self.grouped_data[f_type]
        count = len(files_in_type)
        stat_label = QLabel(_("SettingsDialog", "category_label", type=f_type, count=count))
        stat_label.setStyleSheet("background: #ecf0f1; padding: 8px; border-radius: 4px;")
        layout.addWidget(stat_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        form_widget = QWidget()
        form_layout = QFormLayout(form_widget)
        form_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form_layout.setSpacing(12)
        
        # 初始化控件字典，用于存储该 Tab 下所有的表单控件引用
        controls_dict = {}
        
        # 添加通用基础设置
        self._add_common_settings(form_layout, f_type, controls_dict)
        
        # 根据文件类型添加特定设置
        if f_type == "PPT":
            self._add_ppt_specific_settings(form_layout, f_type, controls_dict)
        elif f_type == "Excel":
            self._add_excel_specific_settings(form_layout, f_type, controls_dict)
        else:
            # 添加版式设置 (缩放 / N-Up / 小册子)
            self._add_layout_mode_settings(form_layout, f_type, controls_dict)

        # --- 分隔线 ---
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        form_layout.addRow(line)

        # 添加双面打印设置
        self._add_duplex_settings(form_layout, f_type, controls_dict)

        # 将构建好的表单添加到滚动区域
        scroll.setWidget(form_widget)
        layout.addWidget(scroll)

        # 将控件字典绑定到容器上
        container.setProperty("controls", controls_dict)
        
        return container

    def _add_common_settings(self, form_layout, f_type, controls_dict):
        """添加所有文件类型共有的基础设置项"""
        
        # --- 打印机 ---
        combo_printer = QComboBox()
        combo_printer.setView(QListView())
        combo_printer.setObjectName(f"printer_{f_type}")
        # combo_printer.addItems(self.printer_list)
        for item in self.printer_list:
            if item == DEFAULT_PRINTER_ID:
                display = _("SettingsDialog","default_printer")
            else:display = item
            combo_printer.addItem(display, item)
        combo_printer.currentTextChanged.connect(self.update_duplex_mode)
        form_layout.addRow(_("SettingsDialog", "label_printer"), combo_printer)

        # --- 分隔线 ---
        line1 = QFrame()
        line1.setFrameShape(QFrame.HLine)
        form_layout.addRow(line1)

        # --- 纸张方向 ---
        combo_orientation = QComboBox()
        combo_orientation.setView(QListView())
        combo_orientation.setObjectName(f"orientation_{f_type}")
        combo_orientation.addItem(_("PaperOrientation", "auto"), PaperOrientations.AUTO)
        combo_orientation.addItem(_("PaperOrientation", "portrait"), PaperOrientations.PORTRAIT)
        combo_orientation.addItem(_("PaperOrientation", "landscape"), PaperOrientations.LANDSCAPE)
        combo_orientation.currentTextChanged.connect(self.update_preview)
        form_layout.addRow(_("SettingsDialog", "label_orientation"), combo_orientation)

        # --- 纸张大小 ---
        combo_paper = QComboBox()
        combo_paper.setView(QListView())
        combo_paper.setObjectName(f"paper_{f_type}")
        combo_paper.addItems(PaperSizeHelper.get_display_list())
        combo_paper.setCurrentIndex(PaperSizeHelper.get_default_index())
        combo_paper.currentTextChanged.connect(self.update_preview)
        form_layout.addRow(_("SettingsDialog", "label_paper_size"), combo_paper)

        # --- 分隔线 ---
        line2 = QFrame()
        line2.setFrameShape(QFrame.HLine)
        form_layout.addRow(line2)

        # 存入字典
        controls_dict["printer"] = combo_printer  
        controls_dict["orientation"] = combo_orientation  
        controls_dict["paper"] = combo_paper

    def _add_duplex_settings(self, form_layout, f_type, controls_dict):
        """添加双面打印设置"""
        duplex_widget = QWidget()
        duplex_layout = QHBoxLayout(duplex_widget)
        duplex_layout.setContentsMargins(0, 0, 0, 0)
        duplex_layout.setSpacing(15)

        bg_duplex = QButtonGroup(self)
        radio_single = QRadioButton(_("DuplexMode", "none"))
        radio_long = QRadioButton(_("DuplexMode", "long_edge"))
        radio_short = QRadioButton(_("DuplexMode", "short_edge"))
        
        radio_single.setObjectName(f"single_{f_type}")
        radio_long.setObjectName(f"long_{f_type}")
        radio_short.setObjectName(f"short_{f_type}")
        
        bg_duplex.addButton(radio_single)
        bg_duplex.addButton(radio_long)
        bg_duplex.addButton(radio_short)
        radio_single.setChecked(True)

        duplex_layout.addWidget(radio_single)
        duplex_layout.addWidget(radio_long)
        duplex_layout.addWidget(radio_short)
        duplex_layout.addStretch()
        form_layout.addRow(_("SettingsDialog", "label_duplex"), duplex_widget)
        
        # 存入字典
        controls_dict["duplex_group"] = bg_duplex
        controls_dict["radio_single"] = radio_single
        controls_dict["radio_long"] = radio_long
        controls_dict["radio_short"] = radio_short

    def _add_layout_mode_settings(self, form_layout, f_type, controls_dict):
        """添加版式设置 (页面缩放 / 一张多页 / 小册子)"""
        tab_layout_mode = QTabWidget()
        tab_layout_mode.setObjectName(f"tab_layout_{f_type}")

        # 选项卡等分拉伸
        tabBar = tab_layout_mode.tabBar()
        tabBar.setDocumentMode(True)

        # --- Tab 1: 页面缩放 ---
        page_scaling = QWidget()
        scaling_layout = QVBoxLayout(page_scaling)
        radio_scaling_actual = QRadioButton(_("ScalingMode", "actual_size"))
        radio_scaling_fit = QRadioButton(_("ScalingMode", "fit_to_printable"))
        radio_scaling_actual.setChecked(True)
            
        scaling_layout.addWidget(radio_scaling_actual)
        scaling_layout.addWidget(radio_scaling_fit)
        scaling_layout.addStretch()

        # --- Tab 2: 一张多页 (N-Up) ---
        page_nup = QWidget()
        nup_form_layout = QVBoxLayout(page_nup)
        nup_widget = NUpSettingsWidget(page_nup,file_type=f_type)
        nup_widget.settingsChanged.connect(self.update_preview)
        nup_form_layout.addWidget(nup_widget)

        # --- Tab 3: 小册子 (Booklet) ---
        page_booklet = QWidget()
        booklet_layout = QFormLayout(page_booklet)
        combo_booklet_dir = QComboBox()
        combo_booklet_dir.setView(QListView())
        combo_booklet_dir.setObjectName(f"booklet_dir_{f_type}")
        combo_booklet_dir.addItem(_("BookletDirection", "ltr"), BookletDirection.LEFT_TO_RIGHT)
        combo_booklet_dir.addItem(_("BookletDirection", "rtl"), BookletDirection.RIGHT_TO_LEFT)
        booklet_layout.addRow(_("SettingsDialog", "label_booklet_direction"), combo_booklet_dir)

        # 将页面添加到 TabWidget
        tab_layout_mode.addTab(page_scaling, _("SettingsDialog", "tab_title_scaling"))
        tab_layout_mode.addTab(page_nup, _("SettingsDialog", "tab_title_nup"))
        tab_layout_mode.addTab(page_booklet, _("SettingsDialog", "tab_title_booklet"))

        label_layout_mode = QLabel(_("SettingsDialog", "label_layout_mode"))
        form_layout.addRow(label_layout_mode)
        form_layout.addRow(tab_layout_mode)

        # 信号连接
        tab_layout_mode.currentChanged.connect(self.on_tab_layout_changed)
        radio_scaling_actual.toggled.connect(self.update_preview)
        radio_scaling_fit.toggled.connect(self.update_preview)
        combo_booklet_dir.currentIndexChanged.connect(self.update_preview)


        # 存入字典
        controls_dict["tab_layout"] = tab_layout_mode
        controls_dict["scaling_actual"] = radio_scaling_actual
        controls_dict["scaling_fit"] = radio_scaling_fit
        controls_dict["nup_widget"] = nup_widget
        controls_dict["combo_booklet_dir"] = combo_booklet_dir

    def _add_ppt_specific_settings(self, form_layout, f_type, controls_dict):
        """添加 PPT 文件类型特有的设置项"""

        # --- PPT 打印内容设置 ---
        combo_ppt_content = QComboBox()
        combo_ppt_content.setView(QListView())
        combo_ppt_content.setObjectName(f"ppt_content_{f_type}")
        for enum_member in PresentationContentType:
            combo_ppt_content.addItem(_("PresentationContentType", enum_member.value), enum_member)
        form_layout.addRow(_("SettingsDialog", "label_print_content"), combo_ppt_content)

        # --- 每页幻灯片数量 ---
        combo_slides_per_page = QComboBox()
        combo_slides_per_page.setView(QListView())
        combo_slides_per_page.setEnabled(False)
        combo_slides_per_page.setObjectName(f"slides_per_page_{f_type}")
        for preset in NUpPreset:
            if preset not in [NUpPreset.CUSTOM,NUpPreset.SIXTEEN_UP]:
                combo_slides_per_page.addItem(str(preset.page_count), preset)
        form_layout.addRow(_("SettingsDialog", "label_nup_preset"), combo_slides_per_page)

        # --- 排序方式 ---
        combo_slides_order = QComboBox()
        combo_slides_order.setView(QListView())
        combo_slides_order.setEnabled(False)
        combo_slides_order.setObjectName(f"slides_order_{f_type}")
        combo_slides_order.addItem(_("LayoutDirection", "left_right_down"), LayoutDirection.LEFT_RIGHT_THEN_DOWN)
        combo_slides_order.addItem(_("LayoutDirection", "top_bottom_right"), LayoutDirection.TOP_BOTTOM_THEN_RIGHT)
        form_layout.addRow(_("SettingsDialog", "label_nup_order"), combo_slides_order)

        # --- PPT 其他选项 (复选框) ---
        ppt_options_widget = QWidget()
        ppt_options_layout = QHBoxLayout(ppt_options_widget)
        ppt_options_layout.setContentsMargins(0, 0, 0, 0)
        ppt_options_layout.setSpacing(15)

        chk_slides_borders = QCheckBox(_("SettingsDialog", "label_nup_border"))
        chk_slides_borders.setChecked(False)
        ppt_options_layout.addSpacing(68)
        ppt_options_layout.addWidget(chk_slides_borders)

        chk_scale_to_fit = QCheckBox(_("ScalingMode", "fit_to_printable"))
        chk_scale_to_fit.setChecked(True)
        ppt_options_layout.addWidget(chk_scale_to_fit)

        ppt_options_layout.addStretch()
        form_layout.addRow(ppt_options_widget)

        # 存入字典
        controls_dict["ppt_content"] = combo_ppt_content  
        controls_dict["slides_per_page"] = combo_slides_per_page  
        controls_dict["slides_order"] = combo_slides_order  
        controls_dict["ppt_draw_border"] = chk_slides_borders  
        controls_dict["ppt_scale_to_fit"] = chk_scale_to_fit  

        # 连接信号
        combo_ppt_content.currentTextChanged.connect(self.toggle_handouts_settings)
        combo_slides_per_page.currentIndexChanged.connect(self.update_preview)
        combo_slides_order.currentIndexChanged.connect(self.update_preview)
        chk_slides_borders.stateChanged.connect(self.update_preview)
        chk_scale_to_fit.stateChanged.connect(self.update_preview)

    def _add_excel_specific_settings(self, form_layout, f_type, controls_dict):
        """添加 Excel 文件类型特有的设置项"""
        
        # --- Excel 特定设置容器 ---
        excel_container = QWidget()
        excel_main_layout = QVBoxLayout(excel_container)
        excel_main_layout.setContentsMargins(0, 0, 0, 0)
        excel_main_layout.setSpacing(12)

        # 每页版数 + 绘制边框
        nup_widget = NUpSettingsWidget(excel_container,file_type=f_type)
        nup_widget.settingsChanged.connect(self.update_preview)
        excel_main_layout.addWidget(nup_widget)

        # --- 缩放设置 ---
        layout_row2 = QHBoxLayout()
        layout_row2.setContentsMargins(0,0,0,0)
        layout_row2.setSpacing(10)

        combo_excel_scaling_mode = QComboBox()
        combo_excel_scaling_mode.setView(QListView())
        combo_excel_scaling_mode.setObjectName(f"excel_scaling_mode_{f_type}")
        for scaleType in ExcelScalingType:
            combo_excel_scaling_mode.addItem(_("ExcelScalingType",scaleType.value),scaleType)
        layout_row2.addWidget(QLabel(_("SettingsDialog", "label_excel_scaling")))
        layout_row2.addWidget(combo_excel_scaling_mode, 1)

        combo_excel_scaling = QComboBox()
        combo_excel_scaling.setView(QListView())
        combo_excel_scaling.setObjectName(f"excel_scaling_value_{f_type}")
        combo_excel_scaling.setEditable(True)
        combo_excel_scaling.setInsertPolicy(QComboBox.NoInsert)
        for scale in ExcelScalePreset:
            combo_excel_scaling.addItem(str(scale.value)+"%",scale)
        combo_excel_scaling.setCurrentIndex(3)
        combo_excel_scaling.setFixedWidth(80)
        layout_row2.addWidget(combo_excel_scaling)
        excel_main_layout.addLayout(layout_row2)
    
        # 存入字典
        controls_dict["nup_widget"] = nup_widget
        controls_dict["excel_scaling_mode"] = combo_excel_scaling_mode  
        controls_dict["excel_scaling_value"] = combo_excel_scaling  

        # 连接信号
        combo_excel_scaling_mode.currentIndexChanged.connect(self.handle_excel_scale_changed)
        combo_excel_scaling.currentIndexChanged.connect(self.handle_excel_scale_value_changed)
        combo_excel_scaling.lineEdit().editingFinished.connect(self.handle_edit_finished)
        combo_excel_scaling.lineEdit().returnPressed.connect(self._on_scale_return_pressed)

        # 将 Excel 容器添加到主表单布局
        form_layout.addRow(excel_container)

    def handle_excel_scale_changed(self,index):
        controls = self.get_current_controls()
        if not controls: return
        combo_mode = controls["excel_scaling_mode"]
        combo_percent = controls["excel_scaling_value"]
        current_mode = combo_mode.currentData()
        should_visible = (current_mode == ExcelScalingType.NORMAL_SIZE) or (current_mode == ExcelScalingType.CUSTOM_SCALING)
        if combo_percent.isVisible != should_visible:
            combo_percent.setVisible(should_visible)
        if combo_mode.currentData() == ExcelScalingType.NORMAL_SIZE:
            self.set_combo_by_enum(combo_percent,ExcelScalePreset.PERCENT_100,ExcelScalePreset)

        self.update_preview()

    def _on_scale_return_pressed(self):
        self._scale_edit_processed = True 
        self._apply_scale_value()
        controls = self.get_current_controls()
        if controls:
            controls["excel_scaling_value"].clearFocus()

    def _apply_scale_value(self):
        controls = self.get_current_controls()
        if not controls:
            return
        combo_scale = controls["excel_scaling_value"]
        combo_mode = controls["excel_scaling_mode"]

        # 解析并规范化文本
        try:
            raw_text = combo_scale.currentText().strip()
            scale_value = int(raw_text.replace('%', '').strip())
        except ValueError:
            return

        # 阻塞信号，防止循环
        combo_scale.blockSignals(True)
        combo_scale.lineEdit().setText(f"{scale_value}%")
        combo_scale.blockSignals(False)

        # 更新缩放模式
        if scale_value != 100:
            self.set_combo_by_enum(combo_mode, ExcelScalingType.CUSTOM_SCALING, ExcelScalingType)
        else:
            self.set_combo_by_enum(combo_mode, ExcelScalingType.NORMAL_SIZE, ExcelScalingType)

        self.update_preview()

    def handle_excel_scale_value_changed(self):
        controls = self.get_current_controls()
        if not controls: return
        if int(controls["excel_scaling_value"].currentText().replace('%', '')) != 100:
            self.set_combo_by_enum(controls["excel_scaling_mode"],ExcelScalingType.CUSTOM_SCALING,ExcelScalingType)
        else:
            self.set_combo_by_enum(controls["excel_scaling_mode"],ExcelScalingType.NORMAL_SIZE,ExcelScalingType)
        controls["excel_scaling_value"].clearFocus()
        self.update_preview()

    def handle_edit_finished(self):
        if self._scale_edit_processed:
            self._scale_edit_processed = False
            return
        controls = self.get_current_controls()
        if not controls: return
        combo_scale = controls["excel_scaling_value"]
        if combo_scale.hasFocus() or combo_scale.lineEdit().hasFocus():
            return
        self._apply_scale_value()

    def toggle_handouts_settings(self, text):
        """根据打印内容类型，启用/禁用讲义相关设置"""
        controls = self.get_current_controls()
        if not controls:
            return

        # 获取当前选中的内容类型
        selected_content_type = controls["ppt_content"].currentData()

        # 判断是否为讲义 (Handout)
        is_handout = (selected_content_type == PresentationContentType.HANDOUTS)
        # 启用或禁用控件
        controls["slides_per_page"].setEnabled(is_handout)
        controls["slides_order"].setEnabled(is_handout)

        # 判断是否是提纲
        if selected_content_type == PresentationContentType.OUTLINE:
            controls["ppt_draw_border"].setEnabled(False)
        else:
            controls["ppt_draw_border"].setEnabled(True)

        # 更新预览
        self.update_preview()

    def on_tab_layout_changed(self,index):
        controls = self.get_current_controls()
        if not controls or "orientation" not in controls:
            return
        target = next((i for i in self.all_items if i.row_id == self.current_row_id), None)
        if not target or not hasattr(target, 'params'):return
        p = target.params
        if index == 2:
            controls['orientation'].setEnabled(False)
            controls['orientation'].setCurrentIndex(2)
        else:
            controls['orientation'].setEnabled(True)
        self.update_preview()


    def update_duplex_mode(self,printer_name):
        if self.current_row_id == -1:return
            
        target = next((i for i in self.all_items if i.row_id == self.current_row_id), None)
        if not target or not hasattr(target, 'params'):return
        p = target.params
        controls = self.get_current_controls()
        if not controls:return

        can_dulex_mode = PrinterHelper.check_duplex_support(printer_name)
        
        p.can_set_duplex = can_dulex_mode

        if hasattr(p, 'duplex_mode') and p.duplex_mode:
            mode = p.duplex_mode
            controls["radio_single"].setEnabled(p.can_set_duplex)
            controls["radio_long"].setEnabled(p.can_set_duplex)
            controls["radio_short"].setEnabled(p.can_set_duplex)
            if not p.can_set_duplex:
                controls["radio_single"].setChecked(True)
            elif mode == DuplexMode.NONE:
                controls["radio_single"].setChecked(True)
            elif mode == DuplexMode.LONG_EDGE:
                controls["radio_long"].setChecked(True)
            elif mode == DuplexMode.SHORT_EDGE:
                controls["radio_short"].setChecked(True)

    def _get_preview_file_path(self) -> Optional[str]:
        """获取当前应该预览的文件路径"""
        current_index = self.tabs.currentIndex()
        if current_index < 0 or current_index >= len(FLAT_FILE_TYPES):
            return None
        
        current_type = FLAT_FILE_TYPES[current_index]
        
        # 优先使用选中文档
        if self.current_row_id != -1:
            target_item = next((i for i in self.all_items if i.row_id == self.current_row_id), None)
            if target_item and target_item.file_type == current_type:
                if os.path.exists(target_item.file_path):
                    return target_item.file_path
        
        # 否则用第一个存在的文件
        files_in_type = self.grouped_data.get(current_type, [])
        for f in files_in_type:
            if os.path.exists(f.file_path):
                return f.file_path

        # 最后 fallback：任意存在的文件
        for item in self.all_items:
            if os.path.exists(item.file_path):
                return item.file_path
        
        return None

    def load_current_params(self):
        """加载当前选中文档的参数到UI"""
        if self.current_row_id == -1: return
            
        target = next((i for i in self.all_items if i.row_id == self.current_row_id), None)
        if not target or not hasattr(target, 'params'): return
            
        p = target.params
        controls = self.get_current_controls()
        if not controls: return

        widgets_to_block = []
        for key in ['scaling_actual','ppt_draw_border','ppt_scale_to_fit',
            'excel_scaling_value','scaling_fit','tab_layout']:
            if key in controls and controls[key]:
                widgets_to_block.append(controls[key])
                controls[key].blockSignals(True)

        # 设置打印机
        if hasattr(p, 'printer') and p.printer:
            idx = controls["printer"].findText(p.printer)
            if idx >= 0:
                controls["printer"].setCurrentIndex(idx)
        # 设置双面模式
        self.update_duplex_mode(controls["printer"].currentText())

        target_tab_index = 0 # 默认为 Scaling
        if hasattr(p, 'layout_mode') and (target.file_type in ["Word","PDF"]):
            if p.layout_mode == LayoutMode.N_UP:
                target_tab_index = 1
                controls["nup_widget"].load_params(p.n_up_layout)
            elif p.layout_mode == LayoutMode.BOOKLET:
                target_tab_index = 2
                if hasattr(p.booklet, 'direction'):
                    self.set_combo_by_enum(controls["combo_booklet_dir"], p.booklet.direction, BookletDirection)
            else:
                target_tab_index = 0
                # 设置缩放模式
                if hasattr(p, 'scaling_mode'):
                    if p.scaling_mode == ScalingMode.ACTUAL_SIZE:
                        controls["scaling_actual"].setChecked(True)
                    else:
                        controls["scaling_fit"].setChecked(True)
            controls["tab_layout"].setCurrentIndex(target_tab_index)

        # 纸张方向
        if "orientation" in controls and hasattr(p, 'orientation') and p.orientation:
            self.set_combo_by_enum(controls["orientation"],p.orientation,PaperOrientations)

        # 纸张大小
        if hasattr(p, 'paper_size') and p.paper_size:
            idx = controls["paper"].findText(p.paper_size)
            if idx >= 0:
                controls["paper"].setCurrentIndex(idx)

        if p.document_options:
            # PPT设置
            if isinstance(p.document_options, PresentationPrintOptions):
                # 打印内容
                if p.document_options.content_type:
                    self.set_combo_by_enum(controls["ppt_content"], p.document_options.content_type, PresentationContentType)
                
                # 每页幻灯片数量
                if p.document_options.handout_slides_per_page:
                    self.set_combo_by_enum(controls["slides_per_page"], p.document_options.handout_slides_per_page, NUpPreset)
                
                # 排序方式
                if p.document_options.handout_layout_order:
                    self.set_combo_by_enum(controls["slides_order"], p.document_options.handout_layout_order, LayoutDirection)
                
                # 全局选项
                controls["ppt_draw_border"].setChecked(p.document_options.draw_slide_border)
                is_fit_to_page = p.scaling_mode == ScalingMode.FIT_TO_PRINTABLE
                controls["ppt_scale_to_fit"].setChecked(is_fit_to_page)
            # Excel参数设置
            elif isinstance(p.document_options,ExcelPrintOptions):
                opts = p.document_options
                if opts.scaling_type:
                    self.set_combo_by_enum(controls["excel_scaling_mode"],opts.scaling_type,ExcelScalingType)
                if opts.custom_scale_percent:
                    controls["excel_scaling_value"].setCurrentText(str(opts.custom_scale_percent)+"%")
                if p.n_up_layout:
                    controls["nup_widget"].load_params(p.n_up_layout) 

        for widget in widgets_to_block:
            if hasattr(widget, 'blockSignals'):
                widget.blockSignals(False)

    def set_combo_by_enum(self,combo, enum_value, enum_class=None):
        if isinstance(enum_value, str) and enum_class:
            try:
                enum_value = enum_class(enum_value)
            except ValueError:
                return False
        target_index = -1
        for i in range(combo.count()):
            if combo.itemData(i) == enum_value:
                target_index = i
                break
        was_blocked = combo.blockSignals(True)
        try:
            combo.setCurrentIndex(target_index)
            return True
        finally:
            combo.blockSignals(was_blocked)

    def update_preview(self):
        """更新真实文档预览"""
        file_path = self._get_preview_file_path()
        if not file_path:
            logger.debug("No files available for preview")
            self.previewer.clear_preview()
            return
        if not self.previewer:
            return
        logger.debug(f"Update Preview: {os.path.basename(file_path)}")
        # 获取设置参数
        params = self.get_current_params()
        # 构建预览更新参数
        new_params = {}
        new_params['file_path'] = file_path
        new_params["page_range"] = params.page_range
        new_params["paper_size"] = params.paper_size
        new_params["orientation"] = params.orientation
        new_params["scaling_mode"] = params.scaling_mode
        new_params["layout_mode"] = params.layout_mode
        new_params["nup_rows"] = params.n_up_layout.rows
        new_params["nup_cols"] = params.n_up_layout.cols
        new_params["nup_dir"] = params.n_up_layout.direction
        new_params["nup_draw_border"] = params.n_up_layout.draw_border
        new_params["booklet_direction"] = params.booklet.direction
        if params.document_options:
            new_params["doc_options"] = params.document_options
            if isinstance(params.document_options, ExcelPrintOptions):
                new_params["layout_mode"] = LayoutMode.N_UP
                new_params["doc_options"].is_landscape = (params.orientation == PaperOrientations.LANDSCAPE)
        # 同步预览参数
        self.previewer.update_preview_params(new_params)

    def get_current_params(self):
        controls = self.get_current_controls()
        if not controls:
            return

        # 构建参数
        target = next((i for i in self.all_items if i.row_id == self.current_row_id), None)
        params = copy.deepcopy(target.params)
        params.printer = controls["printer"].currentText()
        params.paper_size = controls["paper"].currentText()

        # 方向
        if "orientation" in controls:
            params.orientation = controls["orientation"].currentData()
        else:
            params.orientation = PaperOrientations.AUTO

        # 布局与缩放参数
        if self.current_type in ["Word","PDF"]:
            current_layout_index = controls["tab_layout"].currentIndex()
            if current_layout_index == 0:
                params.layout_mode = LayoutMode.PAGE_SCALE
                # 缩放模式
                if "scaling_actual" in controls:
                    if controls["scaling_actual"].isChecked():
                        params.scaling_mode = ScalingMode.ACTUAL_SIZE
                    else:
                        params.scaling_mode = ScalingMode.FIT_TO_PRINTABLE
            elif current_layout_index == 1:
                params.layout_mode = LayoutMode.N_UP
                nup_params = controls["nup_widget"].get_params()
                params.n_up_layout.preset_value = nup_params.preset_value
                params.n_up_layout.cols = nup_params.cols
                params.n_up_layout.rows = nup_params.rows
                # N-Up 方向
                params.n_up_layout.direction = nup_params.direction
                # 边框
                params.n_up_layout.draw_border = nup_params.draw_border
            elif current_layout_index == 2:
                params.layout_mode = LayoutMode.BOOKLET
                # 小册子方向
                params.booklet.direction = controls["combo_booklet_dir"].currentData()
        elif self.current_type == "PPT":
            ppt_options = PresentationPrintOptions()
            # 获取当前选择的内容类型
            ppt_options.content_type = controls["ppt_content"].currentData()
            # 如果是讲义模式，设置相关参数
            if ppt_options.content_type == PresentationContentType.HANDOUTS:
                ppt_options.handout_slides_per_page = controls["slides_per_page"].currentData()
                ppt_options.handout_layout_order = controls["slides_order"].currentData()
            
            ppt_options.draw_slide_border = controls["ppt_draw_border"].isChecked()
            
            if controls["ppt_scale_to_fit"].isChecked():
                params.scaling_mode = ScalingMode.FIT_TO_PRINTABLE
            else:
                params.scaling_mode = ScalingMode.ACTUAL_SIZE

            params.document_options = ppt_options
        elif self.current_type == "Excel":
            params.document_options.scaling_type = controls["excel_scaling_mode"].currentData()
            params.document_options.custom_scale_percent = controls["excel_scaling_value"].currentText().replace("%","")
            nup_params = controls["nup_widget"].get_params()
            params.n_up_layout.preset_value = nup_params.preset_value
            params.n_up_layout.rows = nup_params.rows
            params.n_up_layout.cols = nup_params.cols
            params.n_up_layout.draw_border = nup_params.draw_border
            params.n_up_layout.direction = nup_params.direction

        # 双面模式
        if controls["radio_long"].isChecked():
            params.duplex_mode = DuplexMode.LONG_EDGE
        elif controls["radio_short"].isChecked():
            params.duplex_mode = DuplexMode.SHORT_EDGE
        else:
            params.duplex_mode = DuplexMode.NONE

        return params

    def apply_params(self, scope: str):
        """全局应用逻辑"""
        current_index = self.tabs.currentIndex()
        if current_index < 0:
            return
            
        target_type = FLAT_FILE_TYPES[current_index]
        params = self.get_current_params()
        target_ids = []
        confirm_msg = ""
        if scope == 'single':
            if self.current_row_id == -1:
                msg = _("SettingsDialog", "message_error_not_selected")
                CustomMessageBox(QMessageBox.Icon.Warning,_("Common","error"),msg,None,self).exec()
                return
                
            target_item = next((i for i in self.all_items if i.row_id == self.current_row_id), None)
            if not target_item or target_item.file_type != target_type:
                msg = _("SettingsDialog", "message_error_wrong_type",type=target_type)
                CustomMessageBox(QMessageBox.Icon.Warning,_("Common","error"),msg,None,self).exec()
                return 
                
            target_ids = [self.current_row_id]
            confirm_msg = _("SettingsDialog","message_confirm_single",type=target_type)

        elif scope == 'all':
            items = self.grouped_data.get(target_type, [])
            if not items:
                msg = _("SettingsDialog","message_error_no_documents",type=target_type)
                CustomMessageBox(QMessageBox.Icon.Information,_("Common","info"),msg,None,self).exec()
                return 
                
            target_ids = [item.row_id for item in items]
            confirm_msg = _("SettingsDialog","message_confirm_all",type=target_type,count=len(target_ids))
            
        # 二次确认
        if len(target_ids) > 1:
            reply = CustomMessageBox(QMessageBox.Icon.Question,_("SettingsDialog","message_title_confirm_action"),
                confirm_msg,QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,self).exec()
            if reply != QMessageBox.StandardButton.Yes:
                return

        target_count = len(target_ids)
        logger.info(f"Apply print parameters: Scope={scope}, Type={target_type}, Count={target_count}")
        
        if scope == 'all':
            logger.debug(f"Batch update parameters of {target_count} files")
        else:
            logger.debug(f"Update single file parameters: ID={self.current_row_id}")

        # 执行更新
        if self.parent():
            for rid in target_ids:
                self.parent().update_file_params(rid, params)

        # 成功反馈
        
        msg = _("SettingsDialog","message_success_all",count=len(target_ids),type=target_type) if scope == 'all' else _("SettingsDialog","message_success_single")
        QMessageBox.information(self, _("Common","success"), msg)
        logger.info("Parameter applied successfully, close the dialog box")
        self.accept()

    def get_current_controls(self):
        """获取当前选中 Tab 内的所有控件"""
        current_tab_widget = self.tabs.currentWidget()
        if not current_tab_widget:
            return None
        return current_tab_widget.property("controls")