# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

# DocumentPreviewer.py
import os
import tempfile
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

import fitz  # PyMuPDF
from PySide6.QtCore import (
    QObject, Signal, QThread, Qt, QSize, QRectF, QRect, QLineF
)
from PySide6.QtGui import QPixmap, QImage, QPainter,QPen,QColor
from PySide6.QtWidgets import (
    QApplication, QLabel, QScrollArea, QWidget, QVBoxLayout,
    QHBoxLayout, QPushButton, QProgressBar, QComboBox, QSpinBox, QFrame
)
from services.uno_connect_service import lo_service
from config.settings import UNO_CONST,SUPPORTED_EXTENSIONS
from utils.paper_utils import PaperSizeHelper,DocumentHelper
from services.create_nup_pdf import _calculate_positions as _calculate_nup_positions,_adjust_layout_for_rotation
from services.excel_layout_engine import ExcelLayoutEngine
from services.ppt_layout_engine import PPTLayoutEngine
from models.file_model import ScalingMode,PaperOrientations,LayoutMode,LayoutDirection,BookletDirection,PresentationContentType

from log.logger import get_logger
logger = get_logger("DocumentPreviewer")
from utils.i18n import _

# ====== 纸张定义 ======
A4_MM = (210, 297)

# 预览基准：A4 竖向宽度 = 297 像素
REF_A4_WIDTH_PX = 300 # 可调整整体预览大小

SCALE_FACTOR = REF_A4_WIDTH_PX / 210.0 # px per mm


def get_standard_preview_size(paper_name: str, is_landscape: bool = False) -> QSize:
    """根据纸张类型和方向，返回其在预览中的标准像素尺寸"""
    paper_item = PaperSizeHelper.get_raw_data_by_display_name(paper_name)
    w_mm,h_mm = paper_item['width'],paper_item['height']
    if is_landscape:
        w_mm, h_mm = h_mm, w_mm

    width_px = int(w_mm * SCALE_FACTOR)
    height_px = int(h_mm * SCALE_FACTOR)
    return QSize(width_px, height_px)


class PaperViewport(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._ = _
        self._pixmap: Optional[QPixmap] = None
        self._paper_size = PaperSizeHelper.get_display_name("A4")
        self._orientation = PaperOrientations.PORTRAIT
        self._update_size()
        self.setStyleSheet("background-color: white;")

    def set_paper(self, paper_size: str, orientation: str):
        self._paper_size = paper_size
        self._orientation = orientation
        self._update_size()
        self.update()

    def set_page_pixmap(self, pixmap: QPixmap):
        self._pixmap = pixmap
        self.update()

    def _update_size(self):
        # 容器大小始终等于“目标纸张”的预览大小
        paper_item = PaperSizeHelper.get_raw_data_by_display_name(self._paper_size)
        w_mm, h_mm = paper_item['width'], paper_item['height']
        if self._orientation == PaperOrientations.LANDSCAPE:
            w_mm, h_mm = h_mm, w_mm
        
        width_px = int(w_mm * SCALE_FACTOR)
        height_px = int(h_mm * SCALE_FACTOR)
        
        # 限制最大预览尺寸
        max_w, max_h = 600, 800
        if width_px > max_w or height_px > max_h:
            ratio = min(max_w / width_px, max_h / height_px)
            width_px = int(width_px * ratio)
            height_px = int(height_px * ratio)
            
        self.setFixedSize(width_px, height_px)

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._pixmap:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.Antialiasing)

        view_w = self.width()
        view_h = self.height()
        pix_w = self._pixmap.width()
        pix_h = self._pixmap.height()
        
        x = (view_w - pix_w) // 2
        y = (view_h - pix_h) // 2
        
        # 绘制
        painter.drawPixmap(x, y, pix_w, pix_h, self._pixmap)
        painter.end()

# ====== 后台渲染线程 ======
class PreviewWorker(QThread):
    progress = Signal(int, str)
    finished = Signal(list, str)  # list of (pixmap, native_paper)
    error = Signal(str)

    def __init__(self, file_path: str, preview_params: Dict[str, Any]):
        super().__init__()
        self._ = _
        self.file_path = file_path
        self.params = preview_params.copy()
        self._stop_requested = False

    def run(self):
        # 临时文件句柄
        temp_pdf_path = None
        pdf_to_render = None
        try:
            if self._stop_requested:
                return
            logger.debug(f"开始渲染预览: {os.path.basename(self.file_path)}")
            self.progress.emit(10, "准备中...")
            ext = Path(self.file_path).suffix.lower()

            if ext == ".pdf":
                pdf_to_render = self.file_path
            elif ext in SUPPORTED_EXTENSIONS["PPT"]:
                engine = PPTLayoutEngine(lo_service)
                try:
                    temp_pdf_path = engine.generate_layout_pdf(self.file_path, self.params)
                    pdf_to_render = temp_pdf_path
                except Exception as e:
                    logger.error(f"PPT 布局引擎失败: {e}", exc_info=True)
                    self.error.emit(str(e))
            elif ext in SUPPORTED_EXTENSIONS["Excel"]:
                calc_engine = ExcelLayoutEngine(lo_service)
                temp_pdf_path = calc_engine.export_to_pdf(self.file_path,self.params["doc_options"])
                pdf_to_render = temp_pdf_path
            else:
                logger.debug(f"非 PDF 文件，需要转换: {ext}")
                self.progress.emit(40, "转换为 PDF...")
                if self._stop_requested:
                    return
                temp_pdf_path = lo_service.get_cached_pdf_by_path(self.file_path)
                pdf_to_render = temp_pdf_path
            
            if self._stop_requested:
                return
            self.progress.emit(60, "渲染预览图...")
            results = self._render_pdf_pages(pdf_to_render, self.params)

            self.progress.emit(100, "完成")
            logger.info(f"预览渲染完成: {len(results)} 页")
            self.finished.emit(results, self.file_path)

        except Exception as e:
            logger.error(f"预览渲染异常: {e}", exc_info=True)
            if not self._stop_requested:
                err_msg = f"预览失败: {str(e)}"
                self.error.emit(err_msg)
        finally:
            if temp_pdf_path and os.path.exists(temp_pdf_path):
                try:
                    os.unlink(temp_pdf_path)
                    logger.debug(f"已清理临时转换文件: {temp_pdf_path}")
                except:
                    pass 

    def _add_line_segment(self, line_dict, pos, start, end, tolerance):
        """
        处理线段合并。
        主要修复了当页面间距极小（如1px）时，线段未被正确连接的问题。
        """
        if start > end: start, end = end, start
        
        # 寻找是否有“邻居”线段
        best_match_key = None
        best_merge_type = None 
        
        for key in line_dict:
            k_pos, k_start, k_end = key
            
            # 必须在同一坐标轴上 (允许微小误差)
            if abs(k_pos - pos) > tolerance:
                continue
            
            # --- 检查重叠或间隙 ---
            # A: 完全包含 (新线在旧线内部) -> 忽略新线
            if start >= k_start and end <= k_end:
                return 
            
            # B: 旧线完全包含在新线内部 -> 替换旧线
            if start <= k_start and end >= k_end:
                best_match_key = key
                best_merge_type = 'cover'
                break 
            
            # C: 尾部接头 (旧线的尾 == 新线的头) 或有微小间隙
            if abs(k_end - start) <= tolerance * 2: # 放宽间隙判定
                best_match_key = key
                best_merge_type = 'connect_tail_head'
                break
            
            # D: 头部接头 (旧线的头 == 新线的尾) 或有微小间隙
            if abs(end - k_start) <= tolerance * 2:
                best_match_key = key
                best_merge_type = 'connect_head_tail'
                break
            
            # E: 部分重叠 (新线比旧线长，向左延伸)
            if start < k_start and abs(end - k_end) <= tolerance:
                 best_match_key = key
                 best_merge_type = 'extend_left'
                 break
                 
            # F: 部分重叠 (新线比旧线长，向右延伸)
            if end > k_end and abs(start - k_start) <= tolerance:
                 best_match_key = key
                 best_merge_type = 'extend_right'
                 break

        # 执行合并
        if best_match_key:
            k_pos, k_start, k_end = best_match_key
            new_start, new_end = start, end
            
            if best_merge_type == 'cover':
                new_start, new_end = start, end
            elif best_merge_type == 'connect_tail_head':
                # [k_start...k_end] + [start...end]  => [k_start...end]
                new_start = k_start
                new_end = end
            elif best_merge_type == 'connect_head_tail':
                # [start...end] + [k_start...k_end] => [start...k_end]
                new_start = start
                new_end = k_end
            elif best_merge_type == 'extend_left':
                new_start = start
                new_end = k_end
            elif best_merge_type == 'extend_right':
                new_start = k_start
                new_end = end
            
            # 更新字典
            line_dict[(pos, new_start, new_end)] = True
            del line_dict[best_match_key]
        else:
            # 没有匹配到任何邻居，作为新线段添加
            line_dict[(pos, start, end)] = True

    def _draw_notes_placeholder(self, painter, rect_f):
        painter.setPen(QPen(QColor(0,0,0),0.5))
        painter.drawLine(int(rect_f.left()), int(rect_f.bottom()), int(rect_f.right()), int(rect_f.bottom()))
        line_spacing = rect_f.height() / 7
        
        # 从底部开始向上画 7 条线
        for i in range(7):
            current_y = rect_f.bottom() - (i * line_spacing)
            if i == 7: continue
            painter.drawLine(int(rect_f.left()), int(current_y), int(rect_f.right()), int(current_y))

    def _render_pdf_pages(self, pdf_path: str, params: Dict[str, Any]) -> List[Tuple[QPixmap, str]]:
        logger.info(f"打开 PDF 进行渲染: {pdf_path}")
        
        # 获取参数
        target_paper_name = params.get("paper_size", PaperSizeHelper.get_display_name("A4"))
        target_orientation = params.get("orientation")
        page_range = params.get("page_range")
        scaling_mode = params.get("scaling_mode", ScalingMode.ACTUAL_SIZE)
        layout_mode = params.get("layout_mode", LayoutMode.PAGE_SCALE)
        nup_rows = max(1, params.get("nup_rows", 1))
        nup_cols = max(1, params.get("nup_cols", 1))
        nup_dir = params.get("nup_dir", LayoutDirection.LEFT_RIGHT_THEN_DOWN)
        nup_draw_border = params.get("nup_draw_border", False)

        processed_pdf = lo_service._create_pdf_subset(pdf_path,page_range)
        doc = fitz.open(processed_pdf)
        results = []

        # 目标容器尺寸
        target_qsize = get_standard_preview_size(
            target_paper_name,
            target_orientation == PaperOrientations.LANDSCAPE
        )
        container_w = target_qsize.width()
        container_h = target_qsize.height()

        render_dpi = 150
        mat = fitz.Matrix(render_dpi / 72.0, render_dpi / 72.0)

        total_pages = doc.page_count
        if total_pages == 0:
            doc.close()
            return []
        if layout_mode == LayoutMode.PAGE_SCALE:
            # === 单页模式 ===
            source_data = []
            for i in range(total_pages):
                if self._stop_requested:
                    break
                page = doc.load_page(i)
                rect = page.rect
                src_w_mm = rect.width * 25.4 / 72
                src_h_mm = rect.height * 25.4 / 72
                
                native_paper = "A4"
                if (abs(src_w_mm - 297) < 8 and abs(src_h_mm - 420) < 8):
                    native_paper = "A3"
                pix = page.get_pixmap(matrix=mat, alpha=False)
                img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
                high_res_pixmap = QPixmap.fromImage(img)
                source_data.append(high_res_pixmap)
                if scaling_mode == ScalingMode.FIT_TO_PRINTABLE:
                    src_w_px = src_w_mm * SCALE_FACTOR
                    src_h_px = src_h_mm * SCALE_FACTOR
                    scale_w = container_w / src_w_px
                    scale_h = container_h / src_h_px
                    scale = min(scale_w, scale_h)
                    final_w = int(src_w_px * scale)
                    final_h = int(src_h_px * scale)
                else:
                    final_w = int(src_w_mm * SCALE_FACTOR)
                    final_h = int(src_h_mm * SCALE_FACTOR)

                standard_pixmap = high_res_pixmap.scaled(
                    QSize(final_w, final_h), Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
                results.append((standard_pixmap, native_paper))  
        elif layout_mode == LayoutMode.N_UP:
            # === N-up 模式 ===
            pages_per_sheet = nup_rows * nup_cols
            layout_order = nup_dir
            original_rows, original_cols = nup_rows, nup_cols
            rotate_pages_for_auto = False

            if total_pages > 0:
                first_page = doc.load_page(0)
                page_width, page_height= first_page.rect.width,first_page.rect.height
                page_aspect_ratio = page_width / page_height if page_height > 0 else 1.0

                # 计算网格的总体宽高比
                grid_aspect_ratio = round((nup_cols * page_aspect_ratio) / nup_rows,3)

                # 目标纸张尺寸（mm）
                paper_item = PaperSizeHelper.get_raw_data_by_display_name(target_paper_name)
                # 计算纸张的宽高比
                paper_aspect_ratio = round(paper_item["width"] / paper_item["height"],3)

                # 如果网格太“宽”，而纸张较“高”，则转置网格
                if grid_aspect_ratio > paper_aspect_ratio and target_orientation==PaperOrientations.AUTO:
                    rotate_pages_for_auto = True
                    nup_rows, nup_cols = nup_cols, nup_rows
                    # 调整布局顺序
                    layout_order = _adjust_layout_for_rotation(nup_dir)

                logger.debug(f"N-up 自动旋转: {rotate_pages_for_auto}, "
                             f"原({original_rows}x{original_cols}) -> 新({nup_rows}x{nup_cols}), "
                             f"网格AR={grid_aspect_ratio:.2f}, 纸张AR={paper_aspect_ratio:.2f}")


            cell_width = container_w / nup_cols
            cell_height = container_h / nup_rows

            # 预先加载所有源页面数据
            source_data = []
            for i in range(total_pages):
                if self._stop_requested:
                    break
                page = doc.load_page(i)
                rect = page.rect
                src_w_mm = rect.width * 25.4 / 72
                src_h_mm = rect.height * 25.4 / 72
                pix = page.get_pixmap(matrix=mat, alpha=False)
                img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
                source_data.append((QPixmap.fromImage(img), src_w_mm, src_h_mm))

            if self._stop_requested:
                doc.close()
                return []

            # 分组合成
            for start in range(0, total_pages, pages_per_sheet):
                group = source_data[start:start + pages_per_sheet]
                num_in_group = len(group)
                composite = QPixmap(container_w, container_h)
                composite.fill(Qt.white)
                painter = QPainter(composite)
                try:
                    positions = _calculate_nup_positions(
                        num_in_group, nup_rows, nup_cols, layout_order, cell_width, cell_height
                    )

                    # 用于存储去重后的线段,格式: (坐标值, 起点, 终点) ,水平线: (y, x1, x2),垂直线: (x, y1, y2)
                    unique_h_lines = {} 
                    unique_v_lines = {}
                    
                    page_rects = [] # 存储 (x, y, w, h)
                    
                    # 计算位置并绘制图片
                    for idx, ((src_pixmap, src_w_mm, src_h_mm), (cell_x, cell_y)) in enumerate(zip(group, positions)):
                        # 计算显示尺寸
                        if rotate_pages_for_auto:
                            display_w = src_h_mm * SCALE_FACTOR
                            display_h = src_w_mm * SCALE_FACTOR
                        else:
                            display_w = src_w_mm * SCALE_FACTOR
                            display_h = src_h_mm * SCALE_FACTOR

                        scale_x = cell_width / display_w
                        scale_y = cell_height / display_h
                        scale = min(scale_x, scale_y)
                        scaled_w = int(display_w * scale)
                        scaled_h = int(display_h * scale)

                        draw_x = cell_x + (cell_width - scaled_w) // 2
                        draw_y = cell_y + (cell_height - scaled_h) // 2
                        
                        # 绘制 pixmap
                        if rotate_pages_for_auto:
                            transform = painter.transform()
                            painter.translate(draw_x + scaled_w // 2, draw_y + scaled_h // 2)
                            painter.rotate(-90)
                            rotated_pixmap = src_pixmap.scaled(int(scaled_h), int(scaled_w), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                            painter.drawPixmap(int(-scaled_h // 2), int(-scaled_w // 2), int(scaled_h), int(scaled_w), rotated_pixmap)
                            painter.setTransform(transform)
                        else:
                            scaled_pixmap = src_pixmap.scaled(int(scaled_w), int(scaled_h), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                            painter.drawPixmap(int(draw_x), int(draw_y), int(scaled_w), int(scaled_h), scaled_pixmap)
                            
                        page_rects.append((int(draw_x), int(draw_y), scaled_w, scaled_h))

                    # 收集所有边框线段
                    if nup_draw_border:
                        tolerance = 1.0 # 1px 容差
                        for rx, ry, rw, rh in page_rects:
                            # --- 处理水平边 (上边和下边) ---
                            self._add_line_segment(unique_h_lines, ry, rx, rx + rw, tolerance)
                            self._add_line_segment(unique_h_lines, ry + rh, rx, rx + rw, tolerance)
                            
                            # --- 处理垂直边 (左边和右边) ---
                            self._add_line_segment(unique_v_lines, rx, ry, ry + rh, tolerance)
                            self._add_line_segment(unique_v_lines, rx + rw, ry, ry + rh, tolerance)

                        # 绘制去重后的线段
                        pen = QPen(Qt.black)
                        pen.setWidthF(1.0)
                        pen.setCosmetic(True)
                        painter.setPen(pen)

                        # 定义有效绘制区域（留出 1px 安全边距，防止线宽被切掉）
                        max_x = container_w-1
                        max_y = container_h-1

                        # 绘制水平线
                        for y, x1, x2 in unique_h_lines.keys():
                            painter.drawLine(QLineF(min(x1,max_x), min(y + 0.5,max_y), min(x2,max_x), min(y + 0.5,max_y)))
                        
                        # 绘制垂直线
                        for x, y1, y2 in unique_v_lines.keys():
                            painter.drawLine(QLineF(min(x + 0.5,max_x), min(y1,max_y), min(x + 0.5,max_x), min(y2,max_y)))
                finally:
                    painter.end()
                results.append((composite, "N-UP"))
        elif layout_mode == LayoutMode.BOOKLET:
            results = self._render_booklet_layout(doc, target_qsize,params,mat)
        doc.close()
        if processed_pdf and os.path.exists(processed_pdf):
            try:
                os.unlink(processed_pdf)
                logger.debug(f"已清理渲染临时文件: {processed_pdf}")
            except Exception as e:
                logger.warning(f"清理渲染临时文件失败: {processed_pdf}, 错误: {e}")
        return results

    def _render_booklet_layout(self,doc, target_qsize, params, mat):
        """渲染小册子布局 - 简化版（小册子固定使用横向）"""
        container_w = target_qsize.width()
        container_h = target_qsize.height()
        total_pages = doc.page_count
        
        if total_pages == 0:
            return []
        
        # 获取关键参数
        booklet_direction = params.get("booklet_direction", BookletDirection.LEFT_TO_RIGHT)
        
        # 确保页数为4的倍数（小册子要求）
        pages_needed = ((total_pages + 3) // 4) * 4
        
        # 预先加载所有源页面数据（使用传入的mat矩阵）
        source_data = []
        for i in range(pages_needed):
            if i < total_pages:
                page = doc.load_page(i)
                rect = page.rect
                src_w_mm = rect.width * 25.4 / 72
                src_h_mm = rect.height * 25.4 / 72
                pix = page.get_pixmap(matrix=mat, alpha=False)
                img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
                source_data.append((QPixmap.fromImage(img), src_w_mm, src_h_mm))
            else:
                # 添加空白页 - 使用第一页尺寸作为参考
                if total_pages > 0:
                    ref_page = doc.load_page(0)
                    ref_rect = ref_page.rect
                    ref_w_mm = ref_rect.width * 25.4 / 72
                    ref_h_mm = ref_rect.height * 25.4 / 72
                else:
                    ref_w_mm, ref_h_mm = 210, 297  # A4默认尺寸（毫米）
                    
                blank_pixmap = QPixmap(int(ref_w_mm * SCALE_FACTOR), int(ref_h_mm * SCALE_FACTOR))
                blank_pixmap.fill(Qt.white)
                source_data.append((blank_pixmap, ref_w_mm, ref_h_mm))
        
        # 计算每页的左右区域（横向布局）
        half_width = container_w / 2
        
        results = []
        # 处理每组4页（形成一个小册子折叠单元）
        for i in range(0, pages_needed, 4):
            # 根据方向确定页面映射
            if booklet_direction == BookletDirection.LEFT_TO_RIGHT:
                front_left = pages_needed - i - 1   # 最后一页（正面左侧）
                front_right = i                     # 第一页（正面右侧）
                back_left = i + 1                   # 第二页（背面左侧）
                back_right = pages_needed - i - 2   # 倒数第二页（背面右侧）
            else:  # right_to_left
                front_left = i                      # 第一页（正面左侧）
                front_right = pages_needed - i - 1  # 最后一页（正面右侧）
                back_left = pages_needed - i - 2    # 倒数第二页（背面左侧）
                back_right = i + 1                  # 第二页（背面右侧）
            
            # === 创建正面页面 ===
            front_page = self._create_booklet_side(
                container_w, container_h, half_width,
                source_data, front_left, front_right
            )
            
            # === 创建背面页面 ===
            back_page = self._create_booklet_side(
                container_w, container_h, half_width,
                source_data, back_left, back_right
            )
            
            # 根据双面打印模式决定如何添加到结果
            sheet_num = i // 4 + 1
            if front_page and not front_page.isNull():
                results.append((front_page, f"BOOKLET_SHEET_{sheet_num}_FRONT"))
            if back_page and not back_page.isNull():
                results.append((back_page, f"BOOKLET_SHEET_{sheet_num}_BACK"))
        
        return results

    def _create_booklet_side(self,container_w, container_h, half_width, source_data, left_page_idx, right_page_idx):
        """创建小册子单面（正面或背面）"""
        side_page = QPixmap(int(container_w), int(container_h))
        side_page.fill(Qt.white)
        painter = QPainter(side_page)
        
        # 左侧内容
        if 0 <= left_page_idx < len(source_data):
            left_pixmap, left_w_mm, left_h_mm = source_data[left_page_idx]
            self._draw_booklet_content(painter, left_pixmap, left_w_mm, left_h_mm, 
                                    0, half_width, container_h)
        
        # 右侧内容
        if 0 <= right_page_idx < len(source_data):
            right_pixmap, right_w_mm, right_h_mm = source_data[right_page_idx]
            self._draw_booklet_content(painter, right_pixmap, right_w_mm, right_h_mm, 
                                    half_width, half_width, container_h)
        
        painter.end()
        return side_page

    def _draw_booklet_content(self,painter, pixmap, src_w_mm, src_h_mm, offset_x, available_width, container_height):
        """绘制小册子单个内容区域"""
        display_w = src_w_mm * SCALE_FACTOR
        display_h = src_h_mm * SCALE_FACTOR
        scale_x = available_width / display_w
        scale_y = container_height / display_h
        scale = min(scale_x, scale_y)
        scaled_w = int(display_w * scale)
        scaled_h = int(display_h * scale)
        draw_x = offset_x + (available_width - scaled_w) // 2
        draw_y = (container_height - scaled_h) // 2
        
        painter.drawPixmap(
            int(draw_x), int(draw_y), int(scaled_w), int(scaled_h),
            pixmap.scaled(int(scaled_w), int(scaled_h), 
                        Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )

# ====== 主预览控件 ======
class DocumentPreviewer(QWidget):
    preview_updated = Signal()
    current_page_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_file: Optional[str] = None
        self._pixmaps: List[QPixmap] = []
        self._current_index = -1
        self._worker: Optional[PreviewWorker] = None
        self._preview_params = {
            "dpi_scale": 1.5,
            "paper_size": PaperSizeHelper.get_display_name("A4"),
            "orientation": PaperOrientations.AUTO,
            "layout_mode": LayoutMode.PAGE_SCALE,
            "nup_rows": 1,
            "nup_cols": 1,
            "nup_dir": LayoutDirection.LEFT_RIGHT_THEN_DOWN,
            "nup_draw_border":False,
            "ppt_show_border":False
        }
        self._setup_ui()

    def _setup_ui(self):
        preview_frame = QFrame()
        preview_frame.setObjectName("preview_frame")
        frame_layout = QVBoxLayout(preview_frame)
        layout = QVBoxLayout(self)

        nav_layout = QHBoxLayout()
        self.btn_first = QPushButton(_("DocumentPreviewer", "btn_first"))
        self.btn_first.setObjectName("btnFirst")
        self.btn_prev = QPushButton(_("DocumentPreviewer", "btn_prev"))
        self.btn_prev.setObjectName("btnPrev")
        self.btn_next = QPushButton(_("DocumentPreviewer", "btn_next"))
        self.btn_next.setObjectName("btnNext")
        self.btn_last = QPushButton(_("DocumentPreviewer", "btn_last"))
        self.btn_last.setObjectName("btnLast")
        self.label_page_info = QLabel("0 / 0")
        self.label_page_info.setMinimumWidth(60)
        self.label_page_info.setAlignment(Qt.AlignmentFlag.AlignCenter)

        for btn in [self.btn_first, self.btn_prev, self.btn_next, self.btn_last]:
            btn.clicked.connect(self._on_nav_click)

        nav_layout.addStretch()
        nav_layout.addWidget(self.btn_first)
        nav_layout.addWidget(self.btn_prev)
        nav_layout.addWidget(self.label_page_info)
        nav_layout.addWidget(self.btn_next)
        nav_layout.addWidget(self.btn_last)
        nav_layout.addStretch()

        self.paper_viewport = PaperViewport()
        self.paper_viewport.setMinimumSize(200, 200)

        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumHeight(15)
        self.progress_bar.setObjectName("previewProgress")
        self.progress_bar.setVisible(False)

        frame_layout.addWidget(self.paper_viewport, 1, Qt.AlignmentFlag.AlignCenter)
        frame_layout.addWidget(self.progress_bar)
        layout.addWidget(preview_frame)
        layout.addLayout(nav_layout)
        self.setLayout(layout)
        self._update_nav_enabled()

    def _on_nav_click(self):
        sender = self.sender()
        total = len(self._pixmaps)
        if sender == self.btn_first:
            self.go_to_page(0)
        elif sender == self.btn_prev:
            self.go_to_page(max(0, self._current_index - 1))
        elif sender == self.btn_next:
            self.go_to_page(min(total - 1, self._current_index + 1))
        elif sender == self.btn_last:
            self.go_to_page(total - 1)

    def go_to_page(self, index: int):
        if not self._pixmaps or index < 0 or index >= len(self._pixmaps):
            return
        self._current_index = index
        self.paper_viewport.set_page_pixmap(self._pixmaps[index])
        self.label_page_info.setText(f"{index + 1} / {len(self._pixmaps)}")
        self._update_nav_enabled()
        self.current_page_changed.emit(index)

    def _update_nav_enabled(self):
        total = len(self._pixmaps)
        self.btn_first.setEnabled(self._current_index > 0)
        self.btn_prev.setEnabled(self._current_index > 0)
        self.btn_next.setEnabled(self._current_index < total - 1)
        self.btn_last.setEnabled(self._current_index < total - 1)

    # ==================== Public API ====================

    def load_document(self, file_path: str):
        if not os.path.exists(file_path):
            raise FileNotFoundError(_("DocumentPreviewer", "file_not_found", path=file_path))

        if self._worker and self._worker.isRunning():
            self._worker._stop_requested = True
            # 断开所有信号连接
            self._worker.progress.disconnect()
            self._worker.finished.disconnect()
            self._worker.error.disconnect() 
            if not self._worker.wait(10000):
                self._worker.terminate()
                self._worker.wait()
            # 请求线程在完成任务后自行销毁
            self._worker.deleteLater() 
            # 将本地引用置为 None，表示当前没有活跃的 worker
            self._worker = None

        self._current_file = file_path
        self._show_progress(True)
        self._worker = PreviewWorker(file_path, self._preview_params)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_preview_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def update_preview_params(self, new_params: Dict[str, Any]):
        self._preview_params.update(new_params)
        self.paper_viewport.set_paper(
            new_params.get("paper_size", PaperSizeHelper.get_display_name("A4")),
            new_params.get("orientation", PaperOrientations.AUTO)
        )
        self.load_document(new_params.get("file_path"))

    def get_current_page_index(self) -> int:
        return self._current_index

    def get_total_pages(self) -> int:
        return len(self._pixmaps)

    def get_current_preview_pixmap(self) -> Optional[QPixmap]:
        if 0 <= self._current_index < len(self._pixmaps):
            return self._pixmaps[self._current_index]
        return None

    def clear_preview(self):
        self._pixmaps = []
        self._current_index = -1
        self.paper_viewport.set_page_pixmap(None)
        self.label_page_info.setText("0 / 0")
        self._update_nav_enabled()

    # ==================== Internal Callbacks ====================

    def _on_progress(self, percent: int, message: str):
        self.progress_bar.setValue(percent)

    def _on_preview_finished(self, result_list: List[Tuple[QPixmap, str]], file_path: str):
        self._pixmaps = [pixmap for pixmap, _ in result_list]
        self._show_progress(False)
        if self._pixmaps:
            self.paper_viewport.set_paper(
                self._preview_params["paper_size"],
                self._preview_params["orientation"]
            )
            self.go_to_page(0)
        else:
            self.paper_viewport.set_page_pixmap(None)
            self.label_page_info.setText(_("DocumentPreviewer", "no_pages"))
        self.preview_updated.emit()

    def _on_error(self, msg: str):
        self._show_progress(False)
        self.paper_viewport.set_page_pixmap(None)
        self.label_page_info.setText(_("Common", "error"))

    def _show_progress(self, show: bool):
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(show)

    def apply_paper_settings_to_document(self, paper_size: str, orientation: str):
        pass