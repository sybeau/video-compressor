@echo off
setlocal
chcp 65001 >nul 2>nul
set "PYTHONIOENCODING=utf-8"
title Video Compressor / Trimmer

set "SCRIPT=%~dp0video-compress.py"
if not exist "%SCRIPT%" (
    echo [ERROR] video-compress.py is missing from this folder.
    echo         Expected at: %SCRIPT%
    pause
    exit /b 1
)
if not exist "%~dp0bin\ffmpeg.exe" (
    echo [ERROR] bin\ffmpeg.exe is missing from this folder.
    pause
    exit /b 1
)

set "PY="
if exist "%~dp0runtime\python.exe" set "PY=%~dp0runtime\python.exe"
if not defined PY if exist "D:\python\python.exe" set "PY=D:\python\python.exe"
if not defined PY (
    for /f "delims=" %%i in ('where python 2^>nul ^| findstr /v /i "WindowsApps"') do (
        if not defined PY set "PY=%%i"
    )
)
if not defined PY (
    echo [ERROR] No Python runtime found.
    echo         The bundled runtime folder is missing.
    echo         Re-extract the whole folder, including the "runtime" sub-folder.
    pause
    exit /b 1
)

"%PY%" "%SCRIPT%" %*

echo.
pause
