# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import sys
import os
import resources_rc
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QLocale
from PySide6.QtGui import QIcon,QImage,QPixmap
from utils.i18n import translator

# 确保能导入本地模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
env_python_path = os.environ.get('PYTHONPATH', '')
# 插入python环境变量
if env_python_path:
    paths = env_python_path.split(os.pathsep)
    for path in reversed(paths):
        if path and path not in sys.path:
            sys.path.insert(0, path)
else:
    print("DEBUG: No external PYTHONPATH set, using embedded paths.")

from services.uno_connect_service import lo_service
from ui.main_window import MainWindow
from config.settings import STYLESHEET

from log.logger import get_logger

app_logger = get_logger("main")

def main():
    # 环境变量修复 (Linux)
    if os.name != 'nt' and not os.environ.get("XDG_RUNTIME_DIR"):
        user = os.getenv('USER', 'root')
        runtime_dir = f"/tmp/runtime-{user}"
        os.environ["XDG_RUNTIME_DIR"] = runtime_dir
        os.makedirs(runtime_dir, exist_ok=True)

    app = QApplication(sys.argv)
    
    # 初始化翻译器
    translator.set_application(app)
    
    # 根据系统语言设置初始语言
    system_locale = QLocale.system().name()
    if system_locale.startswith('zh_CN'):
        translator.set_language('zh_CN')
    else:
        translator.set_language('en_US')
    
    # 设置图标
    pixmap = QPixmap(":/images/resources/logo.png")
    app.setWindowIcon(QIcon(pixmap))

    app.setStyle("Breeze")
    initial_files = [
        f for f in sys.argv[1:]
        if f not in {'%F', '%f', '%U', '%u'} and os.path.isfile(f)
    ] 

    # 如果有文件参数，尝试发送给已运行的实例
    if initial_files:
        app_logger.info(f"initial_files:{initial_files}")
        if lo_service.send_files_to_instance(initial_files):
            app_logger.info("✅ Files sent to running instance, exiting.")
            sys.exit(0)

    # 启动 IPC 服务
    if not lo_service.start_ipc_server():
        app_logger.warning("⚠️ Warning: IPC service startup failed, may already have instance.")
        sys.exit(0)

     # 创建主窗口
    window = MainWindow()
    
    # 连接信号：当收到外部文件时，添加到列表
    lo_service.files_received.connect(window.add_files_from_external)
    
    # 如果有初始文件，直接添加
    if initial_files:
        window.add_files_from_external(initial_files)
        
    window.show()
    
    # 注册退出清理
    import atexit
    def on_exit():
        lo_service.shutdown()
    atexit.register(on_exit)
    exit_code = app.exec()
    app_logger.info(f"Application exit, exit_code: {exit_code}")
    sys.exit(exit_code)

if __name__ == "__main__":
    main()