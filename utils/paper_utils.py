# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import re
import os
import cups
import fitz
import magic
import zipfile
import xml.etree.ElementTree as ET
import subprocess
from config.settings import PAPER_SIZES,SUPPORTED_EXTENSIONS,ALLOWED_MIMES,FLAT_FILE_TYPES
from com.sun.star.awt import Size
from utils.i18n import _
class PaperSizeHelper:

    @staticmethod
    def get_display_list():
        """
        获取用于 UI 下拉框显示的列表
        格式："名称 宽mm x 高mm"
        返回: List[str]
        """
        display_list = []
        for item in PAPER_SIZES:
            name = item["name"]
            w = item["width"]
            h = item["height"]
            w_str = f"{w:.1f}".rstrip('0').rstrip('.')
            h_str = f"{h:.1f}".rstrip('0').rstrip('.')
            if w == 0 and h == 0:
                display_list.append(f"{name}")
            elif not name:
                display_list.append(f"{w_str}mm x {h_str}mm")
            else:
                display_list.append(f"{name} ({w_str}mm x {h_str}mm)")
        
        return display_list

    @staticmethod
    def get_raw_data_by_name(name):
        """
        根据名称（如 'A4'）直接获取原始数据字典
        """
        for item in PAPER_SIZES:
            if item.get("name") == name:
                return item
        return None

    @staticmethod
    def get_raw_data_by_display_name(display_name):
        for item in PAPER_SIZES:
            name = item["name"]
            # 构建正则模式：以name开头，后跟空格、左括号、任意字符、右括号，且字符串结束
            pattern = r"^{}\s*\(.*\)$".format(re.escape(name))
            if re.match(pattern, display_name):
                return item
        return None

    @staticmethod
    def get_uno_size_by_display_name(display_name):
        """
        直接获取 UNO 需要的 Size 对象
        """
        data = PaperSizeHelper.get_raw_data_by_display_name(display_name)
        if not data or data["width"] == 0:
            return None
            
        size = Size()
        # 转换为 1/100 mm
        size.Width = int(data["width"] * 100)
        size.Height = int(data["height"] * 100)
        return size

    @staticmethod
    def get_default_index():
        """获取 'A4' 在列表中的索引，用于默认选中"""
        default_index = 0 
        for i, item in enumerate(PAPER_SIZES):
            if 'A4' in item['name']:
                default_index = i
                break
        return default_index

    @staticmethod
    def get_file_page_size(file_path):
        src_doc_check = fitz.open(file_path)
        if len(src_doc_check) > 0:
            src_page = src_doc_check[0]
            # 源尺寸 (Points -> mm)
            src_w_mm = src_page.rect.width * 25.4 / 72
            src_h_mm = src_page.rect.height * 25.4 / 72
            return {'width':src_w_mm,'height':src_h_mm}
        return None

    @staticmethod
    def isFileFitPaper(file_path,paper_size):
        # 容差最大1mm
        tolerance = 1 
        page_size = PaperSizeHelper.get_file_page_size(file_path)
        w_diff = abs(paper_size['width'] - page_size['width'])
        h_diff = abs(paper_size['height'] - page_size['height'])
        if w_diff > tolerance or h_diff > tolerance:
            return False
        return True

    def get_display_name(name):
        for item in PAPER_SIZES:
            if item["name"] == name:
                w = item["width"]
                h = item["height"]
                w_str = f"{w:.1f}".rstrip('0').rstrip('.')
                h_str = f"{h:.1f}".rstrip('0').rstrip('.')
                return f"{name} ({w_str}mm x {h_str}mm)"
class DocumentHelper:

    @staticmethod
    def getFileFilter():
        """
        构建文件选择对话框的过滤器字符串。
        采用“总览 + 分类”的设计，提升用户体验。
        """
        all_extensions = set()
        filter_parts = []

        # 遍历支持的扩展名分类
        for category, ext_list in SUPPORTED_EXTENSIONS.items():
            # 将扩展名添加到总览集合中
            all_extensions.update(ext_list)
            new_cate = ""
            if category == FLAT_FILE_TYPES[0]:
                new_cate = _("MainWindow", "filter_pdf_and_image")
            elif category == FLAT_FILE_TYPES[1]:
                new_cate = _("MainWindow", "filter_word")
            elif category == FLAT_FILE_TYPES[2]:
                new_cate = _("MainWindow", "filter_ppt")
            else:
                new_cate = _("MainWindow", "filter_excel")
            
            # 构建当前分类的过滤器:前面是文件格式(分类名)，后面跟具体的支持格式，格式之间用空格隔开
            # 例如："Word(*.doc *.docx *.odt)"
            extensions_str = " ".join([f"*{ext}" for ext in ext_list]) 
            filter_parts.append(f"{new_cate}({extensions_str})")

        # 构建“所有支持的文档”总览过滤器
        all_wildcards = " ".join([f"*{ext}" for ext in sorted(all_extensions)])
        all_supported_filter = f"{_('MainWindow', 'filter_all_supported')}({all_wildcards})"

        # 拼接所有分类过滤器
        combined_filters = ";;".join([all_supported_filter] + filter_parts)

        # 在最后追加“所有文件 (*)”
        all_files_filter = f"{_('MainWindow', 'filter_all_files')} (*)"
        final_filter_string = f"{combined_filters};;{all_files_filter}"
        return final_filter_string

    @staticmethod
    def check_file_type(file_path):
        try:
            mime = magic.from_file(file_path, mime=True)
            if mime in ALLOWED_MIMES:
                return True, mime
            elif mime == "application/zip" and DocumentHelper.is_valid_ofd(file_path):
                return True, ALLOWED_MIMES[1]
            else:
                return False, _("MainWindow","file_error_magic_type",mime=mime)
        except Exception as e:
            return False, _("MainWindow","file_error_read_failure",error = str(e))

    @staticmethod
    def is_valid_ofd(file_path):
        """
        极速、精准地校验文件是否为合法的 OFD 格式
        """
        try:
            # zipfile 底层直接读取 ZIP
            with zipfile.ZipFile(file_path, 'r') as zf:
                # OFD 根目录包含 OFD.xml
                if 'OFD.xml' in zf.namelist():
                    return True
        except (zipfile.BadZipFile, OSError, ValueError):
            # 文件损坏、非 ZIP 格式或无法读取
            return False
            
        return False

    @staticmethod
    def get_ofd_page_count(ofd_path):
        try:
            with zipfile.ZipFile(ofd_path, 'r') as zf:
                # 读取 OFD.xml
                ofd_xml = zf.read('OFD.xml')
                root = ET.fromstring(ofd_xml)
                ns = {'ofd': 'http://www.ofdspec.org/2016'}

                # 查找 <ofd:DocBody> 元素
                doc_body = root.find('.//ofd:DocBody', ns)
                if doc_body is not None:
                    # 在 <ofd:DocBody> 下查找 <ofd:DocRoot> 子元素
                    doc_root_element = doc_body.find('ofd:DocRoot', ns)
                    if doc_root_element is not None:
                        # 获取 <ofd:DocRoot> 元素的文本内容
                        doc_root_path = doc_root_element.text
                        
                        if doc_root_path:
                            # 读取具体的 Document.xml 文件
                            doc_content = zf.read(doc_root_path)
                            doc_root_xml = ET.fromstring(doc_content)
                            
                            # 获取所有 <ofd:Page> 元素并返回数量
                            pages = doc_root_xml.findall('.//ofd:Page', ns)
                            return len(pages)
                
                # 直接统计 Pages 目录下的文件数
                page_files = [f for f in zf.namelist() if f.startswith('Pages/') and f.endswith('.xml')]
                if page_files:
                    return len(page_files)
                    
        except Exception as e:
            print(f"Error reading OFD: {e}")
        return -1
    @staticmethod
    def get_project_font_path():
        """
        获取项目目录下 fonts 文件夹中的中文字体绝对路径
        """
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(current_dir) 
        font_path = os.path.join(project_root, 'fonts', 'NotoSansCJKsc-Regular.ttf')
        if os.path.exists(font_path):
            return font_path
        return None

class PrinterHelper:

    @staticmethod
    def check_duplex_support(printer_name: str = None) -> bool:
        """
        使用 lpoptions 检测打印机是否支持双面打印。
        返回 True 表示支持，False 表示不支持或检测失败。
        """
        try:
            # 如果没有指定打印机，获取默认打印机
            if not printer_name:
                res = subprocess.run(['lpstat', '-d'], capture_output=True, text=True, timeout=5)
                if res.returncode != 0 or 'default destination' not in res.stdout:
                    return False
                printer_name = res.stdout.split()[-1]

            # 获取打印机详细选项列表
            res = subprocess.run(['lpoptions', '-p', printer_name, '-l'], 
                                capture_output=True, text=True, timeout=5)
            
            if res.returncode != 0:return False

            # 解析输出
            for line in res.stdout.splitlines():
                # 匹配以 Duplex 开头的行
                if line.startswith('Duplex'):
                    # 提取冒号后面的部分
                    if ':' not in line:
                        continue
                    options_part = line.split(':', 1)[1]
                    
                    # 分割所有选项值
                    values = [v.strip('*') for v in options_part.split()]
                    supported_modes = [v for v in values if v.lower() != 'none']
                    return len(supported_modes) > 0
            return False 

        except Exception:
            return False
    