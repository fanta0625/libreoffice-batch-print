# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

# utils.py
import os
import sys

def get_port(env_name: str, default: int) -> int:
    """
    安全地从环境变量获取端口号
    """
    val = os.environ.get(env_name)
    if val is None:
        return default
    try:
        port = int(val)
        if not (1 <= port <= 65535):
            raise ValueError("端口超出有效范围 (1-65535)")
        return port
    except ValueError:
        print(f"环境变量 {env_name}={val} 无效，使用默认端口 {default}", file=sys.stderr)
        return default

def get_executable_path() -> str:
    """
    确定可执行文件路径。
    """
    env_path = os.environ.get("LBP_LO_EXECUTABLE")
    if env_path and os.path.exists(env_path):
        return env_path
    
    # 常见安装路径
    common_paths = [
        "/usr/lib/libreoffice/program/soffice",
        "/opt/loongoffice/program/soffice",
        "/usr/bin/soffice",
    ]
    for path in common_paths:
        if os.path.exists(path):
            return path
    
    # 若都找不到，回退到默认
    return common_paths[0]