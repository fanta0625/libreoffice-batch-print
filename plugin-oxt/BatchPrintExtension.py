# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import unohelper
import sys
import os
import subprocess
import urllib.parse
from com.sun.star.task import XJobExecutor
import config

class BatchPrintExtension(unohelper.Base, XJobExecutor):
    def __init__(self, ctx):
        self.ctx = ctx

    def _show_message(self, title, message, msg_type=0, buttons=1):
        """
        dialog func
        msg_type: 0=Info, 1=Warning, 2=Error, 3=Query
        buttons: 1=OK, 2=OK_Cancel, 3=Yes_No, 4=Yes_No_Cancel
        """
        try:
            toolkit = self.ctx.ServiceManager.createInstanceWithContext(
                "com.sun.star.awt.Toolkit", self.ctx)
            
            desktop = self.ctx.ServiceManager.createInstanceWithContext(
                "com.sun.star.frame.Desktop", self.ctx)
            frame = desktop.getCurrentFrame()
            parent_window = frame.getContainerWindow() if frame else None

            # 直接传入整数，LO 内部会自动识别
            box = toolkit.createMessageBox(
                parent_window, 
                msg_type, 
                buttons, 
                title, 
                message
            )
            
            return box.execute()
            
        except Exception as e:
            print(f"[BatchPrint] 弹窗失败: {e}")
            return 0

    def trigger(self, args):
        try:
            desktop = self.ctx.ServiceManager.createInstanceWithContext(
                "com.sun.star.frame.Desktop", self.ctx)
            
            current_component = desktop.getCurrentComponent()
            file_path = None

            if current_component and hasattr(current_component, "getURL"):
                url = current_component.getURL()
                if url and url.startswith("file://"):
                    try:
                        parsed = urllib.parse.urlparse(url)
                        path = urllib.parse.unquote(parsed.path)
                        if os.name == 'nt' and path.startswith('/'):
                            path = path[1:]
                        
                        if os.path.exists(path):
                            file_path = path
                    except Exception as e:
                        print(f"[BatchPrint] 路径解析错误: {e}")
                        
                elif url and url.startswith("private:"):
                    ret = self._show_message(
                        "文档未保存", 
                        "当前文档尚未保存，无法进行批量打印。\n\n请先保存文档 (Ctrl+S)，然后再试。", 
                        1,  # MessageBoxType.WARNINGBOX
                        1   # MessageBoxButtons.BUTTONS_OK
                    )
                    return 
                else:
                    pass
            
            cmd = [config.APP_PATH]
            
            if file_path:
                cmd.append(file_path)
                print(f"[BatchPrint] 启动应用，携带文件: {file_path}")
            else:
                print("[BatchPrint] 启动应用 (无预加载文件)")

            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )

        except Exception as e:
            # 2 = ERRORBOX, 1 = BUTTONS_OK
            self._show_message(
                "Batch print error", 
                f"Start failed:\n{str(e)}", 
                2, 
                1
            )
            import traceback
            traceback.print_exc()

g_ImplementationHelper = unohelper.ImplementationHelper()
g_ImplementationHelper.addImplementation(
    BatchPrintExtension,
    "com.loongoffice.batchprint.BatchPrintExtension",
    ("com.sun.star.task.Job",),
)