@echo off
title AI Video Automation Suite
cls
echo ==============================================================
echo    🎬 AI Video Automation Suite
echo    Iniciando servidor web en http://localhost:8000 ...
echo ==============================================================
echo.
python run.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] No se pudo iniciar el servidor.
    echo Asegúrate de tener instaladas las dependencias:
    echo   pip install -r requirements.txt
    echo.
    pause
)
