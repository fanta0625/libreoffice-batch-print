# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import os
import time
from enum import Enum
from PySide6.QtCore import QObject, Signal, QThread, QMutex, QWaitCondition, QTimer
from services.uno_connect_service import lo_service 
from services.print_job_monitor import PrintStatus
from utils.status_type import msg_start_LO, msg_start_LO_error, msg_start_LO_success, msg_wait_LO_ready
from log.logger import get_logger
logger = get_logger("TaskManager")
from utils.i18n import _

# ================= 状态定义 =================
class TaskStatus(Enum):
    WAITING = "waiting"       # 等待
    SUCCESS = "success"       # 打印成功
    FAILED = "failed"         # 打印失败
    CANCELLED = "cancelled"   # 已取消

class TaskResult:
    def __init__(self, file_path, status, message="", detail=None):
        self.file_path = file_path
        self.status = status      # TaskStatus 枚举
        self.message = message 
        self.detail = detail   

    def __repr__(self):
        return f"<TaskResult {os.path.basename(self.file_path)}: {self.status.value}>"

# ================= 工作线程 =================

class WorkerThread(QThread):
    finished = Signal(object) # 返回结果

    def __init__(self, func, file_path, *args, **kwargs):
        super().__init__()
        self.func = func
        self.file_path = file_path
        self.args = args
        self.kwargs = kwargs
        self._is_cancelled = False

    def run(self):
        result = None
        try:
            # 检查是否在开始前就被取消
            if self._is_cancelled:
                result = TaskResult(self.file_path, TaskStatus.CANCELLED, -1)  # -1是用户取消
            else:
                success, message = self.func(*self.args, **self.kwargs)
                if self._is_cancelled:
                    result = TaskResult(self.file_path, TaskStatus.CANCELLED, -1) # -1是用户取消
                elif success:
                    result = TaskResult(self.file_path, TaskStatus.SUCCESS, message)
                else:
                    result = TaskResult(self.file_path, TaskStatus.FAILED, message)
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            result = TaskResult(self.file_path, TaskStatus.FAILED, f"系统异常: {str(e)}", detail=error_detail)

        # 只有在未被取消或结果本身就是取消状态时才发射信号
        if not self._is_cancelled or (result and result.status == TaskStatus.CANCELLED):
            self.finished.emit(result)

    def request_cancel(self):
        """请求取消任务，非阻塞"""
        self._is_cancelled = True


class TaskManager(QObject):
    """
    统一的任务管理器
    负责：LO 连接管理、页码获取队列、打印任务队列
    """
    status_message = Signal(object)
    task_status_changed = Signal(object)
    page_count_ready = Signal(str, object) 

    def __init__(self):
        super().__init__()
        self._ = _
        self.lo_manager = lo_service
        self.is_lo_ready = False
        self.lo_connecting = False
        self.active_workers = [] # 记录所有活跃线程
        self._shutdown_requested = False
        
        # 用于管理等待 LO 就绪的页码获取任务
        self._page_count_wait_queue = []
        self._lo_polling_timer = None
        
        # 启动时立即尝试连接 LO (异步)
        self.connect_lo_async()

    def connect_lo_async(self):
        if self.lo_connecting or self.is_lo_ready or self._shutdown_requested:
            return
        
        self.lo_connecting = True
        logger.info("Asynchronously connecting to the print engine ...")
        self.status_message.emit(msg_start_LO)
        
        def _connect():
            return self.lo_manager.connect_or_start()

        # 包装一下，使其返回 (success, msg) 格式
        def _wrapper():
            success = _connect()
            return success, "Ready" if success else "Failed"

        self._run_in_thread(_wrapper, file_path="SYSTEM", callback=self._on_lo_connected)

    def _on_lo_connected(self, result):
        self.lo_connecting = False
        if result.status == TaskStatus.SUCCESS:
            self.is_lo_ready = True
            self.status_message.emit(msg_start_LO_success)
            logger.info("Print engine ready")
            # LO 就绪后，立即处理等待队列
            self._process_page_count_wait_queue()
        else:
            self.status_message.emit(msg_start_LO_error)
            logger.error("Print engine startup failed")

    def get_page_count_async(self, file_path,sheet_index=-1):
        """异步获取页码"""
        if not self.is_lo_ready:
            logger.debug(f"LO is not ready, adding to wait queue: {os.path.basename(file_path)}")
            self.status_message.emit(msg_wait_LO_ready)
            # 将文件加入等待队列
            if file_path not in self._page_count_wait_queue:
                self._page_count_wait_queue.append(file_path)
            
            # 启动轮询定时器
            if self._lo_polling_timer is None:
                self._start_lo_polling()
            return
        
        # LO 已就绪，直接处理
        logger.debug(f"Submit page number retrieval task: {os.path.basename(file_path)}")
        def _get_count():
            result = self.lo_manager.get_page_count(file_path,sheet_index)
            if isinstance(result, tuple):
                return result[0]>0,(result[0], result[1]) 
                message = (result[0], result[1]) 
            else:
                return int(result)>0,result

        def _callback(result: TaskResult):
            msg = result.message
            if isinstance(msg, tuple):
                page_count, sheet_names = msg
            else:
                page_count = int(msg)
                sheet_names = []  # 非 Excel 文件没有 Sheet 列表
            self.page_count_ready.emit(file_path, (page_count, sheet_names))

        self._run_in_thread(_get_count, file_path, callback=_callback)

    def _start_lo_polling(self):
        """启动一个单一的定时器来轮询 LO 状态"""
        if self._lo_polling_timer is not None:
            return
        self._lo_polling_timer = QTimer()
        self._lo_polling_timer.setSingleShot(False) # 重复定时器
        self._lo_polling_timer.timeout.connect(self._check_lo_and_process_queue)
        self._lo_polling_timer.start(1000) # 每秒检查一次

    def _check_lo_and_process_queue(self):
        """检查 LO 是否就绪，并处理等待队列"""
        if self.is_lo_ready:
            self._process_page_count_wait_queue()
        elif self._shutdown_requested:
            # 如果正在关闭，也停止轮询
            self._cleanup_lo_polling()

    def _process_page_count_wait_queue(self):
        """处理等待队列中的所有文件"""
        if not self._page_count_wait_queue:
            return
            
        waiting_files = self._page_count_wait_queue.copy()
        self._page_count_wait_queue.clear()
        self._cleanup_lo_polling() # 处理完后停止轮询
        
        for file_path in waiting_files:
            self.get_page_count_async(file_path) 

    def _cleanup_lo_polling(self):
        """清理轮询定时器"""
        if self._lo_polling_timer:
            self._lo_polling_timer.stop()
            self._lo_polling_timer.deleteLater()
            self._lo_polling_timer = None

    def print_file_async(self, file_path, options=None):
        if not self.is_lo_ready:
            self.status_message.emit(msg_wait_LO_ready)
            logger.warning(f"The print engine is not ready, ignoring the print request: {os.path.basename(file_path)}")
            return

        logger.info(f"Create a print task: {os.path.basename(file_path)}")
        self.task_status_changed.emit(TaskResult(file_path, TaskStatus.WAITING, ("MainWindow","message_in_queue")))

        def _print():
            success, msg = self.lo_manager.print_document(file_path, options)
            return success, msg

        def _callback(result: TaskResult):
            self.task_status_changed.emit(result)

        self._run_in_thread(_print,file_path, callback=_callback)

    def _run_in_thread(self, func, file_path, callback=None):
        worker = WorkerThread(func,file_path)
        self._register_worker(worker)

        if callback:
            worker.finished.connect(callback)

        worker.start()

    def _register_worker(self, worker):
        self.active_workers.append(worker)
        # 将清理逻辑连接到线程的 finished 信号
        worker.finished.connect(lambda: self._cleanup_worker(worker))

    def _cleanup_worker(self, worker):
        """安全地清理已完成的 worker"""
        if worker in self.active_workers:
            self.active_workers.remove(worker)
        worker.deleteLater() # 安全地安排删除

    def cancel_task(self, file_path):
        """取消特定文件的任务"""
        logger.info(f"用户取消任务: {os.path.basename(file_path)}")
        for worker in self.active_workers[:]:
            if worker.file_path == file_path and not worker.isFinished():
                worker.request_cancel()
                # 发送取消状态
                self.task_status_changed.emit(TaskResult(file_path, TaskStatus.CANCELLED, "用户取消"))
                return True
        return False

    def shutdown(self):
        """优雅关闭所有线程"""
        logger.info("正在关闭 TaskManager...")
        self._shutdown_requested = True
        
        # 清理 LO 轮询器
        self._cleanup_lo_polling()
        self._page_count_wait_queue.clear()
        
        # 请求所有活跃线程取消
        for worker in self.active_workers[:]:
            worker.request_cancel()
        
        # 等待所有线程自然结束 (最多等待 1 秒，10 * 100ms)
        for _ in range(10): 
            if not self.active_workers:
                break
            time.sleep(0.1) # 非阻塞式等待
        
        # 强制清理任何剩余的线程
        if self.active_workers:
            logger.warning(f"仍有 {len(self.active_workers)} 个线程未能及时停止，将强制清理。")
            for worker in self.active_workers[:]:
                self._cleanup_worker(worker)
        
        logger.info(f"已清理所有工作线程")
        
        # 关闭 LO 进程
        if hasattr(self.lo_manager, 'shutdown'):
            self.lo_manager.shutdown()
        
        logger.info("✅ TaskManager 已完全关闭")
# 全局单例
task_manager = TaskManager()