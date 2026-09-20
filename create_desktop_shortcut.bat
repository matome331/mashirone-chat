@echo off
setlocal
chcp 65001 > nul

set "BASE_DIR=%~dp0"
set "TARGET=%BASE_DIR%update_chat.bat"

if not exist "%TARGET%" (
    echo [ERROR] update_chat.bat が見つかりません。
    echo このファイルをリポジトリ直下で実行してください。
    echo.
    pause
    exit /b 1
)

set "SHORTCUT_TARGET=%TARGET%"
set "SHORTCUT_WORKDIR=%BASE_DIR%"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$desktop=[Environment]::GetFolderPath('Desktop');" ^
  "$shell=New-Object -ComObject WScript.Shell;" ^
  "$path=Join-Path $desktop 'ミミィチャット検索 更新.lnk';" ^
  "$shortcut=$shell.CreateShortcut($path);" ^
  "$shortcut.TargetPath=$env:SHORTCUT_TARGET;" ^
  "$shortcut.WorkingDirectory=$env:SHORTCUT_WORKDIR;" ^
  "$shortcut.Description='ミミィチャット検索 コメントログ更新';" ^
  "$shortcut.Save();" ^
  "Write-Host ('作成しました: ' + $path)"

if errorlevel 1 (
    echo.
    echo [ERROR] ショートカットの作成に失敗しました。
    pause
    exit /b 1
)

echo.
echo デスクトップに「ミミィチャット検索 更新」を作成しました。
echo.
pause
