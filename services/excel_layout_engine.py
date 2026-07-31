# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import uno
import os
import tempfile
from com.sun.star.awt import Size as UnoSize
from com.sun.star.beans import PropertyValue as UnoProp
from models.file_model import ExcelPrintMode,ExcelScalingType
import logging

logger = logging.getLogger("ExcelExportService")

class ExcelLayoutEngine:
    def __init__(self, lo_service):
        """
        Args:
            lo_service: UnoConnectorService 实例，提供 UNO 文档操作能力。
        """
        self.lo_service = lo_service

    def configure_excel_print_settings(self,doc, options):
        """
        核心逻辑：根据 ExcelPrintOptions 配置 Calc 文档的打印设置。
        
        Args:
            doc: 已打开的 LibreOffice Calc 文档对象
            options: ExcelPrintOptions 配置对象
        
        Returns:
            bool: 成功返回 True，失败返回 False
        """
        target_sheet = None
        try:
            # 获取页面样式管理器
            style_families = doc.getStyleFamilies()
            page_styles = style_families.getByName("PageStyles")
            sheets = doc.getSheets()
            
            if options.print_mode == ExcelPrintMode.ACTIVE_SHEET:
                # 使用指定索引，默认为0
                if sheets.getCount() > options.sheet_index:
                    target_sheet = sheets.getByIndex(options.sheet_index)
                else:
                    logger.warning(f"指定的 sheet_index {options.sheet_index} 不存在，使用第一个 sheet")
                    target_sheet = sheets.getByIndex(0)
                # 遍历所有 Sheet，隐藏非目标且可见的
                for i in range(sheets.getCount()):
                    s = sheets.getByIndex(i)
                    if s.getName() != target_sheet.getName() and s.IsVisible:
                        s.IsVisible = False

                # 对目标 Sheet 进行设置
                if target_sheet:
                    self._apply_sheet_settings(target_sheet, page_styles, options)
                    
            elif options.print_mode == ExcelPrintMode.ENTIRE_WORKBOOK:
                # 对于整个工作簿，遍历所有可见工作表进行设置
                for i in range(sheets.getCount()):
                    sheet = sheets.getByIndex(i)
                    if sheet.IsVisible: # 仅处理可见工作表
                        self._apply_sheet_settings(sheet, page_styles, options)
                return True # 提前返回，因为已经处理了所有 Sheet
                
            return True

        except Exception as e:
            logger.error(f"配置 Excel 打印设置失败: {e}", exc_info=True)
            return False


    def _apply_sheet_settings(self,sheet, page_styles, options):
        """应用单个工作表的打印设置"""
        try:
            # 获取页面样式
            style_name = sheet.getPropertyValue("PageStyle")
            page_style = page_styles.getByName(style_name)
            

            # 方向设置
            page_style.setPropertyValue("IsLandscape", options.is_landscape)

            # 获取当前页面尺寸
            current_size = page_style.getPropertyValue("Size")
            
            # 根据方向手动交换宽高
            if options.is_landscape:
                if current_size.Width < current_size.Height:
                    new_size = UnoSize(current_size.Height, current_size.Width)
                    page_style.setPropertyValue("Size", new_size)
            else:
                if current_size.Width > current_size.Height:
                    new_size = UnoSize(current_size.Height, current_size.Width)
                    page_style.setPropertyValue("Size", new_size)
            
            # --- 缩放设置 (Scaling) ---
            scaling_type = options.scaling_type
            
            if scaling_type == ExcelScalingType.CUSTOM_SCALING:
                page_style.setPropertyValue("ScaleToPages", 0)      
                page_style.setPropertyValue("ScaleToPagesX", 0)    
                page_style.setPropertyValue("ScaleToPagesY", 0) 
                # 自定义百分比
                page_style.setPropertyValue("PageScale", int(options.custom_scale_percent))
                current_scale = page_style.getPropertyValue("PageScale")
                
            elif scaling_type == ExcelScalingType.FIT_ALL_COLUMNS_ON_ONE_PAGE:
                # 所有列打印在一页 (宽度缩放至1页，高度不限)
                page_style.setPropertyValue("ScaleToPagesX", 1)
                page_style.setPropertyValue("ScaleToPagesY", 0) 
                
            elif scaling_type == ExcelScalingType.FIT_ALL_ROWS_ON_ONE_PAGE:
                # 所有行打印在一页 (高度缩放至1页，宽度不限)
                page_style.setPropertyValue("ScaleToPagesX", 0)
                page_style.setPropertyValue("ScaleToPagesY", 1)
                
            elif scaling_type == ExcelScalingType.FIT_SHEET_ON_ONE_PAGE:
                # 整个工作表打印到指定页数
                page_style.setPropertyValue("ScaleToPages",1)
                
            else: 
                # 正常尺寸，不进行特殊缩放
                page_style.setPropertyValue("PageScale", 100)
                page_style.setPropertyValue("ScaleToPages", 0)
                page_style.setPropertyValue("ScaleToPagesX", 0)
                page_style.setPropertyValue("ScaleToPagesY", 0)
            
            logger.debug(f"已配置工作表 '{sheet.getName()}' 打印选项")

            # 重新绑定样式到工作表
            sheet.setPropertyValue("PageStyle", style_name)
        except Exception as e:
            logger.error(f"配置工作表设置失败: {e}", exc_info=True)
            raise

    def export_to_pdf(self,input_source,options):
        """
        将 Excel (Calc) 文档根据指定参数导出为 PDF。
        Args:
            input_source: 可以是已打开的 LibreOffice 文档对象 (XComponent) 或者是文件路径 (str)
            output_pdf_path: 输出 PDF 的路径 
            options: ExcelPrintOptions 配置对象
            
        Returns:
            tuple: (success: bool, message: str)
        """
        doc = input_source
        try:
            if isinstance(input_source, str):
                doc, temp_path = self.lo_service._load_document_safely(
                    input_source, tuple(self.lo_service.get_hidden_property()))
            # 验证文档类型
            if not doc.supportsService("com.sun.star.sheet.SpreadsheetDocument"):
                return False, "文档不是 Excel (Calc) 格式"
                
            # 应用打印配置
            if not self.configure_excel_print_settings(doc, options):
                return False, "配置打印参数失败"

            # UNO 导出属性
            # FilterName: calc_pdf_Export 是 Calc 的标准 PDF 导出过滤器
            tmp_file = tempfile.NamedTemporaryFile(suffix=".pdf",delete=False)
            tmp_path = tmp_file.name
            tmp_file.close()
            # 执行导出
            out_url = uno.systemPathToFileUrl(os.path.abspath(tmp_path))
            props = [UnoProp(Name="FilterName", Value="calc_pdf_Export")]
            
            doc.storeToURL(out_url, tuple(props))
            logger.info(f"Excel 文档成功导出为 PDF: {out_url}")
            return tmp_path
            
        except Exception as e:
            logger.error(f"导出 Excel 为 PDF 失败: {e}", exc_info=True)
            return None