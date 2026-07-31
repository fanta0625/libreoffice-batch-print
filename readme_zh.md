# LibreOffice 批量打印与 UNO 扩展插件

## 1. 项目介绍

本项目旨在提供一套针对 Linux 平台的文档自动化处理解决方案，包含两个核心组件：
- **独立 GUI 应用**：基于 PySide6 构建，通过 UNO API 调用办公软件内核执行批量打印任务。
- **办公软件扩展插件 (`.oxt`)**：深度集成于办公软件内部，提供菜单入口与快捷操作，并在底层自动调度独立应用实现打印任务。

### 项目主要结构
```text
project-root/
├── run.sh                # 独立应用启动脚本 (自动配置 UNO 运行时环境)
├── main.py               # 主程序入口
├── services/             # 批量打印核心逻辑
├── ui/                   # PySide6 界面文件
└── plugin-oxt/           # 办公软件插件源码
```

---

## 2. 环境适配与路径说明

本项目同时支持 LibreOffice 与 LoongOffice。由于两者底层 UNO API 及目录结构高度一致，切换办公软件时**无需改动任何 Python 业务代码**，仅需在 `run.sh` 中配置正确的路径。

| 办公软件 | 默认安装路径 (`$OFFICE_HOME`) | 备注 |
| :--- | :--- | :--- |
| **LibreOffice** | `/usr/lib/libreoffice/program` | 主流 Linux 发行版默认路径 |
| **LoongOffice** | `/opt/loongoffice/program` | 龙芯平台默认安装路径 |

> **提示**：若您的安装路径与上述默认路径不同，请在执行后续脚本时，将路径替换为实际安装路径。

---

## 3. 构建部署指南

本项目推荐使用 **Python 虚拟环境** 进行开发隔离，并使用 **PyInstaller** 生成可执行文件。

### 3.1 创建与配置虚拟环境
强烈建议使用虚拟环境以避免包冲突。

```bash
# 1. 创建虚拟环境
python3 -m venv venv

# 2. 激活虚拟环境
source venv/bin/activate

# 3. 安装依赖
# 注意：PyMuPDF 已包含底层 mupdf 绑定，无需单独安装 fitz 或 mupdf
pip install pyinstaller cups PySide6 PyMuPDF python-magic
```

### 3.2 打包为可执行程序 (PyInstaller)
使用 PyInstaller 将应用打包为独立的可执行文件。

```bash
# 1. 清理旧构建
rm -rf dist/ build/ *.spec

# 2. 执行打包命令
pyinstaller \
--name=lobatchprint \
--windowed \
--add-data "locales:locales" \
--add-data "fonts:fonts" \
main.py
```

### 3.3 办公软件插件 (OXT) 构建与安装
插件通过 `subprocess.Popen` 调度独立应用，并设置 `start_new_session=True` 以确保后台任务在办公软件关闭后仍能独立运行。

#### 1. 配置独立应用路径
在打包 `.oxt` 文件之前，请打开 `plugin-oxt/config.py` 文件，修改 `APP_PATH` 变量，将其指向您实际部署的独立应用启动脚本：

```python
# plugin-oxt/config.py
APP_PATH = "/usr/lib/libreoffice/program/lobatchprint"
```

#### 2. 打包与安装
1. 在 `plugin-oxt/` 目录下执行 `zip -rq ../batchprintextension.oxt *` 生成扩展文件。
2. 在办公软件中通过 `工具 -> 扩展管理器 -> 添加` 安装该 `.oxt` 文件，重启后生效。

### 3.4 启动脚本配置与运行原理

为确保独立应用能正确加载 UNO 接口，需配置 `run.sh` 启动脚本以注入必要的环境变量。

#### 配置步骤
打开项目根目录下的 `run.sh`，根据您的实际安装环境，**修改 `OFFICE_HOME` 变量**：

```bash
# 根据实际环境修改
OFFICE_HOME="/usr/lib/libreoffice/program"
```

#### 运行原理
`run.sh` 脚本通过注入以下关键环境变量，确保应用能正确加载办公软件内置的 UNO 运行时：
- **`URE_BOOTSTRAP`**：指向 `fundamentalrc` 配置文件，引导 UNO 引擎启动。
- **`LD_LIBRARY_PATH`**：指定底层 C++ 动态库的搜索路径。
- **`PYTHONPATH`**：强制指向办公软件内置的 `uno.py`，避免与系统 pip 安装的版本冲突。

此外，脚本会自动检测办公软件内置的 Python 版本并优先使用，若未找到则回退到系统默认的 `python3`，从而保证 `import uno` 能够正确执行。

---

## License (开源许可)

本项目基于 **Mozilla Public License 2.0 (MPL 2.0)** 协议开源。
有关详细信息，请参阅项目根目录下的 [LICENSE](./LICENSE) 文件。