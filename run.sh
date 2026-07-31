#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

OFFICE_HOME="/usr/lib/libreoffice/program"
# OFFICE_HOME="/opt/loongoffice/program"

export LBP_LO_EXECUTABLE="$OFFICE_HOME/soffice" 
# 设置 UNO 运行时配置
export URE_BOOTSTRAP="file://$OFFICE_HOME/fundamentalrc"

# 设置共享库路径（C++ 扩展）
export LD_LIBRARY_PATH="$OFFICE_HOME:$OFFICE_HOME/ure/lib:$LD_LIBRARY_PATH"

# 设置 Python 模块路径（让 import uno 能找到 uno.py）
export PYTHONPATH="$OFFICE_HOME:$PYTHONPATH"

# 确定 Python 版本
PYCACHE_UNO="$OFFICE_HOME/__pycache__/uno.cpython-*.pyc"
PYTHON_CMD="python3"
if ls $PYCACHE_UNO 1> /dev/null 2>&1; then
    PY_VER=$(ls $PYCACHE_UNO | grep -o 'cpython-[0-9]*' | head -1 | cut -d'-' -f2)
    if [[ ${#PY_VER} -ge 3 ]]; then
        MAJOR="${PY_VER:0:1}"
        MINOR="${PY_VER:1:2}"
        REQUIRED_PYTHON="python${MAJOR}.${MINOR}"
        if command -v "$REQUIRED_PYTHON" &> /dev/null; then
            PYTHON_CMD="$REQUIRED_PYTHON"
        else
            echo "⚠️  未找到 $REQUIRED_PYTHON，回退到 python3"
        fi
    fi
fi

# 启动
exec "$PYTHON_CMD" "$SCRIPT_DIR/main.py" "$@"