# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import fitz 
import tempfile
from typing import Literal, Optional, Tuple, List
from models.file_model import LayoutDirection,PaperOrientations,BookletDirection

def create_nup_pdf(
    input_pdf: str,
    rows: int = 1,
    cols: int = 1,
    layout_order: LayoutDirection = LayoutDirection.LEFT_RIGHT_THEN_DOWN,
    paper_size: Tuple[float, float]=None,  # A4 in mm
    orientation: PaperOrientations = PaperOrientations.AUTO,
    draw_borders: bool = False,
    border_color: Tuple[float, float, float] = (0, 0, 0),
    border_width: float = 0.5
) -> str:
    """
    创建 N-up 布局的 PDF 文件（行列形式）
    """
    factor = 72 / 25.4

    # 验证输入
    if rows < 1 or cols < 1:
        raise ValueError("rows and cols must be >= 1")
    
    # 打开源文档
    src_doc = fitz.open(input_pdf)
    total_pages = len(src_doc)
    
    if total_pages == 0:
        src_doc.close()
        raise ValueError("Input PDF has no pages")
    
    # 存储原始的 rows 和 cols
    original_rows, original_cols = rows, cols

    # 标记是否需要旋转页面内容
    rotate_pages_for_auto = False
    
    # 计算纸张尺寸
    paper_width, paper_height = paper_size[0]*factor, paper_size[1]*factor

    if orientation == PaperOrientations.AUTO:
        first_page = src_doc[0]
        page_width, page_height = first_page.rect.width, first_page.rect.height
        page_aspect_ratio = page_width / page_height if page_height > 0 else 1.0
        # 计算网格的总体宽高比
        grid_aspect_ratio = round((cols * page_aspect_ratio) / rows,3)
        # 计算纸张的宽高比
        paper_aspect_ratio = round(paper_size[0] / paper_size[1],3)
        # 如果网格宽高比大于纸张宽高比，则使用横向布局
        if grid_aspect_ratio > paper_aspect_ratio:
            rotate_pages_for_auto = True
            rows, cols = cols, rows
             # 调整布局顺序
            layout_order = _adjust_layout_for_rotation(layout_order)
    
    # 创建目标文档
    dst_doc = fitz.open()
    
    # 计算单元格尺寸
    cell_width = paper_width / cols
    cell_height = paper_height / rows
    
    # 计算总页面数
    pages_per_sheet = rows * cols
    
    # 处理每个页面组
    for start_page in range(0, total_pages, pages_per_sheet):
        # 创建新页面
        new_page = dst_doc.new_page(width=paper_width, height=paper_height)
        
        # 获取当前组的源页面索引
        current_group_pages = []
        for i in range(pages_per_sheet):
            src_page_idx = start_page + i
            if src_page_idx < total_pages:
                current_group_pages.append(src_page_idx)
        
        # 计算所有子页面的位置（使用可能交换后的 rows/cols）
        positions = _calculate_positions(len(current_group_pages), rows, cols, layout_order, cell_width, cell_height)
        
        # 放置每个子页面
        for i, (src_page_idx, (x, y)) in enumerate(zip(current_group_pages, positions)):
            src_page = src_doc[src_page_idx]
            src_rect = src_page.rect
            
            if rotate_pages_for_auto:
                rotated_width = src_rect.height
                rotated_height = src_rect.width
                # 完全适应单元格
                scale_x = cell_width / rotated_width
                scale_y = cell_height / rotated_height
                scale = min(scale_x, scale_y)
                
                # 计算居中位置
                scaled_rotated_width = rotated_width * scale
                scaled_rotated_height = rotated_height * scale
                target_x = x + (cell_width - scaled_rotated_width) / 2
                target_y = y + (cell_height - scaled_rotated_height) / 2
                
                # 创建目标矩形
                target_rect = fitz.Rect(
                    target_x, 
                    target_y, 
                    target_x + scaled_rotated_width, 
                    target_y + scaled_rotated_height
                )
                
                # 使用 show_pdf_page 实现变换
                new_page.show_pdf_page(
                    target_rect, 
                    src_doc, 
                    src_page_idx,
                    rotate=90,  # 直接指定旋转角度
                    clip=src_rect
                )
                    
                
            else:
                # 不需要旋转的正常处理
                # 首先计算缩放比例以保持宽高比
                src_w,src_h= src_rect.width,src_rect.height
                scale_x = cell_width / src_w
                scale_y = cell_height / src_h
                scale = min(scale_x, scale_y)

                scaled_w = src_w * scale
                scaled_h = src_h * scale

                # 居中计算
                target_x = x + (cell_width - scaled_w) / 2
                target_y = y + (cell_height - scaled_h) / 2

                # 创建目标矩形
                target_rect = fitz.Rect(
                    target_x,
                    target_y,
                    target_x + scaled_w,
                    target_y + scaled_h
                )

                new_page.show_pdf_page(target_rect, src_doc, src_page_idx)
            
            # 绘制边框
            if draw_borders:
                new_page.draw_rect(target_rect,
                    color=border_color,
                    width=border_width
                )
    
    # 清理源文档
    src_doc.close()
    
    # 保存输出文件
    output_path = tempfile.mktemp(suffix=".pdf")
    dst_doc.save(output_path, garbage=4, deflate=True)
    dst_doc.close()
    
    return output_path


def _calculate_positions(
    num_pages: int, 
    rows: int, 
    cols: int,
    layout_order: LayoutDirection,
    cell_width: float,
    cell_height: float
) -> List[Tuple[float, float]]:
    """
    计算页面在网格中的位置坐标
    """
    positions = []
    
    if layout_order == LayoutDirection.LEFT_RIGHT_THEN_DOWN:
        for i in range(num_pages):
            row = i // cols
            col = i % cols
            x = col * cell_width
            y = row * cell_height
            positions.append((x, y))
            
    elif layout_order == LayoutDirection.RIGHT_LEFT_THEN_DOWN:
        for i in range(num_pages):
            row = i // cols
            col = (cols - 1) - (i % cols)
            x = col * cell_width
            y = row * cell_height
            positions.append((x, y))
            
    elif layout_order == LayoutDirection.TOP_BOTTOM_THEN_RIGHT:
        for i in range(num_pages):
            col = i // rows
            row = i % rows
            x = col * cell_width
            y = row * cell_height
            positions.append((x, y))
            
    elif layout_order == LayoutDirection.TOP_BOTTOM_THEN_LEFT:
        for i in range(num_pages):
            col = (cols - 1) - (i // rows)
            row = i % rows
            x = col * cell_width
            y = row * cell_height
            positions.append((x, y))

    elif layout_order == LayoutDirection.BOTTOM_TOP_THEN_RIGHT:
        for i in range(num_pages):
            col = i // rows
            row = (rows - 1) - (i % rows)  # 从底部开始向上
            x = col * cell_width
            y = row * cell_height
            positions.append((x, y))
            
    elif layout_order == LayoutDirection.BOTTOM_TOP_THEN_LEFT:
        for i in range(num_pages):
            col = (cols - 1) - (i // rows)  # 从右侧开始向左
            row = (rows - 1) - (i % rows)   # 从底部开始向上
            x = col * cell_width
            y = row * cell_height
            positions.append((x, y))

    elif layout_order == LayoutDirection.LEFT_RIGHT_THEN_TOP:
        for i in range(num_pages):
            # 从底部开始向上：总行数 - 1 - 当前行索引
            row_from_top = i // cols
            row = (rows - 1) - row_from_top
            col = i % cols
            x = col * cell_width
            y = row * cell_height
            positions.append((x, y))
            
    elif layout_order == LayoutDirection.RIGHT_LEFT_THEN_TOP:
        for i in range(num_pages):
            row_from_top = i // cols
            row = (rows - 1) - row_from_top
            col = (cols - 1) - (i % cols)
            x = col * cell_width
            y = row * cell_height
            positions.append((x, y))
            
    else:
        for i in range(num_pages):
            row = i // cols
            col = i % cols
            x = col * cell_width
            y = row * cell_height
            positions.append((x, y))
    
    return positions

def _adjust_layout_for_rotation(layout_order: LayoutDirection) -> LayoutDirection:
    """调整布局顺序以适应旋转后的行列交换"""
    if layout_order == LayoutDirection.LEFT_RIGHT_THEN_DOWN:
        return LayoutDirection.BOTTOM_TOP_THEN_RIGHT
    elif layout_order == LayoutDirection.RIGHT_LEFT_THEN_DOWN:
        return LayoutDirection.TOP_BOTTOM_THEN_RIGHT
    elif layout_order == LayoutDirection.TOP_BOTTOM_THEN_RIGHT:
        return LayoutDirection.LEFT_RIGHT_THEN_TOP
    elif layout_order == LayoutDirection.TOP_BOTTOM_THEN_LEFT:
        return LayoutDirection.LEFT_RIGHT_THEN_DOWN
    else:
        return layout_order

def create_booklet_pdf(input_pdf: str, paper_size: tuple, 
                      direction: BookletDirection = BookletDirection.LEFT_TO_RIGHT) -> str:
    """
    创建小册子格式的PDF
    
    Args:
        input_pdf: 输入PDF文件路径
        paper_size: 纸张尺寸 (width_mm, height_mm)
        direction: 布局方向
    
    Returns:
        处理后的PDF临时文件路径
    """
    # 转换纸张尺寸到点单位
    factor = 72 / 25.4
    paper_width_pt = paper_size[0] * factor
    paper_height_pt = paper_size[1] * factor
    
    # 打开输入PDF
    src_doc = fitz.open(input_pdf)
    total_pages = len(src_doc)
    
    # 确保页数为4的倍数（小册子要求）
    pages_needed = ((total_pages + 3) // 4) * 4
    blank_pages = pages_needed - total_pages
    
    # 创建输出文档
    dst_doc = fitz.open()
    
    # 计算每张纸上的四个位置
    half_width = paper_width_pt / 2
    page_height = paper_height_pt
    
    # 处理每组4页（形成一个小册子折叠单元）
    for i in range(0, pages_needed, 4):
        # 确定4个页面的页码（根据小册子折叠逻辑）
        if direction == BookletDirection.LEFT_TO_RIGHT:
            # 左到右的小册子布局
            page1 = pages_needed - i - 1  # 最后一页
            page2 = i                     # 第一页
            page3 = i + 1                 # 第二页
            page4 = pages_needed - i - 2  # 倒数第二页
        else:  # right_to_left
            # 右到左的小册子布局（镜像）
            page1 = i                     # 第一页
            page2 = pages_needed - i - 1  # 最后一页
            page3 = pages_needed - i - 2  # 倒数第二页
            page4 = i + 1                 # 第二页
        
        # 创建新的A4页面（横向）
        new_page = dst_doc.new_page(width=paper_width_pt, height=paper_height_pt)
        
        # 定义四个区域
        left_rect = fitz.Rect(0, 0, half_width, page_height)
        right_rect = fitz.Rect(half_width, 0, paper_width_pt, page_height)
        
        # 绘制页面1（左半部分）
        if page1 < total_pages:
            new_page.show_pdf_page(left_rect, src_doc, page1)
        elif blank_pages > 0:
            # 空白页，什么都不画
            pass
            
        # 绘制页面2（右半部分）
        if page2 < total_pages:
            new_page.show_pdf_page(right_rect, src_doc, page2)
            
        # 创建背面页面
        back_page = dst_doc.new_page(width=paper_width_pt, height=paper_height_pt)
        
        # 绘制页面3（左半部分）
        if page3 < total_pages:
            back_page.show_pdf_page(left_rect, src_doc, page3)
            
        # 绘制页面4（右半部分）
        if page4 < total_pages:
            back_page.show_pdf_page(right_rect, src_doc, page4)
    
    src_doc.close()
    
    # 保存结果
    output_pdf = tempfile.mktemp(suffix=".pdf")
    dst_doc.save(output_pdf, garbage=4, deflate=True)
    dst_doc.close()
    
    return output_pdf