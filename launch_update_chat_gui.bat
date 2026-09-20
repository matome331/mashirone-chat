@echo off
setlocal
chcp 65001 > nul

set "BASE_DIR=%~dp0"
cd /d "%BASE_DIR%"

set "PYTHON_CMD="
where python > nul 2>&1
if not errorlevel 1 set "PYTHON_CMD=python"

if not defined PYTHON_CMD (
    where py > nul 2>&1
    if not errorlevel 1 set "PYTHON_CMD=py -3"
)

if not defined PYTHON_CMD (
    echo [ERROR] Python 3 が見つかりません。
    echo update_chat.bat を使うか、Python 3 をインストールしてください。
    echo.
    pause
    exit /b 1
)

call %PYTHON_CMD% -c "import tkinter" > nul 2>&1
if errorlevel 1 (
    echo [ERROR] Tkinter が利用できません。
    echo Windows公式Pythonでは通常Tkinterが含まれています。
    echo 非GUI版の update_chat.bat はそのまま利用できます。
    echo.
    pause
    exit /b 1
)

set "PYTHONW="
for /f "delims=" %%I in ('%PYTHON_CMD% -c "import os,sys; print(os.path.join(os.path.dirname(sys.executable), 'pythonw.exe'))"') do set "PYTHONW=%%I"

if defined PYTHONW if exist "%PYTHONW%" (
    start "" "%PYTHONW%" "%BASE_DIR%update_chat_gui.py"
    exit /b 0
)

start "" %PYTHON_CMD% "%BASE_DIR%update_chat_gui.py"
exit /b 0
