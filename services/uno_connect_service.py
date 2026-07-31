# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import tempfile
import subprocess
import time
import fitz
import platform
import os
import threading
import socket
import json
import shutil
import uno
import math
import copy
from lru import LRU
from com.sun.star.beans import PropertyValue
from com.sun.star.awt import Size as UnoSize
from com.sun.star.awt import Point as UnoPoint

from PySide6.QtCore import QObject, Signal, QMutex, QTimer
from config.settings import SUPPORTED_EXTENSIONS, DEFAULT_PRINTER_ID, PAPER_SIZES,UNO_CONST
from models.file_model import PaperOrientations, DuplexMode, ScalingMode, LayoutMode, LayoutDirection,PresentationContentType
from utils.paper_utils import PaperSizeHelper,DocumentHelper
from services.create_nup_pdf import create_nup_pdf, create_booklet_pdf
from services.excel_layout_engine import ExcelLayoutEngine
from services.stats_service import StatsService
from log.logger import get_logger
from services.print_job_monitor import PrintStatus
from services.print_job_monitor import PrintJobMonitor
from utils.i18n import _


logger = get_logger("UnoConnectorService")

def pv(name, value):
    p = PropertyValue()
    p.Name = name
    p.Value = value
    return p


class UnoConnectorService(QObject):
    # 信号定义,接收外部文件列表信号
    files_received = Signal(list) 
    def __init__(self):
        super().__init__()
        self.local_ctx = None
        self.desktop = None
        self.process = None
        self.is_temp_instance = False
        self.temp_profile_dir = None
        
        # 互斥锁：确保 UNO 操作串行化
        self.uno_lock = QMutex()
        self.ipc_socket = None
        self.is_ipc_server = False
        self._ipc_thread = None
        self._printer_cache = []
        self._cache_time = 0
        self._ = _

        # PDF 转换缓存,最多缓存 100 个文件
        self._pdf_cache = LRU(100)
        # 用于保护缓存读写的锁
        self._cache_lock = threading.RLock()

    # ================= 1. 核心连接与启动逻辑 =================
    def connect_or_start(self, timeout=10):
        """连接现有 LO 或启动新的 Headless 实例"""
        if self.desktop:
            return True
        if self._connect_to_existing():
            self.is_temp_instance = False
            logger.info("成功连接到现有的 Office 实例")
            return True

        # 2. 启动新实例
        logger.info("未检测到运行中的服务，正在启动 Headless 实例...")
        if self.start_headless_instance():
            for _ in range(timeout * 2): # 增加等待次数
                time.sleep(0.5)
                if self._connect_to_existing():
                    self.is_temp_instance = True
                    logger.info("后台 Headless 服务启动成功")
                    return True
        logger.error("无法启动或连接 Office 服务")
        return False

    def _connect_to_existing(self):
        try:
            local_ctx = uno.getComponentContext()
            resolver = local_ctx.ServiceManager.createInstanceWithContext("com.sun.star.bridge.UnoUrlResolver", local_ctx)
            ctx = resolver.resolve(f"uno:socket,host={UNO_CONST["HOST"]},port={UNO_CONST["UNO_PORT"]};urp;StarOffice.ComponentContext")
            self.desktop = ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
            self.local_ctx = ctx
            logger.debug(f"UNO 连接成功: {UNO_CONST['HOST']}:{UNO_CONST['UNO_PORT']}")
            return True
        except Exception as e:
            logger.debug(f"连接现有实例失败: {e}")
            return False

    def start_headless_instance(self):
        """启动带临时配置的 Headless 实例"""
        try:
            # 创建唯一的临时配置目录
            self.temp_profile_dir = tempfile.mkdtemp(prefix="lo_batch_")

            cmd = [UNO_CONST['LO_EXECUTABLE'],"--headless","--invisible","--norestore",
                "--nologo","--nodefault","--nolockcheck",
                f"--accept=socket,host={UNO_CONST['HOST']},port={UNO_CONST['UNO_PORT']};urp;",
                f"-env:UserInstallation=file://{self.temp_profile_dir}"  # 隔离配置
            ]
            
            logger.info(f"启动命令: {' '.join(cmd)}")
            env = os.environ.copy()
            self.process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,env=env)
            logger.debug("LO 进程已启动 (PID: %s)", self.process.pid)
            return True
        except Exception as e:
            logger.error(f"启动 LO 实例失败: {e}", exc_info=True)
            if self.temp_profile_dir and os.path.exists(self.temp_profile_dir):
                shutil.rmtree(self.temp_profile_dir, ignore_errors=True)
            return False

    # ================= 2. 单例 IPC 通信逻辑 =================
    def start_ipc_server(self):
        """启动 IPC 监听服务器"""
        if self.is_ipc_server:  return True
        self.ipc_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.ipc_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.ipc_socket.bind((UNO_CONST['HOST'], UNO_CONST['IPC_PORT']))
            self.ipc_socket.listen(5)
            self.is_ipc_server = True
            logger.info(f"📡 IPC 服务已启动 (端口 {UNO_CONST['IPC_PORT']})")
            
            # 启动监听线程
            self._ipc_thread = threading.Thread(target=self._ipc_loop, daemon=True)
            self._ipc_thread.start()
            return True
        except OSError as e:
            logger.error(f"IPC 启动失败: {e}")
            return False

    def send_files_to_instance(self, files):
        """向运行中的实例发送文件。如果发送成功返回 True，否则返回 False。"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1.0)
                s.connect((UNO_CONST['HOST'], UNO_CONST['IPC_PORT']))
                payload = json.dumps({"files": [os.path.abspath(f) for f in files]}).encode('utf-8')
                s.sendall(len(payload).to_bytes(4, 'big') + payload)
                return True
        except (ConnectionRefusedError, socket.timeout, OSError):
            return False

    def _ipc_loop(self):
        """IPC 监听循环"""
        while self.is_ipc_server:
            try:
                conn, addr = self.ipc_socket.accept()
                threading.Thread(target=self._handle_ipc_client, args=(conn,), daemon=True).start()
            except Exception as e:
                if self.is_ipc_server:
                    logger.error(f"IPC 接受连接错误: {e}")
                break

    def _handle_ipc_client(self, conn):
        """处理单个 IPC 客户端连接"""
        try:
            raw_len = conn.recv(4)
            if not raw_len: return
            length = int.from_bytes(raw_len, 'big')
            data = b""
            while len(data) < length:
                chunk = conn.recv(length - len(data))
                if not chunk:
                    break
                data += chunk
            
            payload = json.loads(data.decode('utf-8'))
            files = payload.get("files", [])
            if files:
                logger.info(f"📩 收到外部文件请求: {len(files)} 个文件")
                self.files_received.emit(files)
        except Exception as e:
            logger.error(f"IPC 数据处理错误: {e}")
            import traceback
            traceback.print_exc()
        finally:
            conn.close()

    # ================= 3. 业务逻辑 (页码/打印) =================

    def print_document(self, file_path, params):
        logger.info(f"开始打印任务: {os.path.basename(file_path)}")
        doc = None
        target_doc = None
        temp_file_path = None
        pdf_temp_path = None
        pre_process_pdf = None
        processed_pdf = None
        self.uno_lock.lock()
        try:
            if not self.desktop:
                if not self.connect_or_start():
                    return False, "打印引擎未就绪"

            props = self.get_hidden_property()
            doc,temp_file_path = self._load_document_safely(file_path,tuple(props))
            doc_type = self._get_document_type(file_path,doc)
            target_doc = doc
            user_landscape = (params.orientation == PaperOrientations.LANDSCAPE)
            if doc_type == "writer":
                logger.info("🔄 检测到 Word 文档，转换为 PDF 以冻结排版并防止重排...")
                try:
                    pdf_temp_path = self.export_doc_to_pdf(doc)
                    doc.close(True) # 关闭 Word 文档
                    doc = None
                    temp_file_path = None # Word 临时文件稍后清理，或者现在清理
                    
                    # 加载新生成的 PDF
                    target_doc, pdf_temp_path = self._load_document_safely(pdf_temp_path, tuple(props))
                    if not target_doc:
                        raise Exception("PDF 转换后加载失败")
                    
                    doc_type = "draw" 
                    logger.info("✅ Word 转 PDF 成功，将继续使用 PDF 居中引擎")
                except Exception as e:
                    logger.error(f"Word 转 PDF 失败: {e}", exc_info=True)
                    # 如果转换失败，回退到原始逻辑
                    target_doc = doc
                    doc_type = "writer"
                    if doc is None:
                         return False, f"Word 转 PDF 失败且无法回退: {e}"

            if doc_type == "draw":
                # 计算目标纸张尺寸（毫米）
                paper_info = PaperSizeHelper.get_raw_data_by_display_name(params.paper_size)
                target_w_mm = float(paper_info['width'])
                target_h_mm = float(paper_info['height'])
                # 确定待处理的 PDF 文件路径
                pdf_to_process = pdf_temp_path if pdf_temp_path and os.path.exists(pdf_temp_path) else temp_file_path

                if pdf_to_process and not pdf_to_process.lower().endswith('.pdf'):
                    try:
                        logger.info(f"检测到非 PDF 文件（{os.path.splitext(pdf_to_process)[1]}），正在转换为 PDF...")
                        temp_pdf = self.export_doc_to_pdf(target_doc)
                        pdf_to_process = temp_pdf
                        pdf_temp_path = temp_pdf   
                        logger.info(f"图片已成功转换为 PDF: {temp_pdf}")
                    except Exception as e:
                        logger.error(f"图片转 PDF 失败: {e}", exc_info=True)

                if pdf_to_process and pdf_to_process.lower().endswith('.pdf'):
                    if params.layout_mode == LayoutMode.PAGE_SCALE:
                        need_scale = (params.scaling_mode == ScalingMode.FIT_TO_PRINTABLE)
                        if need_scale:
                            processed_pdf = self.scale_pdf_vector(pdf_to_process, target_w_mm, target_h_mm, user_landscape)
                        else:
                            # 非缩放模式：根据方向选择旋转或居中
                            if user_landscape:
                                processed_pdf = self.rotate_pdf_only(pdf_to_process, target_w_mm, target_h_mm)
                            else:
                                processed_pdf = self.center_pdf_only(pdf_to_process, target_w_mm, target_h_mm)
                    elif params.layout_mode == LayoutMode.N_UP:
                        pre_process_pdf = self._create_pdf_subset(pdf_to_process,params.page_range)
                        # 如果用户选择了横向，交换纸张尺寸
                        if user_landscape:
                            paper_width, paper_height = target_h_mm, target_w_mm
                        else:
                            paper_width,paper_height = target_w_mm,target_h_mm
                        processed_pdf = create_nup_pdf(pre_process_pdf,rows=params.n_up_layout.rows,cols=params.n_up_layout.cols,
                            layout_order=params.n_up_layout.direction,paper_size=(paper_width, paper_height),orientation=PaperOrientations.AUTO,
                            draw_borders=params.n_up_layout.draw_border
                        )
                    elif params.layout_mode == LayoutMode.BOOKLET:
                        pre_process_pdf = self._create_pdf_subset(pdf_to_process,params.page_range)
                        paper_width = max(target_w_mm,target_h_mm)
                        paper_height = min(target_w_mm,target_h_mm)
                        processed_pdf = create_booklet_pdf(pre_process_pdf,paper_size=(paper_width, paper_height),direction=params.booklet.direction)

                    # 关闭原文档，加载处理后的 PDF
                    if target_doc:
                        target_doc.close(True)
                    target_doc, pdf_temp_path = self._load_document_safely(processed_pdf, tuple(props))
                    doc_type = self._get_document_type(file_path,target_doc)
                    logger.info(f"✅ 处理后的 PDF: {processed_pdf}")
            
            if doc_type == "impress":
                success, processed_pdf, new_type = self.process_impress_print_mode(target_doc,params)
                if isinstance(processed_pdf, str):
                    load_props = tuple([])
                    target_doc = self.desktop.loadComponentFromURL(uno.systemPathToFileUrl(processed_pdf), "_blank", 0, load_props)
                    doc_type = new_type
                else:
                    raise Exception("未知的文档数据类型")

            if doc_type == "calc":
                logger.info("检测到电子表格文档，正在设置页面方向...")
                calc_params = copy.deepcopy(params.document_options)
                calc_params.is_landscape = user_landscape
                calc_engine = ExcelLayoutEngine(self)
                processed_pdf = calc_engine.export_to_pdf(target_doc,calc_params)
                target_doc, pdf_temp_path = self._load_document_safely(processed_pdf, tuple(props))
                
            # 设置打印机属性
            print_props = self.build_printer_properties(params)
            try:
                target_doc.setPrinter(tuple(print_props))
            except Exception:
                pass
            
            # 执行打印
            print_opts = self.build_print_options(params,file_path)

            monitor = PrintJobMonitor(file_path)
            listener = monitor.create_listener()

            try:
                XPrintJobBroadcaster = uno.getTypeByName("com.sun.star.view.XPrintJobBroadcaster")
                broadcaster = target_doc.queryInterface(XPrintJobBroadcaster)
                if broadcaster is not None:
                    broadcaster.addPrintJobListener(listener)
                    logger.info(f"✅ 已注册打印监听器: {os.path.basename(file_path)}")
                else:
                    logger.warning("⚠️ 无法获取 XPrintJobBroadcaster")
            except Exception as e:
                logger.error(f"❌ 注册监听器失败: {e}")

            # 执行打印
            target_doc.print(print_opts)
            logger.info(f"📤 打印命令已发送: {os.path.basename(file_path)}")

            # 等待结果
            result = monitor.wait_for_result(timeout=60)

            if result["status"] == PrintStatus.SUBMITTED:
                return True, result["message"]
            else:
                return False, result["message"]

        except Exception as e:
            logger.error(f"打印异常: {e}", exc_info=True)
            return False, str(e)
        finally:
            self.uno_lock.unlock()
            self._cleanup_resources([doc,target_doc],[temp_file_path,pdf_temp_path,pre_process_pdf,processed_pdf])

    def _cleanup_resources(self, docs=None, paths=None):
        """统一资源清理"""
        if docs:
            for d in docs:
                try: d.close(True)
                except: pass
        if paths:
            for path in paths:
                if path is None:continue
                for i in range(5): # 最多重试5次
                    try:
                        os.unlink(path)
                        logger.debug(f"成功清理临时文件: {path}")
                        break
                    except PermissionError:
                        time.sleep(0.5)
                    except Exception as e:
                        logger.error(f"清理临时文件失败: {path}, 错误: {e}")
                        break

    def process_impress_print_mode(self, target_doc, params):
        try:
            # 获取文件路径
            file_url = target_doc.getURL()
            file_path = uno.fileUrlToSystemPath(file_url)

            paper_info = PaperSizeHelper.get_raw_data_by_display_name(params.paper_size)
            paper_w_mm = float(paper_info['width'])
            paper_h_mm = float(paper_info['height'])
            is_landscape = (params.orientation == PaperOrientations.LANDSCAPE)

            engine_params = {
                "paper_size": (paper_w_mm, paper_h_mm),
                "orientation": params.orientation,
                "scaling_mode": params.scaling_mode,
                "doc_options":params.document_options
            }

            from services.ppt_layout_engine import PPTLayoutEngine
            engine = PPTLayoutEngine(self)
            processed_pdf = engine.generate_layout_pdf(file_path, engine_params)

            target_doc.close(True)
            new_doc, new_temp = self._load_document_safely(processed_pdf, tuple(self.get_hidden_property()))
            return True, processed_pdf, "draw"
        except Exception as e:
            logger.error(f"PPT 布局引擎失败: {e}", exc_info=True)
            return False, None, None

    # 防止libreoffice和应用同时加载同一个文件造成的文档夹载失败的问题
    def _load_document_safely(self, file_path: str, load_props=tuple([])):
        _, ext = os.path.splitext(file_path)
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                temp_path = tmp.name
            shutil.copy2(file_path, temp_path)
            url = uno.systemPathToFileUrl(temp_path)
            doc = self.desktop.loadComponentFromURL(url, "_blank", 0, load_props)
            return doc, temp_path
        except Exception as e:
            logger.error(f"加载失败: {e}")
            if temp_path and os.path.exists(temp_path): os.unlink(temp_path)
            return None, None

    def build_print_options(self,params,file_path):
        props = [
            pv("Wait", True),
            pv("Silent", True),
            pv('CopyCount', int(params.copies)),
            pv('Collate', True),
            pv("JobName", os.path.basename(file_path))
        ]
        # 页码范围
        if hasattr(params, 'page_range') and params.page_range:
            props.append(pv("Pages", params.page_range))
        # 双面
        if hasattr(params, 'duplex_mode'):
            mode_map = {DuplexMode.NONE: 0,DuplexMode.LONG_EDGE: 2, DuplexMode.SHORT_EDGE: 3}
            props.append(pv("DuplexMode", mode_map.get(params.duplex_mode, 0)))
        return props

    def build_printer_properties(self, params):
        """构建 UNO 打印属性"""
        props = []
        if params.printer and params.printer not in ["默认", "自动", "Default"]:
            props.append(pv('Name',params.printer))

        # 获取基础尺寸数据
        paper_info = PaperSizeHelper.get_raw_data_by_display_name(params.paper_size)

        # 使用User 自定义格式
        # user_format_enum = uno.Enum("com.sun.star.view.PaperFormat", "USER")
        # props.append(pv("PaperFormat", user_format_enum))
        # 设置方向
        # orient_val = 0
        # if params.orientation != PaperOrientations.AUTO:
        #     orient_val = 1 if params.orientation == PaperOrientations.LANDSCAPE else 0
        #     target_orient = uno.Enum(UNO_CONST['PAPER_ORIENTATION'], 'LANDSCAPE' if orient_val else 'PORTRAIT')
        #     props.append(pv("PaperOrientation", target_orient))
        
        # 设置纸张格式、大小， 自定义纸张格式
        target_paper_format = uno.Enum(UNO_CONST['PAPER_FORMAT'],paper_info['name'].upper())
        props.append(pv("PaperFormat", target_paper_format))

        # if orient_val == 1:  # Landscape
        #     props.append(pv("PaperSize", UnoSize(int(paper_info['height'])*100, int(paper_info['width'])*100)))
        # else:  # Portrait
        #     props.append(pv("PaperSize", UnoSize(int(paper_info['width'])*100, int(paper_info['height'])*100)))

        return tuple(props)

    def _create_pdf_subset(self, input_pdf_path: str, page_range: str) -> str:
        """
        根据页码范围字符串，从源PDF中提取页面并生成一个新的临时PDF文件。
        
        Args:
            input_pdf_path: 源PDF文件的路径。
            page_range_str: 页码范围字符串，例如 "1-3, 5, 7-9"。
            
        Returns:
            新生成的临时PDF文件的路径。
            
        Raises:
            ValueError: 如果页码范围格式不正确或超出文档页数。
        """
        if not page_range:
            return input_pdf_path

        doc = fitz.open(input_pdf_path)
        total_pages = doc.page_count
        page_indices = StatsService.get_page_indices(page_range,total_pages)
        
        if not page_indices:
            doc.close()
            raise ValueError("页码范围未选择任何有效页面")

        # 创建新的PDF文档
        new_doc = fitz.open()
        # 按顺序插入页面
        for i in sorted(page_indices):
            new_doc.insert_pdf(doc, from_page=i, to_page=i)
        
        doc.close()

        # 保存为临时文件
        output_pdf_path = tempfile.mktemp(suffix=".pdf")
        new_doc.save(output_pdf_path)
        new_doc.close()
        
        logger.info(f"已根据页码范围 '{page_range}' 生成临时PDF: {output_pdf_path}")
        return output_pdf_path

    def get_page_count(self, file_path, sheet_index=-1):
        self.uno_lock.lock()
        temp_pdf = None
        path = None
        try:
            if not self.desktop and not self.connect_or_start():
                return -1
            # OFD 直接走专用解析器
            if file_path.lower().endswith('.ofd'):
                return DocumentHelper.get_ofd_page_count(file_path)
            
            doc, path = self._load_document_safely(file_path, tuple(self.get_hidden_property()))
            if not doc:
                return 0
            
            try:
                if doc.supportsService("com.sun.star.text.TextDocument"):
                    cursor = doc.getCurrentController().getViewCursor()
                    cursor.jumpToLastPage()
                    return cursor.getPage()
                if doc.supportsService("com.sun.star.drawing.DrawingDocument"):
                    return doc.getDrawPages().getCount()
                if doc.supportsService("com.sun.star.presentation.PresentationDocument"):
                    return doc.getDrawPages().getCount()
                elif doc.supportsService("com.sun.star.sheet.SpreadsheetDocument"):
                    sheets = doc.getSheets()
                    sheet_names = list(sheets.getElementNames())
                    temp_pdf = self.export_doc_to_pdf(doc)
                    f_doc = fitz.open(temp_pdf)
                    page_count = f_doc.page_count
                    f_doc.close()
                    return (page_count, sheet_names)
            finally:
                # 确保 doc 总是被关闭
                if doc:
                    try:doc.close(True)
                    except Exception:
                        pass
                # 清理创建的临时副本
                if path and os.path.exists(path):
                    try:
                        os.unlink(path)
                    except Exception:pass
            return 0
        except Exception as e:
            # 记录异常信息，便于调试
            logger.error(f"获取页数失败: {file_path}, 错误: {e}", exc_info=True)
            return -1
        finally:
            # 清理创建的临时PDF
            if temp_pdf and os.path.exists(temp_pdf):
                try:
                    os.unlink(temp_pdf)
                except Exception:pass
            self.uno_lock.unlock()

    def get_readonly_property(self):
        props = []
        hid_props = self.get_hidden_property()
        props.append(hid_props[0])

        # ReadOnly
        props.append(pv('ReadOnly',True))
        return props

    def get_hidden_property(self):
        return [pv('Hidden', True)]

    def transform_pdf(
        self,
        input_pdf: str,
        target_width_mm: float,
        target_height_mm: float,
        rotate_angle: int = 0,
        scale_to_fit: bool = False,
        keep_aspect_ratio: bool = True,
        show_border: bool = False,
        margin: float = 2.0
    ) -> str:
        """
        通用的 PDF 页面变换函数。
        
        Args:
            input_pdf: 输入 PDF 路径。
            target_width_mm: 目标纸张宽度（毫米）。
            target_height_mm: 目标纸张高度（毫米）。
            rotate_angle: 旋转角度。
            scale_to_fit: 是否将内容缩放到适应目标纸张。
            keep_aspect_ratio: 缩放时是否保持宽高比。
            show_border:控制是否显示边框的参数
        Returns:
            输出 PDF 的临时文件路径。
        """
        factor = 72 / 25.4  # mm to pt

        # --- 1. 确定目标纸张尺寸（始终为纵向） ---
        target_w_pt = min(target_width_mm, target_height_mm) * factor
        target_h_pt = max(target_width_mm, target_height_mm) * factor

        logger.info(f"目标纸张尺寸（纵向）: {target_w_pt:.2f} x {target_h_pt:.2f} pts")
        logger.info(f"变换参数: rotate={rotate_angle}°, scale_to_fit={scale_to_fit}")

        src_doc = fitz.open(input_pdf)
        dst_doc = fitz.open()

        for i in range(len(src_doc)):
            src_page = src_doc[i]
            src_rect = src_page.rect
            src_w, src_h = src_rect.width, src_rect.height

            # --- 2. 计算变换后的内容逻辑尺寸 ---
            if rotate_angle % 180 == 0:
                logical_w, logical_h = src_w, src_h
            else:
                logical_w, logical_h = src_h, src_w

            if show_border:
                logical_w -= 2*margin
                logical_h -= 2*margin

            # --- 3. 计算最终的目标矩形 (target_rect) ---
            if scale_to_fit:
                # 需要缩放
                if keep_aspect_ratio:
                    scale_x = target_w_pt / logical_w
                    scale_y = target_h_pt / logical_h
                    scale = min(scale_x, scale_y)
                    content_w = logical_w * scale
                    content_h = logical_h * scale
                else:
                    # 拉伸以完全填充
                    content_w = target_w_pt
                    content_h = target_h_pt
            else:
                # 不缩放，使用原始逻辑尺寸
                content_w = logical_w
                content_h = logical_h

            # 居中计算
            x = (target_w_pt - content_w) / 2
            y = (target_h_pt - content_h) / 2
            target_rect = fitz.Rect(x, y, x + content_w, y + content_h)

            # --- 4. 创建新页面并绘制 ---
            new_page = dst_doc.new_page(width=target_w_pt, height=target_h_pt)
            new_page.show_pdf_page(
                target_rect,
                src_doc,
                i,
                clip=src_rect,
                rotate=rotate_angle
            )
            if show_border:
                # 绘制边框
                border_rect = fitz.Rect(target_rect.x0 - margin, target_rect.y0 - margin, target_rect.x1 + margin, target_rect.y1 + margin)
                self._draw_content_border(new_page, border_rect)

        src_doc.close()
        out_pdf = tempfile.mktemp(suffix=".pdf")
        dst_doc.save(out_pdf, garbage=3, deflate=True)
        dst_doc.close()

        return out_pdf

    def _draw_content_border(self, page, rect, width=0.5):
        """
        为指定的内容区域绘制带内边距的边框
        :param page: fitz.Page 对象
        :param rect: 内容区域的矩形 (fitz.Rect)
        :param width: 边框线宽（pt）
        """
        border_rect = fitz.Rect(
            round(rect.x0 ), 
            round(rect.y0 ), 
            round(rect.x1 ), 
            round(rect.y1)
        )
        page.draw_rect(border_rect,width=width)

    def center_pdf_only(self, input_pdf, target_width_mm, target_height_mm,show_border=False):
        """将 PDF 内容居中到目标纸张（纵向），不缩放，不旋转。"""
        return self.transform_pdf(
            input_pdf, 
            target_width_mm, 
            target_height_mm, 
            rotate_angle=0, 
            scale_to_fit=False,
            show_border=show_border
        )

    def rotate_pdf_only(self, input_pdf, target_width_mm, target_height_mm,show_border=False):
        """仅将 PDF 内容旋转 90 度并居中，纸张保持纵向尺寸。"""
        return self.transform_pdf(
            input_pdf, 
            target_width_mm, 
            target_height_mm, 
            rotate_angle=90, 
            scale_to_fit=False,
            show_border=show_border
        )

    def scale_pdf_vector(self, input_pdf, target_width_mm, target_height_mm, target_is_landscape,show_border=False):
        """
        将 PDF 页面缩放到目标纸张尺寸。
        如果 target_is_landscape 为 True，则内容旋转 90 度。
        """
        rotate_angle = 90 if target_is_landscape else 0
        return self.transform_pdf(
            input_pdf, 
            target_width_mm, 
            target_height_mm, 
            rotate_angle=rotate_angle, 
            scale_to_fit=True,
            keep_aspect_ratio=True,
            show_border=show_border
        )
    
    def _get_document_type(self,file_path, doc):
        if not doc: 
            if file_path and file_path.lower().endswith('.ofd'):
                return 'writer'
            return None
        if doc.supportsService("com.sun.star.text.TextDocument"): return "writer"
        if doc.supportsService("com.sun.star.drawing.DrawingDocument"): return "draw"
        if doc.supportsService("com.sun.star.sheet.SpreadsheetDocument"): return "calc"
        if doc.supportsService("com.sun.star.presentation.PresentationDocument"): return "impress"
        return "unknown"

    def get_printer_list(self, force_refresh=False):
        """获取打印机列表 (带缓存)"""
        current_time = time.time()
        if not force_refresh and self._printer_cache and (current_time - self._cache_time) < 10:
            return self._printer_cache

        printers = []
        try:
            if not self.desktop and not self.connect_or_start():
                return ["未连接服务"]
            ps = self.local_ctx.ServiceManager.createInstanceWithContext("com.sun.star.awt.PrinterServer", self.local_ctx)
            printers = [str(n) for n in ps.getPrinterNames()]
        except:
            printers = [DEFAULT_PRINTER_ID]
        
        self._printer_cache = printers
        self._cache_time = current_time
        return printers

    def export_doc_to_pdf(self,doc):
        """
        通用的文档转 PDF 方法，自动识别文档类型并匹配正确的过滤器
        """
        filter_name = "writer_pdf_Export"  # 默认为 Writer
        if doc.supportsService("com.sun.star.sheet.SpreadsheetDocument"):
            filter_name = "calc_pdf_Export"
        elif doc.supportsService("com.sun.star.presentation.PresentationDocument"):
            filter_name = "impress_pdf_Export"
        elif doc.supportsService("com.sun.star.drawing.DrawingDocument"):
            filter_name = "draw_pdf_Export"
        tmp_file = tempfile.NamedTemporaryFile(suffix=".pdf",delete=False)
        tmp_path = tmp_file.name
        tmp_file.close()
        # 执行导出
        out_url = uno.systemPathToFileUrl(os.path.abspath(tmp_path))
        export_props = (pv("FilterName", filter_name),)
        doc.storeToURL(out_url, export_props)
    
        return tmp_path

    def get_cached_pdf_by_path(self,input_path: str):
        cached_pdf = None
        with self._cache_lock:
            if input_path in self._pdf_cache:
                cached_pdf = self._pdf_cache[input_path]
                if not os.path.exists(cached_pdf):
                    del self._pdf_cache[input_path]
                    cached_pdf = None
                else:
                    return cached_pdf
        if not cached_pdf:
            doc, temp_file_path = self._load_document_safely(input_path)
            if not doc: return None
            try:
                tmp_pdf = self.export_doc_to_pdf(doc)
                # 将生成的PDF加入缓存
                with self._cache_lock:
                    self._pdf_cache[input_path] = tmp_pdf
                return tmp_pdf
            finally:
                # 关闭并清理原始文档的临时副本
                try: doc.close(True)
                except: pass
                if temp_file_path and os.path.exists(temp_file_path):
                    try: os.unlink(temp_file_path)
                    except: pass

    # ================= 4. 清理 =================

    def shutdown(self):
        logger.info("正在关闭 UnoConnectorService...")
        self.is_ipc_server = False
        if self.ipc_socket:self.ipc_socket.close()
        if self.is_temp_instance and self.process:
            logger.info("终止临时 LO 进程...")
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except:
                self.process.kill()
            finally:
                self.process = None

        # 清理缓存的临时 PDF 文件
        with self._cache_lock:
            for pdf_path in self._pdf_cache.values():
                if os.path.exists(pdf_path):
                    try:
                        os.unlink(pdf_path)
                        logger.debug(f"清理缓存文件: {pdf_path}")
                    except Exception as e:
                        logger.error(f"清理缓存文件失败 {pdf_path}: {e}")
            self._pdf_cache.clear()
        
        # 清理临时目录
        if self.temp_profile_dir and os.path.exists(self.temp_profile_dir):
            try:
                shutil.rmtree(self.temp_profile_dir)
                logger.info(f"已清理临时目录: {self.temp_profile_dir}")
            except Exception as e:
                logger.error(f"清理目录失败: {e}")
        
        self.desktop = None
        self.local_ctx = None
        logger.info("UnoConnectorService 已关闭")

    def __del__(self):
        self.shutdown()

# 全局单例
lo_service = UnoConnectorService()