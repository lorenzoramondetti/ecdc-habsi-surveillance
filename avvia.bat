@echo off
title ECDC HA-BSI Surveillance & Benchmark AI
cd /d "%~dp0"

echo ===================================================================
echo     ECDC HA-BSI Surveillance & Benchmark AI Platform
echo     Deterministic Algorithm - ECDC PPS Protocol (ECDC/2025/LVP/0005)
echo ===================================================================
echo.

:: 1. Check Python installation
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [CRITICAL ERROR] Python was not detected in system PATH.
    echo Please ensure Python 3.10+ is installed with "Add to PATH" checked.
    echo.
    pause
    exit /b 1
)

:: 2. Check local Ollama daemon
echo [*] Verifying Ollama service status...
curl -s http://127.0.0.1:11434/api/tags >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [!] Ollama service not detected.
    echo     Attempting to start Ollama daemon in background...
    where ollama >nul 2>&1
    if %ERRORLEVEL% EQU 0 (
        start "" ollama serve
    ) else if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" (
        start "" "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" serve
    ) else (
        echo [WARNING] Ollama executable not found automatically.
        echo          Please start Ollama manually before running inferences.
    )
    timeout /t 3 /nobreak >nul
) else (
    echo [OK] Ollama service active and ready.
)

:: 3. Launch browser and web server
echo.
echo [*] Launching Web Control Dashboard on: http://127.0.0.1:5050
echo [*] Automatically opening your browser...
echo.
echo Press Ctrl+C in this console to stop the server.
echo -------------------------------------------------------------------

start "" cmd /c "timeout /t 2 /nobreak >nul && start http://127.0.0.1:5050"

python run_pipeline.py --ui

pause
