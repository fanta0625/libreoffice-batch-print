# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from enum import Enum
from abc import ABC

class DocumentPrintOptions(ABC):
    """所有文档打印选项的基类"""
    def to_dict(self) -> Dict[str, Any]:
        """序列化方法"""
        raise NotImplementedError

class LayoutMode(Enum):
    """打印布局模式（互斥）"""
    PAGE_SCALE = "page_scale" # 页面缩放
    N_UP = "n_up"                     # 多页合一
    BOOKLET = "booklet"                # 小册子

class ScalingMode(Enum):
    ACTUAL_SIZE = "actual_size"
    FIT_TO_PRINTABLE = "fit_to_printable"

class PageRangeType(Enum):
    ALL = "all"
    ODD = "odd"
    EVEN = "even"
    CUSTOM = "custom"

class DuplexMode(Enum):
    NONE = "none"
    LONG_EDGE = "long_edge"
    SHORT_EDGE = "short_edge"

class PaperOrientations(Enum):
    AUTO = "auto"
    PORTRAIT = "portrait"
    LANDSCAPE = "landscape"

class LayoutDirection(Enum):
    LEFT_RIGHT_THEN_DOWN = "left_right_down"
    RIGHT_LEFT_THEN_DOWN = "right_left_down"
    TOP_BOTTOM_THEN_RIGHT = "top_bottom_right"
    TOP_BOTTOM_THEN_LEFT = "top_bottom_left"
    # 扩展
    BOTTOM_TOP_THEN_RIGHT = "bottom_top_right"
    BOTTOM_TOP_THEN_LEFT = "bottom_top_left"
    LEFT_RIGHT_THEN_TOP = "left_right_top"
    RIGHT_LEFT_THEN_TOP = "right_left_top"

class BookletDirection(Enum):
    """小册子书写方向"""
    LEFT_TO_RIGHT = "ltr"  # 从左向右
    RIGHT_TO_LEFT = "rtl"  # 从右向左 

class NUpPreset(Enum):
    """
    N-Up 预设模式枚举
    """
    # 格式: 枚举名 = (键值, 描述, 总页数)
    ONE_UP = ("1up", "nup_1_page", 1)
    TWO_UP = ("2up", "nup_2_page", 2)
    THREE_UP = ("3up", "nup_3_page", 3)
    FOUR_UP = ("4up", "nup_4_page", 4)
    SIX_UP = ("6up", "nup_6_page", 6)
    NINE_UP = ("9up", "nup_9_page", 9)
    SIXTEEN_UP = ("16up", "nup_16_page", 16)
    CUSTOM = ("custom", "nup_custom", -1)  # 特殊值 -1 代表需要使用自定义参数

    def __init__(self, key: str, label: str, page_count: int):
        self.key = key
        self.label = label
        self.page_count = page_count
    
    @staticmethod
    def get_preset_by_count(count: int) -> Optional['NUpPreset']:
        """根据页数获取对应的预设枚举"""
        for preset in NUpPreset:
            if preset.page_count == count:
                return preset
        return None

# ========== 文档类型枚举 ==========
class DocumentType(Enum):
    """支持的文档类型"""
    WRITER = "writer"          # Word 文档
    IMPRESS = "impress"        # PPT 演示文稿
    DRAW = "draw"              # PDF/图片
    CALC = "calc"              # Excel 表格（预留）
    UNKNOWN = "unknown"

# ========== PPT 打印内容类型 ==========
class PresentationContentType(Enum):
    SLIDES = "slides"          # 幻灯片
    HANDOUTS = "handouts"      # 讲义（每页多张幻灯片）
    NOTES = "notes"            # 备注页
    OUTLINE = "outline"        # 提纲

@dataclass
class PresentationPrintOptions(DocumentPrintOptions):
    """PPT 打印专用选项"""
    content_type: PresentationContentType = PresentationContentType.SLIDES
    # 讲义模式有效：每页幻灯片数量
    handout_slides_per_page: NUpPreset = NUpPreset.ONE_UP
    # 讲义布局顺序
    handout_layout_order: LayoutDirection = LayoutDirection.LEFT_RIGHT_THEN_DOWN
    # 是否打印幻灯片边框
    draw_slide_border: bool = False

# ==========Excel 数据模型 ===============

class ExcelPrintMode(Enum):
    """Excel 打印模式"""
    ACTIVE_SHEET = "active_sheet"
    ENTIRE_WORKBOOK = "entire_workbook"
    SELECTION = "selection"
    DEFINED_RANGE = "defined_range"

class ExcelScalingType(Enum):
    """Excel 缩放类型"""
    NORMAL_SIZE = "normal_size"                 # 无打印缩放
    FIT_ALL_COLUMNS_ON_ONE_PAGE = "fit_all_columns_on_one_page"  # 将所有列打印在一页
    FIT_ALL_ROWS_ON_ONE_PAGE = "fit_all_rows_on_one_page"        # 将所有行打印在一页
    FIT_SHEET_ON_ONE_PAGE = "fit_sheet_on_one_page"              # 将工作表打印在一页
    CUSTOM_SCALING = "custom_scaling"         # 自定义缩放

class ExcelScalePreset(Enum):
    """
    Excel 常用的预设缩放比例
    当 scaling_type == CUSTOM_PERCENTAGE 时，推荐使用这些值
    """
    PERCENT_25 = 25
    PERCENT_50 = 50
    PERCENT_75 = 75
    PERCENT_100 = 100
    PERCENT_200 = 200

@dataclass
class ExcelPrintOptions(DocumentPrintOptions):
    """
    Excel (Calc) 打印专用选项
    """
    # 打印范围模式
    print_mode: ExcelPrintMode = ExcelPrintMode.ENTIRE_WORKBOOK
    
    # 仅当 print_mode == DEFINED_RANGE 时有效
    custom_range: str = "" 
    sheet_index: int = 0
    
    # 缩放设置
    scaling_type: ExcelScalingType = ExcelScalingType.NORMAL_SIZE
    custom_scale_percent: int = 100  
    
    # 重复打印（顶端标题行/左端标题列）
    repeat_rows: str = "" # 如 "1:3" 表示重复第1-3行
    repeat_cols: str = "" # 如 "A:C" 表示重复A-C列
    
    # 打印顺序 (先列后行 vs 先行后列)
    print_order: LayoutDirection = LayoutDirection.LEFT_RIGHT_THEN_DOWN

@dataclass
class NUpLayout:
    """
    多页打印布局配置
    当 mode 为 CUSTOM 时，使用 cols/rows；否则使用 preset_value
    """
    enabled: bool = False
    # 预设模式 (1, 2, 4, 6, 9, 16) 或 CUSTOM
    preset_value: int = NUpPreset.ONE_UP.page_count  
    
    # 自定义模式参数 (当 preset_value == -1 时表示自定义)
    rows: int = 1
    cols: int = 1
    # 边距 (单位: 毫米)
    cell_margin_x: float = 0  # 页面之间的水平间距
    cell_margin_y: float = 0  # 页面之间的垂直间距
    edge_margin: float = 0  # 内容到纸张边缘的距离
    
    direction: LayoutDirection = LayoutDirection.LEFT_RIGHT_THEN_DOWN
    draw_border: bool = False # 是否绘制边框

    @staticmethod
    def get_label_by_page_count(count: int) -> Optional[str]:
        """
        根据页数获取对应的描述 Label
        :param count: 页数 (如 1, 2, 4, 6 等)
        :return: 对应的 label 字符串，未找到返回 None
        """
        for preset in NUpPreset:
            if preset.page_count == count:
                return preset.label
        return None

    @staticmethod
    def get_layout_info(page_count: int) -> tuple:
        """
        直接通过页数获取行和列
        返回: (rows, cols)
        """
        mapping = {1: (1, 1), 2: (1, 2),3: (3, 1), 4: (2, 2), 6: (2, 3), 9: (3, 3), 16: (4, 4)}
        return mapping.get(page_count, (1, 1)) # 默认返回 1x1

@dataclass
class BookletSettings:
    """
    小册子打印设置
    """
    enabled: bool = False
    # 书写方向：决定折叠后的阅读顺序
    direction: BookletDirection = BookletDirection.LEFT_TO_RIGHT 
    # 小册子通常需要特定的纸张方向，可以在 PrintParams 中通过 orientation 控制

@dataclass
class PrintParams:
    """打印参数模型"""
    printer: str = "system_default"
    orientation: PaperOrientations = PaperOrientations.AUTO  # 自动，横向，竖向
    paper_size: str = "A4 (841mm x 1189mm)"
    copies: int = 1
    duplex_mode: DuplexMode = DuplexMode.NONE
    can_set_duplex:bool = False
    page_range: str = "" # 例如 "1-5"
    layout_mode: LayoutMode = LayoutMode.PAGE_SCALE
    scaling_mode: ScalingMode = ScalingMode.ACTUAL_SIZE  # 默认
    # 多页打印/小册子
    n_up_layout: NUpLayout = field(default_factory=NUpLayout)
    booklet: BookletSettings = field(default_factory=BookletSettings)
    document_options: Optional[DocumentPrintOptions] = None
    def is_nup_custom(self) -> bool:
        """检查是否为自定义 N-Up 模式"""
        return self.n_up_layout.preset_value == -1

@dataclass
class FileItem:
    """文件列表项模型"""
    row_id: int
    file_path: str
    file_name: str
    file_type: str
    total_pages: int
    page_range: str = ""
    params: PrintParams = field(default_factory=PrintParams)
    status: str = ""

    def get_effective_range(self) -> str:
        if self.page_range:
            return self.page_range
        elif self.params.page_range:
            return self.params.page_range
        return f"1-{self.total_pages}"

