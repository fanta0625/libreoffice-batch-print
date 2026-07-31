# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from utils.utils import get_port,get_executable_path
STYLESHEET = """
    QMainWindow { background-color: #f5f6f8; }
    QWidget { font-family: "Segoe UI", "Microsoft YaHei", sans-serif; font-size: 13px; color: #333; }
    QWidget#listContainer { background-color: white; border-radius: 8px; border: 1px solid #e0e0e0;}
    QWidget#bottomContainer {background-color: transparent;}
    QLabel#listStatusLabel {max-height:20px;margin-top:18px;color: #666;padding-right:5px;font-size:12px;}
    QLabel#statusLabel {color:#666;font-size:12px;}
    QLabel#preview_header{font-size: 13px; color: #34495e;}
    QGroupBox { border: 1px solid #e0e0e0; border-radius: 8px; margin-top: 12px; padding-top: 10px; background-color: white; }
    QGroupBox::title { subcontrol-origin: margin; left: 15px; padding: 0 8px; color: #555; }
    QPushButton { background-color: #ffffff; border: 1px solid #ddd; border-radius: 4px;padding:5px 16px;}
    QPushButton:hover { background-color: #f0f0f0; border-color: #c0c0c0; }
    QPushButton:disabled { background-color: #f0f0f0; color: #bbb;}
    QPushButton:pressed { background-color: #e0e0e0; }
    QPushButton#btnAddFile {padding: 5px 12px; }
    QPushButton#btnAddFile:hover {background-color:#f9f9f9;}
    QPushButton#btnAddFolder {padding: 5px 12px; }
    QPushButton#btnAddFolder:hover {background-color:#f9f9f9;}
    QPushButton#btnDelFile {padding: 5px 12px; }
    QPushButton#btnDelFile:hover {background-color:#f9f9f9;}
    QPushButton#btnDel {padding: 4px 10px;border-radius: 6px;border:none;}
    QPushButton#btnDel:hover {background-color: #f0f0f0;}
    QPushButton#btnDel:pressed { background-color: #e0e0e0;}
    QPushButton#btnSet {padding: 6px 10px;border-radius: 6px;border:none;}
    QPushButton#btnSet:hover {background-color: #f0f0f0;}
    QPushButton#btnSet:pressed { background-color: #e0e0e0;}
    QPushButton#btnPrint { background-color: #0078D4; color: white;padding:6px 18px;border:none; border-radius: 4px;}
    QPushButton#btnPrint:hover { background-color: #0063B1; }
    QPushButton#btnPrint:disabled { background-color: #e0e0e0; color: #bbb;}
    QPushButton#btnClose { background-color: #ffffff; color: #555; border: 1px solid #ccc; padding:6px 18px; border-radius: 4px;}
    QPushButton#btnClose:hover { background-color: #f0f0f0; }
    QPushButton#btnApplySingle { border:1px solid #eee; border-radius: 4px;padding:5px 15px}
    QPushButton#btnApplySingle:hover { background-color: #f7f7f7;}
    QPushButton#btnApplySingle:disabled {background-color: #e0e0e0; color: #bbb;}
    QPushButton#btnApplyAll { background-color: #27ae60; color: white;border:none; border-radius: 4px;padding:5px 15px}
    QPushButton#btnApplyAll:hover { background-color: #219150; }
    QPushButton#btnFirst{font-size:12px;padding:4px 10px;}
    QPushButton#btnPrev{font-size:12px;padding:4px 10px;}
    QPushButton#btnNext{font-size:12px;padding:4px 10px;}
    QPushButton#btnLast{font-size:12px;padding:4px 10px;}
    QComboBox::down-arrow {image:url(':/images/resources/arrow_down.png');width: 12px;height:12px;margin-right: 4px;}
    QComboBox::drop-down {border: none;width:20px;}
    QComboBox QAbstractItemView { background-color: white; border: 1px solid #dcdcdc; selection-background-color: #e0e0e0; outline: none;}
    QComboBox QAbstractItemView::item {min-height: 30px; padding: 5px 10px; border: none; margin: 1px 2px; border-radius: 2px;}
    QComboBox QAbstractItemView::item:selected { background-color: #eee;color:black; border: none;}
    QTableWidget { background-color: white; border: 1px solid #e0e0e0; border-radius: 8px; gridline-color: #f0f0f0; selection-background-color: #e5f3ff; selection-color: #333; }
    QTableWidget::item { padding: 0px; border-bottom: 1px solid #f5f5f5; }
    QHeaderView {background-color:transparent;}
    QHeaderView::section { background-color: #f7f7f7; padding: 12px; border: none; text-align: center; color:#333;}
    QHeaderView::section:first {border-top-left-radius: 8px;}
    QHeaderView::section:last {border-top-right-radius: 8px;}
    QComboBox { border: 1px solid #dcdcdc; border-radius: 4px; padding: 5px 10px; background-color: white; selection-background-color: #0078D4; }
    QComboBox:disabled {background-color: #f2f2f2;color: #ccc;border: 1px solid #e0e0e0;}
    QLineEdit{ border: 1px solid #dcdcdc; border-radius: 4px; background-color: white; selection-background-color: #0078D4;height:30px }
    QLineEdit:focus, QComboBox:focus { border-color: #0078D4; }
    QSpinBox { border: 1px solid #dcdcdc; border-radius: 4px; padding: 0px; background-color: white; height:30px;max-height:30px;}
    QSpinBox:focus { border-color: #0078D4; }
    QSpinBox:disabled {background: #f0f0f0; color: #aaa;}
    QSpinBox::up-button, QSpinBox::down-button { border: none; background: transparent; width: 0; }
    QDialog { background-color: #f5f6f8; }
    QTabWidget#tab_file_type::pane { border: 1px solid #e0e0e0;border-bottom-left-radius:8px;border-bottom-right-radius:8px;margin-left:1px;border-top-right-radius:8px; background: white; top: -1px; }
    QTabWidget#tab_file_type > QTabBar::tab { background: #e9ecef; color: #555;border:1px solid #e0e0e0;border-bottom:none;padding: 8px 20px; border-top-left-radius: 4px; border-top-right-radius: 4px; margin-right: 2px; font-weight: 600; }
    QTabWidget#tab_file_type > QTabBar::tab:selected { background: white; color: #0078D4;}
    QTabWidget#tab_file_type > QTabBar::tab:hover:!selected { background: #dde2e6; }
    QTabWidget#tab_file_type > QTabBar::tab:disabled { background: #f0f0f0; color: #aaa;}
    QTabWidget[objectName^="tab_layout"] > QTabBar {border:1px solid #eee;border-radius:4px;max-height:40px;}
    QTabWidget[objectName^="tab_layout"] > QTabBar::tab {padding:3px 8px;margin:3px 5px;background-color:transparent;border-radius:3px;font-weight:normal;}
    QTabWidget[objectName^="tab_layout"] > QTabBar::tab:selected {background: #f0f0f0;}
    QTabWidget[objectName^="tab_layout"] > QTabBar::tab:hover {background-color:#f7f7f7;}
    QTabWidget[objectName^="tab_layout"]:pane{margin-top:5px;border:none;}
    QFrame#preview_frame {background-color:#f7f7f7;border-radius: 10px;border: 1px solid #ccc;}
    QFrame#footerFrame {background-color: #f8f9fa; border-top: 1px solid #ddd; padding: 10px;}
    QFrame[frameShape="4"] { color: #dddddd;}
    QScrollBar:vertical {border: none;background: #f0f0f0; width: 6px; margin: 0px 0px 0px 0px; border-radius: 3px; }
    QScrollBar::handle:vertical { background: #d0d0d0; min-height: 20px; border-radius: 3px;}
    QScrollBar::handle:vertical:hover { background: #c0c0c0;}
    QScrollBar::add-line:vertical { height: 0px; subcontrol-position: bottom; subcontrol-origin: margin;}
    QScrollBar::sub-line:vertical { height: 0px; subcontrol-position: top; subcontrol-origin: margin;}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none;}
    QRadioButton:disabled {color:#ccc;}
    QCheckBox:disabled {color:#ccc}
    QProgressBar#previewProgress {background-color: lightgray; border: none;height: 14px;text-align: center;border-radius:7px;color:white;}
    QProgressBar#previewProgress::chunk {background-color: #3366FF;border-radius:7px;}
    QProgressBar[objectName^="progress_row_"] {border:none;border-radius: 5px;background-color: #f0f0f0;text-align: center;}
    QProgressBar[objectName^="progress_row_"]::chunk {background-color: #0078D4;border-radius: 5px;}
"""

SUPPORTED_EXTENSIONS = {
    'PDF': ['.pdf','.ofd','.png','.jpg','.odg'],
    'Word': ['.doc', '.docx', '.odt'],
    'PPT': ['.ppt', '.pptx','.odp','.dps'],
    'Excel': ['.xls', '.xlsx', '.ods']
}

# 分别对应pdf|jpg|png|doc|docx|odt|ofd|odg
ALLOWED_MIMES = [
    'application/pdf', 
    'application/ofd',
    'image/jpeg',  
    'image/png',   
    'application/msword',   
    'application/vnd.ms-powerpoint',  # PPT (PowerPoint 97-2003)
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',  # PPTX
    'application/vnd.oasis.opendocument.graphics',
    'application/x-wps-office-dps',   # for .dps (WPS Presentation)
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',  
    'application/vnd.oasis.opendocument.text',
    'application/vnd.oasis.opendocument.presentation', # odp    
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.oasis.opendocument.spreadsheet'
]

# PDF、Word、PPT
FLAT_FILE_TYPES = ['PDF', 'Word','PPT','Excel']   

DEFAULT_PRINTER_ID = "__default_printer__"

PAPER_SIZES = [
    {"name": "A3", "width": 297, "height": 420},
    {"name": "A4", "width": 210, "height": 297},
    {"name": "A5", "width": 148, "height": 210},
    # B4 (JIS)
    {"name": "B4", "width": 257, "height": 364},
    # B5 (JIS)
    {"name": "B5", "width": 182, "height": 257},
    # 美国信函 (Letter)
    {"name": "Letter", "width": 216, "height": 279},
    # 美国法律 (Legal)
    {"name": "Legal", "width": 216, "height": 356},
    # 美国半报纸 (Tabloid)
    {"name": "Tabloid", "width": 279, "height": 432},   
    # 美国 (Statement)
    # {"name": "Statement", "width": 140, "height": 216},
    # 行政 (Executive)
    # {"name": "Executive", "width": 184, "height": 267},
]

UNO_CONST = {
    "UNO_PORT":get_port("LBP_UNO_PORT", 8100),
    "IPC_PORT":get_port("LBP_IPC_PORT", 58963),
    "MM_TO_PT":2.83465,
    "HOST":"127.0.0.1",
    "LO_EXECUTABLE":get_executable_path(),
    "PAPER_FORMAT":'com.sun.star.view.PaperFormat',
    "PAPER_ORIENTATION":'com.sun.star.view.PaperOrientation'
}




