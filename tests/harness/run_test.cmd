@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "PYTHON_EXE=%SCRIPT_DIR%..\..\.venv\Scripts\python.exe"
set "PY_SCRIPT=%SCRIPT_DIR%run_test.py"

if not exist "%PY_SCRIPT%" (
    echo ERROR: Harness script not found: "%PY_SCRIPT%"
    exit /b 1
)

if exist "%PYTHON_EXE%" (
    "%PYTHON_EXE%" "%PY_SCRIPT%" %*
    exit /b %ERRORLEVEL%
)

where python >nul 2>nul
if errorlevel 1 (
    echo ERROR: Python not found. Install Python or create .venv at "%SCRIPT_DIR%..\..\.venv".
    exit /b 1
)

python "%PY_SCRIPT%" %*
exit /b %ERRORLEVEL%
