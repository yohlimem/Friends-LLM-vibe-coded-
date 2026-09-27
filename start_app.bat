@echo off
set PYTHONIOENCODING=utf-8
title WhatsApp Persona AI Studio Launcher
echo =======================================================
echo     WhatsApp Persona AI Fine-Tuner for RTX 4080 Super
echo =======================================================
echo.

set CONDA_ENV_PYTHON=C:\Users\yahli\anaconda3\envs\whatsapp_ai\python.exe

if exist "%CONDA_ENV_PYTHON%" (
    echo [INFO] Found Conda environment 'whatsapp_ai'.
) else (
    echo [WARNING] Conda environment 'whatsapp_ai' not found at %CONDA_ENV_PYTHON%.
    echo Using fallback system python...
    set CONDA_ENV_PYTHON=python
)

echo.
echo [INFO] Starting FastAPI Web Server at http://localhost:8000 ...
echo [INFO] Press Ctrl+C in this window to stop the server.
echo.

"%CONDA_ENV_PYTHON%" -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload

pause
