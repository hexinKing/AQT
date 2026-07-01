@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [AQT] 创建虚拟环境...
    python -m venv .venv
    echo [AQT] 安装依赖...
    .venv\Scripts\python.exe -m pip install -r requirements.txt -q
)

echo [AQT] 启动服务...
.venv\Scripts\python.exe run.py
pause
