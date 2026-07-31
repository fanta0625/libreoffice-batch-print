# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

# ppt_layout_engine.py
import os
import tempfile
import fitz
from typing import Dict, Any, Optional, List, Tuple
from models.file_model import (
    PresentationContentType, PaperOrientations, ScalingMode,
    LayoutDirection
)
from config.settings import UNO_CONST
from utils.paper_utils import PaperSizeHelper, DocumentHelper
from log.logger import get_logger
from PySide6.QtCore import QMutex
import uno
from com.sun.star.beans import PropertyValue

logger = get_logger("PPTLayoutEngine")


class PPTLayoutEngine:
    """
    PPT 布局引擎：统一处理幻灯片、讲义、备注、大纲的 PDF 生成。
    预览和打印均调用此引擎获得布局后的 PDF 文件。
    """

    # -------------------- 静态布局映射 --------------------
    LAYOUT_MAP_PORTRAIT = {
        1: (1, 1),
        2: (2, 1),
        3: (3, 2), 
        4: (2, 2),
        6: (3, 2),
        9: (3, 3)
    }
    LAYOUT_MAP_LANDSCAPE = {
        1: (1, 1),
        2: (1, 2),
        3: (2, 3), 
        4: (2, 2),
        6: (2, 3),
        9: (3, 3)
    }

    def __init__(self, lo_service):
        """
        Args:
            lo_service: UnoConnectorService 实例，提供 UNO 文档操作能力。
        """
        self.lo_service = lo_service
        self._lock = QMutex()

    # ===================== 公共接口 =====================
    def generate_layout_pdf(self, file_path: str, params: Dict[str, Any]) -> str:
        """
        根据参数生成布局后的 PDF 临时文件路径。

        Args:
            file_path: 原始 PPT 文件路径
            params: 布局参数
        Returns:
            临时 PDF 文件路径
        """
        self._lock.lock()
        ppt_options = params["doc_options"]
        try:
            content_type = ppt_options.content_type
            paper_size = params.get("paper_size", "A4")
            orientation = params.get("orientation", PaperOrientations.AUTO)

            # 解析纸张尺寸
            if isinstance(paper_size, str):
                paper_info = PaperSizeHelper.get_raw_data_by_display_name(paper_size)
                paper_w_mm = float(paper_info["width"])
                paper_h_mm = float(paper_info["height"])
            else:
                paper_w_mm, paper_h_mm = paper_size

            is_landscape = (orientation == PaperOrientations.LANDSCAPE)
            # 若 AUTO，则采用纵向
            if orientation == PaperOrientations.AUTO:
                is_landscape = False

            # 分发
            if content_type == PresentationContentType.SLIDES:
                return self._generate_slides_pdf(
                    file_path, paper_w_mm, paper_h_mm,
                    is_landscape,
                    params.get("scaling_mode", ScalingMode.FIT_TO_PRINTABLE),
                    ppt_options.draw_slide_border
                )
            elif content_type == PresentationContentType.HANDOUTS:
                return self._generate_handouts_pdf(
                    file_path, paper_w_mm, paper_h_mm,
                    is_landscape,
                    ppt_options.handout_slides_per_page,
                    ppt_options.handout_layout_order,
                    ppt_options.draw_slide_border
                )
            elif content_type == PresentationContentType.NOTES:
                return self._generate_notes_pdf(
                    file_path, paper_w_mm, paper_h_mm,
                    is_landscape,
                    ppt_options.draw_slide_border
                )
            elif content_type == PresentationContentType.OUTLINE:
                return self._generate_outline_pdf(
                    file_path, paper_w_mm, paper_h_mm,
                    is_landscape
                )
            else:
                raise ValueError(f"Unsupported content_type: {content_type}")
        finally:
            self._lock.unlock()

    # ===================== 幻灯片模式 =====================
    def _generate_slides_pdf(self, file_path, paper_w_mm, paper_h_mm,
                             is_landscape, scaling_mode, draw_border) -> str:
        """幻灯片模式：居中/缩放/旋转每一页"""
        raw_pdf = self._export_ppt_to_pdf(file_path)
        rotate_angle = 90 if is_landscape else 0
        scale_to_fit = (scaling_mode == ScalingMode.FIT_TO_PRINTABLE)

        processed_pdf = self.lo_service.transform_pdf(
            input_pdf=raw_pdf,
            target_width_mm=paper_w_mm,
            target_height_mm=paper_h_mm,
            rotate_angle=rotate_angle,
            scale_to_fit=scale_to_fit,
            keep_aspect_ratio=True,
            show_border=draw_border
        )
        self._cleanup_temp(raw_pdf)
        return processed_pdf

    # ===================== 讲义模式=====================
    def _generate_handouts_pdf(self, file_path, paper_w_mm, paper_h_mm,
                               is_landscape, slides_per_page, layout_order,
                               draw_border) -> str:
        """讲义模式：调用内部讲义合成方法"""
        raw_pdf = self._export_ppt_to_pdf(file_path)
        handout_pdf = self._create_handout_pdf(
            input_pdf_path=raw_pdf,
            slides_per_page=slides_per_page,
            paper_size_mm=(paper_w_mm, paper_h_mm),
            is_landscape=is_landscape,
            draw_border=draw_border,
            draw_direction=layout_order
        )
        self._cleanup_temp(raw_pdf)
        return handout_pdf

    def _create_handout_pdf(self, input_pdf_path, slides_per_page,
                            paper_size_mm, is_landscape,
                            draw_border, draw_direction) -> str:
        """
        内部讲义合成方法
        """
        if slides_per_page.page_count not in self.LAYOUT_MAP_PORTRAIT:
            raise ValueError(f"不支持的排版数量: {slides_per_page}")

        # 确定行列
        if is_landscape:
            rows, cols = self.LAYOUT_MAP_LANDSCAPE[slides_per_page.page_count]
            paper_w_mm, paper_h_mm = max(paper_size_mm), min(paper_size_mm)
        else:
            rows, cols = self.LAYOUT_MAP_PORTRAIT[slides_per_page.page_count]
            paper_w_mm, paper_h_mm = min(paper_size_mm), max(paper_size_mm)

        # 单位转换
        paper_w_pt = paper_w_mm * UNO_CONST["MM_TO_PT"]
        paper_h_pt = paper_h_mm * UNO_CONST["MM_TO_PT"]

        margin_h_pt = 10.0 * UNO_CONST["MM_TO_PT"]
        gap_h_pt = 10.0 * UNO_CONST["MM_TO_PT"]
        margin_v_pt = 20 * UNO_CONST["MM_TO_PT"]

        available_width = paper_w_pt - 2 * margin_h_pt - (cols - 1) * gap_h_pt
        cell_width = available_width / cols
        available_height = paper_h_pt - 2 * margin_v_pt
        cell_height = available_height / rows

        slide_width = cell_width
        slide_height = slide_width * (9 / 16)

        src_doc = fitz.open(input_pdf_path)
        dst_doc = fitz.open()
        slide_index = 0
        total_slides = len(src_doc)

        # 生成网格坐标顺序
        grid_coords = [(r, c) for r in range(rows) for c in range(cols)]
        if draw_direction == LayoutDirection.TOP_BOTTOM_THEN_RIGHT:
            grid_coords.sort(key=lambda x: (x[1], x[0]))

        while slide_index < total_slides:
            new_page = dst_doc.new_page(width=paper_w_pt, height=paper_h_pt)
            for r, c in grid_coords:
                grid_x = margin_h_pt + c * (cell_width + gap_h_pt)
                grid_y = margin_v_pt + r * cell_height
                offset_y = (cell_height - slide_height) / 2
                content_rect = fitz.Rect(
                    grid_x, grid_y + offset_y,
                    grid_x + slide_width, grid_y + offset_y + slide_height
                )

                # 判断笔记区（仅针对 3 张/页）
                is_notes_area = False
                if slides_per_page.page_count == 3:
                    if is_landscape and r == 1:
                        is_notes_area = True
                    elif not is_landscape and c == 1:
                        is_notes_area = True

                if is_notes_area:
                    self._draw_notes_placeholder(new_page, content_rect)
                else:
                    if slide_index >= total_slides:
                        break
                    src_page = src_doc[slide_index]
                    new_page.show_pdf_page(content_rect, src_doc, slide_index,
                                           keep_proportion=False)
                    if draw_border:
                        inner_rect = content_rect + (-1, -1, 1, 1)
                        new_page.draw_rect(inner_rect, color=(0, 0, 0), width=1)
                    slide_index += 1

        out_path = tempfile.mktemp(suffix="_handout.pdf")
        dst_doc.save(out_path, garbage=4, deflate=True)
        src_doc.close()
        dst_doc.close()
        return out_path

    @staticmethod
    def _draw_notes_placeholder(page, rect):
        """绘制笔记占位横线"""
        x, y, x1, y1 = rect.x0, rect.y0, rect.x1, rect.y1
        w, h = rect.width, rect.height
        page.draw_line(fitz.Point(x, y1), fitz.Point(x1, y1),
                       color=(0, 0, 0), width=0.5)
        line_spacing = h / 7
        for i in range(7):
            current_y = y1 - (i * line_spacing)
            if i == 7:continue
            page.draw_line(fitz.Point(x, current_y),fitz.Point(x + w, current_y),color=(0, 0, 0), width=0.5)

    # ===================== 备注模式 =====================
    def _generate_notes_pdf(self, file_path, paper_w_mm, paper_h_mm,
                            is_landscape, draw_border) -> str:
        """备注模式：生成含幻灯片和备注的 PDF"""
        # 打开文档提取备注 HTML
        doc, temp_path = self.lo_service._load_document_safely(
            file_path, tuple(self.lo_service.get_hidden_property())
        )
        if not doc:
            raise RuntimeError("无法打开 PPT 文档")

        try:
            notes_list = self._extract_notes_html(doc)
            raw_pdf = self.lo_service.export_doc_to_pdf(doc)
        finally:
            doc.close(True)
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)

        # 合成备注 PDF
        notes_pdf = self._build_notes_pdf_from_raw(
            raw_pdf, notes_list, paper_w_mm, paper_h_mm,
            is_landscape, draw_border
        )
        self._cleanup_temp(raw_pdf)
        return notes_pdf

    def _extract_notes_html(self, doc):
        """提取所有备注页的 HTML"""
        notes_list = []
        draw_pages = doc.getDrawPages()
        for i in range(draw_pages.getCount()):
            slide = draw_pages.getByIndex(i)
            notes_page = slide.getNotesPage()
            slide_notes_html = ""
            if notes_page:
                for j in range(notes_page.getCount()):
                    shape = notes_page.getByIndex(j)
                    if shape.supportsService("com.sun.star.drawing.TextShape"):
                        text = shape.getText()
                        if hasattr(text, "createEnumeration"):
                            para_enum = text.createEnumeration()
                            while para_enum.hasMoreElements():
                                para = para_enum.nextElement()
                                if para.supportsService("com.sun.star.text.Paragraph"):
                                    para_text = para.getString()
                                    
                                    # 保留空行，避免段落挤在一起 
                                    if not para_text.strip():
                                        slide_notes_html += "<br/>"
                                        continue 
 
                                    style_attrs = []
                                    # 字体大小 
                                    font_height = para.getPropertyValue("CharHeight")
                                    style_attrs.append(f"font-size: {font_height:.1f}pt;")
                                    # 加粗 
                                    if para.getPropertyValue("CharWeight") > 100:
                                        style_attrs.append("font-weight: bold;")
                                    # 斜体 
                                    if para.getPropertyValue("CharPosture") == 2:
                                        style_attrs.append("font-style: italic;")
                                    # 颜色 
                                    color_val = para.getPropertyValue("CharColor")
                                    style_attrs.append(f"color: #{color_val:06X};")
 
                                    style_str = " ".join(style_attrs)
                                    safe_text = para_text.replace("&", "&amp;") \
                                        .replace("<", "&lt;") \
                                        .replace(">", "&gt;") \
                                        .replace('"', "&quot;")
                                    safe_text = safe_text.replace("\r\n", "<br/>") \
                                        .replace("\n", "<br/>") \
                                        .replace("\r", "<br/>")
                                    slide_notes_html += f'<p style="{style_str}">{safe_text}</p>'
            notes_list.append({
                'slide_number': i + 1,
                'notes_html': slide_notes_html 
            })
        return notes_list 
 
    def _build_notes_pdf_from_raw(self, slides_pdf_path, notes_list,
                                  paper_w_mm, paper_h_mm,
                                  is_landscape, draw_border) -> str:
        """使用 slides PDF 和备注列表合成备注 PDF"""
        factor = UNO_CONST["MM_TO_PT"]
        if is_landscape:
            page_w_pt = max(paper_w_mm, paper_h_mm) * factor
            page_h_pt = min(paper_w_mm, paper_h_mm) * factor
            border_mx, border_my = 6, 4
        else:
            page_w_pt = min(paper_w_mm, paper_h_mm) * factor
            page_h_pt = max(paper_w_mm, paper_h_mm) * factor
            border_mx, border_my = 4, 6

        slides_doc = fitz.open(slides_pdf_path)
        notes_doc = fitz.open()

        font_file = DocumentHelper.get_project_font_path()
        font_dir = os.path.dirname(font_file) if font_file else ""
        font_filename = os.path.basename(font_file) if font_file else ""

        for i in range(len(slides_doc)):
            slide_page = slides_doc[i]
            slide_rect = slide_page.rect
            new_page = notes_doc.new_page(width=page_w_pt, height=page_h_pt)

            if draw_border:
                border_rect = fitz.Rect(border_mx, border_my,page_w_pt - border_mx,page_h_pt - border_my)
                new_page.draw_rect(border_rect, color=(0, 0, 0), width=0.5)

            margin_x, margin_y, gap = 40, 72, 20
            max_slide_h_ratio = 0.55
            avail_w = page_w_pt - margin_x
            max_slide_h = (page_h_pt - 2 * margin_y - gap) * max_slide_h_ratio
            scale = min(avail_w / slide_rect.width,
                        max_slide_h / slide_rect.height)
            scaled_w = slide_rect.width * scale
            scaled_h = slide_rect.height * scale
            slide_x = (page_w_pt - scaled_w) / 2
            slide_y = margin_y

            new_page.show_pdf_page(
                fitz.Rect(slide_x, slide_y, slide_x + scaled_w, slide_y + scaled_h),
                slides_doc, i, clip=slide_rect, rotate=0
            )

            if i < len(notes_list) and notes_list[i].get('notes_html'):
                notes_top = slide_y + scaled_h + gap
                notes_bottom = page_h_pt - margin_y
                if notes_bottom > notes_top:
                    text_rect = fitz.Rect(60, notes_top, page_w_pt - 60, notes_bottom)
                    css = f"""
                        @font-face {{ font-family: 'ChineseFont'; src: url('{font_filename}'); }}
                        body {{ font-family: 'ChineseFont', sans-serif; font-size: 12pt; }}
                    """
                    full_html = f"""<!DOCTYPE html>
                        <html><head><meta charset="UTF-8"><style>{css}</style></head>
                        <body>{notes_list[i]['notes_html']}</body></html>"""
                    new_page.insert_htmlbox(text_rect, full_html, archive=font_dir)

        fd, out_pdf = tempfile.mkstemp(suffix="_notes.pdf")
        os.close(fd)
        notes_doc.save(out_pdf, garbage=4, deflate=True)
        notes_doc.close()
        slides_doc.close()
        return out_pdf

    # ===================== 大纲模式 =====================
    def _generate_outline_pdf(self, file_path, paper_w_mm, paper_h_mm,
                              is_landscape) -> str:
        """大纲模式：生成纯文本大纲 PDF"""
        outline_text = self._get_outline_text(file_path)
        return self._create_outline_pdf_from_text(
            outline_text, paper_w_mm, paper_h_mm, is_landscape
        )

    def _get_outline_text(self, file_path) -> str:
        """提取大纲"""
        doc, temp_path = self.lo_service._load_document_safely(
            file_path, tuple(self.lo_service.get_hidden_property())
        )
        if not doc:
            raise RuntimeError("无法打开 PPT 文档")

        try:
            outline_text = self._extract_outline_using_outliner(doc)
            return outline_text
        finally:
            doc.close(True)
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)

    def _extract_outline_using_outliner(self, doc) -> str:
        """使用 OutlinerShape 提取大纲"""
        outline_text = ""
        try:
            draw_pages = doc.getDrawPages()
            for i in range(draw_pages.getCount()):
                slide = draw_pages.getByIndex(i)
                title = self._extract_slide_title(slide)
                outline_text += f"{i+1}: {title}\n"
        except Exception as e:
            logger.error(f"提取大纲出错: {e}")
        return outline_text

    def _extract_slide_title(self, slide) -> str:
        """从单张幻灯片提取标题"""
        try:
            for j in range(slide.getCount()):
                shape = slide.getByIndex(j)
                if hasattr(shape, 'supportsService') and \
                   shape.supportsService("com.sun.star.presentation.TitleTextShape"):
                    text = shape.getText()
                    cursor = text.createTextCursor()
                    return cursor.getString().strip()
        except Exception as e:
            logger.error(f"提取单张标题出错: {e}")
        return ""

    def _create_outline_pdf_from_text(self, outline_text,
                                      paper_w_mm, paper_h_mm,
                                      is_landscape) -> str:
        """根据纯文本生成大纲 PDF"""
        factor = UNO_CONST["MM_TO_PT"]
        if is_landscape:
            w_pt, h_pt = max(paper_w_mm, paper_h_mm) * factor, min(paper_w_mm, paper_h_mm) * factor
        else:
            w_pt, h_pt = min(paper_w_mm, paper_h_mm) * factor, max(paper_w_mm, paper_h_mm) * factor

        font_file = DocumentHelper.get_project_font_path()
        font_name = "NotoSansCJK" if font_file else "Helvetica"

        doc = fitz.open()
        page = doc.new_page(width=w_pt, height=h_pt)
        y_pos = 72
        line_height = 25
        lines = outline_text.strip().split('\n')

        for line in lines:
            line = line.strip()
            if not line:
                continue
            if y_pos > h_pt - 94:
                page = doc.new_page(width=w_pt, height=h_pt)
                y_pos = 72
            if ':' in line:
                parts = line.split(':', 1)
                page_num = parts[0].strip()
                title = parts[1].strip()
                text = f"{page_num}- {title}"
                fontsize = 12
            else:
                text = line
                fontsize = 11
            page.insert_text((72, y_pos), text,
                             fontname=font_name, fontfile=font_file,
                             fontsize=fontsize)
            y_pos += line_height

        out_pdf = tempfile.mktemp(suffix="_outline.pdf")
        doc.save(out_pdf, garbage=4, deflate=True)
        doc.close()
        return out_pdf

    # ===================== 辅助方法 =====================
    def _export_ppt_to_pdf(self, file_path) -> str:
        """将 PPT 导出为 PDF，利用缓存"""
        cached_pdf = None
        with self.lo_service._cache_lock:
            if file_path in self.lo_service._pdf_cache:
                cached_pdf = self.lo_service._pdf_cache[file_path]
                if os.path.exists(cached_pdf):
                    return cached_pdf
                else:
                    del self.lo_service._pdf_cache[file_path]

        doc, temp_path = self.lo_service._load_document_safely(
            file_path, tuple(self.lo_service.get_hidden_property())
        )
        if not doc:
            raise RuntimeError("无法打开文档以导出 PDF")
        try:
            pdf_path = self.lo_service.export_doc_to_pdf(doc)
            with self.lo_service._cache_lock:
                self.lo_service._pdf_cache[file_path] = pdf_path
            return pdf_path
        finally:
            doc.close(True)
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)

    @staticmethod
    def _cleanup_temp(path):
        """安全删除临时文件"""
        if path and os.path.exists(path):
            try:
                os.unlink(path)
            except:
                pass