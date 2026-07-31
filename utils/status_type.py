# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from dataclasses import dataclass, field
from typing import Optional, Any
from enum import Enum
import time

# 1. 定义状态类型枚举
class StatusType(Enum):
    INFO = "info"       # 普通提示
    SUCCESS = "success" # 成功
    WARNING = "warning" # 警告
    ERROR = "error"     # 错误
    PROGRESS = "progress" # 进度更新

# 2. 定义统一的消息结构
@dataclass
class PrintStatusMessage:
    type: StatusType
    message: str
    details: Optional[str] = None      # 详细错误堆栈或额外信息
    progress: Optional[int] = None     # 0-100 的进度值
    timestamp: float = field(default_factory=lambda: time.time()) # 时间戳
    code: Optional[int] = None         # 错误代码

    def to_dict(self) -> dict:
        """转换为字典以便通过 signal 发送 (兼容 Qt 的信号槽机制)"""
        return {
            "type": self.type.value,
            "message": self.message,
            "details": self.details,
            "progress": self.progress,
            "code": self.code,
            "timestamp": self.timestamp
        }

# 启动引擎
msg_start_LO = PrintStatusMessage(
    type=StatusType.INFO, 
    # message="正在启动打印引擎...",
    message="initializing_printer"
)

# 打印成功
msg_start_LO_success = PrintStatusMessage(
    type=StatusType.SUCCESS, 
    # message="打印引擎就绪",
    message="printer_ready"
)

# 发生错误
msg_start_LO_error = PrintStatusMessage(
    type=StatusType.ERROR, 
    # message="无法启动打印引擎",
    message="printer_start_failed"
)

# 更新进度
msg_wait_LO_ready = PrintStatusMessage(
    type=StatusType.INFO, 
    # message="等待打印引擎就绪...", 
    message="waiting_for_printer"
)