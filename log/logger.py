# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

# logger.py
import logging
import logging.handlers
import os
from pathlib import Path

# 定义日志级别
LOG_LEVEL = logging.INFO  # 可设为 DEBUG, INFO, WARNING, ERROR, CRITICAL

# 确定日志文件存放目录
# 对于 Windows，通常放在 %APPDATA%；对于 Linux/macOS，放在 ~/.config/
if os.name == 'nt':  # Windows
    log_dir = Path(os.getenv('APPDATA')) / 'libreofficebatchprint'
else:  # Linux/macOS
    log_dir = Path.home() / '.config' / 'libreofficebatchprint'

log_dir.mkdir(parents=True, exist_ok=True)
log_file_path = log_dir / 'libreofficebatchprint.log'

# 创建格式化器
formatter = logging.Formatter(
    fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# 创建处理器
console_handler = logging.StreamHandler()
console_handler.setLevel(LOG_LEVEL)
console_handler.setFormatter(formatter)


# 文件处理器 - 按天轮转
from logging.handlers import TimedRotatingFileHandler

# 文件处理器，并最多保留7个旧文件。
file_handler = TimedRotatingFileHandler(
    filename=log_file_path,
    when='midnight', 
    interval=1,
    backupCount=7,
    encoding='utf-8'
)
file_handler.setLevel(LOG_LEVEL)
file_handler.setFormatter(formatter)

# 让轮转后的文件名格式为 .YYYY-MM-DD
file_handler.suffix = "%Y-%m-%d"

# 删除旧日志时也匹配这个后缀
import re
file_handler.extMatch = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# 获取或创建根日志记录器
logger = logging.getLogger('LBP')
logger.setLevel(LOG_LEVEL)
logger.addHandler(console_handler)
logger.addHandler(file_handler)
logger.propagate = False 

# 便捷函数，供其他模块直接导入使用
def get_logger(name: str = None):
    """获取一个子日志记录器"""
    if name:
        return logger.getChild(name)
    return logger