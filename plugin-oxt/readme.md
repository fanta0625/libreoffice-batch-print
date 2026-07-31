# 安装 LibreOffice 的 Python 脚本支持包
sudo apt install libreoffice-script-provider-python
# 项目打包成oxt扩展
zip -r ./BatchPrintExtension.oxt . -x ".git/*"
