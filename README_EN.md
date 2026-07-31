English | [简体中文](README.md)

# LibreOffice Batch Printing & UNO Extension Plugin

## 1. Project Overview

This project provides an automated document processing solution tailored for the Linux platform. It consists of two core components:
- **Standalone GUI Application**: Built with PySide6, it leverages the UNO API to invoke the office software kernel for batch printing tasks.
- **Office Extension Plugin (`.oxt`)**: Deeply integrated into the office software, it provides menu entries and quick actions, while seamlessly dispatching the standalone application in the background to execute printing tasks.

### Project Structure
```text
project-root/
├── run.sh                # Standalone app launcher (auto-configures UNO runtime environment)
├── main.py               # Main application entry point
├── services/             # Core batch printing logic
├── ui/                   # PySide6 UI files
└── plugin-oxt/           # Office extension plugin source code
```

---

## 2. Environment Adaptation & Path Configuration

This project natively supports both LibreOffice and LoongOffice. Since their underlying UNO APIs and directory structures are highly consistent, **no Python business code modifications are required** when switching between them; you only need to configure the correct path in `run.sh`.

| Office Software | Default Path (`$OFFICE_HOME`) | Notes |
| :--- | :--- | :--- |
| **LibreOffice** | `/usr/lib/libreoffice/program` | Default path for mainstream Linux distros |
| **LoongOffice** | `/opt/loongoffice/program` | Default path for Loongson platforms |

> **Note**: If your installation path differs from the defaults above, please replace the path with your actual installation path when executing the subsequent scripts.

---

## 3. Build & Deployment Guide

We highly recommend using a **Python Virtual Environment** for development isolation and **PyInstaller** to generate standalone executables.

### 3.1 Create & Configure Virtual Environment
Using a virtual environment is strongly recommended to avoid package conflicts.

```bash
# 1. Create virtual environment
python3 -m venv venv

# 2. Activate virtual environment
source venv/bin/activate

# 3. Install dependencies
pip install pyinstaller cups PySide6 PyMuPDF python-magic
```

### 3.2 Package as Executable (PyInstaller)
Use PyInstaller to package the application into a standalone executable.

```bash
# 1. Clean old builds
rm -rf dist/ build/ *.spec

# 2. Execute packaging command
pyinstaller \
--name=lobatchprint \
--windowed \
--add-data "locales:locales" \
--add-data "fonts:fonts" \
main.py
```

### 3.3 Office Extension Plugin (OXT) Build & Installation
The plugin dispatches the standalone application via `subprocess.Popen`, using `start_new_session=True` to ensure background tasks continue running independently even after the office software is closed.

#### 1. Configure Standalone App Path
Before packaging the `.oxt` file, open `plugin-oxt/config.py` and modify the `APP_PATH` variable to point to your actual deployed standalone application launcher script:

```python
# plugin-oxt/config.py
APP_PATH = "/usr/lib/libreoffice/program/lobatchprint"
```

#### 2. Package & Install
1. Execute the following command in the `plugin-oxt/` directory to generate the extension file:
   ```bash
   zip -rq ../batchprintextension.oxt *
   ```
2. In the office software, navigate to `Tools -> Extension Manager -> Add` to install the `.oxt` file. Restart the software for changes to take effect.

### 3.4 Launcher Script Configuration & Runtime Principles

To ensure the standalone application loads the UNO interface correctly, the `run.sh` launcher script must be configured to inject the necessary environment variables.

#### Configuration Steps
Open `run.sh` in the project root and **modify the `OFFICE_HOME` variable** according to your actual installation environment:

```bash
# Modify based on your actual environment
OFFICE_HOME="/usr/lib/libreoffice/program"
```

#### Runtime Principles
The `run.sh` script injects the following critical environment variables to ensure the application correctly loads the office software's built-in UNO runtime:
- **`URE_BOOTSTRAP`**: Points to the `fundamentalrc` configuration file to bootstrap the UNO engine.
- **`LD_LIBRARY_PATH`**: Specifies the search path for underlying C++ dynamic libraries.
- **`PYTHONPATH`**: Forces the path to the office software's built-in `uno.py`, preventing conflicts with system-wide pip-installed versions.

Additionally, the script automatically detects and prioritizes the office software's built-in Python version. If not found, it gracefully falls back to the system's default `python3`, ensuring that `import uno` executes correctly.

---

## License

This project is open-sourced under the **Mozilla Public License 2.0 (MPL 2.0)**.
For more details, please refer to the [LICENSE](./LICENSE) file in the project root directory.

---