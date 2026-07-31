# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import os
import random
from config.settings import SUPPORTED_EXTENSIONS

class FileService:
    @staticmethod
    def get_file_type(file_path: str) -> str:
        ext = os.path.splitext(file_path)[1].lower()
        for f_type, exts in SUPPORTED_EXTENSIONS.items():
            if ext in exts:
                return f_type
        return 'Other'

    @staticmethod
    def mock_get_page_count(file_path: str) -> int:
        """模拟获取页数，实际项目中应替换为 UNO 调用"""
        return random.randint(1, 50)

    @staticmethod
    def scan_folder(folder_path: str) -> list:
        """扫描文件夹获取所有支持的文件"""
        files = []
        all_exts = []
        for exts in SUPPORTED_EXTENSIONS.values():
            all_exts.extend(exts)

        for root, _, filenames in os.walk(folder_path):
            for f in filenames:
                if any(f.lower().endswith(ext) for ext in all_exts):
                    files.append(os.path.join(root, f))
        return files
