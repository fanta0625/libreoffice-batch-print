# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import threading
import uno
from enum import Enum
from utils.i18n import _
from log.logger import get_logger
logger = get_logger("PrintJobMonitor")

# 硬编码 PrintableState 的值
PRINTABLE_STATE = {
    "JOB_STARTED":          uno.Enum("com.sun.star.view.PrintableState", "JOB_STARTED"),
    "JOB_COMPLETED":        uno.Enum("com.sun.star.view.PrintableState", "JOB_COMPLETED"),
    "JOB_SPOOLED":          uno.Enum("com.sun.star.view.PrintableState", "JOB_SPOOLED"),
    "JOB_ABORTED":          uno.Enum("com.sun.star.view.PrintableState", "JOB_ABORTED"),
    "JOB_FAILED":           uno.Enum("com.sun.star.view.PrintableState", "JOB_FAILED"),
    "JOB_SPOOLING_FAILED":  uno.Enum("com.sun.star.view.PrintableState", "JOB_SPOOLING_FAILED")
}
class PrintStatus(Enum):
    WAITING = "waiting"
    SUBMITTED = "submitted"
    FAILED = "failed"
    CANCEL = "cancel"
    TIMEOUT = "timeout"

class PrintJobMonitor:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.job_name = file_path.split("/")[-1]
        self._event = threading.Event()
        self._result = {"status": PrintStatus.WAITING, "message": ""}
        self._ = _

    def create_listener(self):
        # 获取接口类型
        XPrintJobListener = uno.getTypeByName("com.sun.star.view.XPrintJobListener")

        class PrintJobListenerImpl:
            def printJobEvent(inner_self, event_obj):
                state = event_obj.State 
                # 打印原始状态
                logger.debug(f"🖨️ 原始状态: {state} (type: {type(state)})")

                if state == PRINTABLE_STATE['JOB_SPOOLED']:
                    msg = f"✅ 打印任务 '{self.job_name}' 已成功提交到打印系统"
                    logger.info(msg)
                    self._result["status"] = PrintStatus.SUBMITTED
                    self._result["message"] = _("MainWindow","message_print_submitted")
                    self._event.set()

                elif state == PRINTABLE_STATE["JOB_STARTED"]:
                    logger.debug(f"🖨️ 打印任务 '{self.job_name}' 开始渲染")

                elif state == PRINTABLE_STATE["JOB_ABORTED"]:
                    logger.warning(f"⚠️ 打印任务 '{self.job_name}' 被用户取消")
                    self._result["status"] = PrintStatus.CANCEL
                    self._result["message"] = _("MainWindow","message_print_cancelled")
                    self._event.set()

                elif state in (
                    PRINTABLE_STATE["JOB_FAILED"],
                    PRINTABLE_STATE["JOB_SPOOLING_FAILED"],
                ):
                    logger.error(f"❌ 打印任务 '{self.job_name}' 失败 (状态值: {state})")
                    self._result["status"] = PrintStatus.FAILED
                    self._result["message"] = _("MainWindow","message_print_failed")
                    self._event.set()

            def disposing(inner_self, event_obj):
                logger.debug(f"🧹 监听器释放: {self.job_name}")

            def getTypes(inner_self):
                return (XPrintJobListener,)

            def getImplementationId(inner_self):
                return b""

        return PrintJobListenerImpl()

    def wait_for_result(self, timeout: int = 60) -> dict:
        if self._event.wait(timeout=timeout):
            return self._result.copy()
        else:
            logger.warning(f"⏰ 打印监听超时 ({timeout}s): {self.job_name}")
            return {"status": PrintStatus.TIMEOUT, "message": _("MainWindow","messgae_print_timeout")}

    @property
    def result(self) -> dict:
        return self._result.copy()