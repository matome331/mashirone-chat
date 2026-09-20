@echo off
setlocal
chcp 65001 > nul

set "BASE_DIR=%~dp0"
cd /d "%BASE_DIR%"

title ミミィチャット検索 - 更新ツール

call :check_environment
if errorlevel 1 goto :fatal

:menu
cls
echo ======================================================
echo    ミミィチャット検索 - コメントログ更新ツール
echo ======================================================
echo.
echo  1. 通常更新
echo     最新側だけ確認して、新しい配信を最大10本収集
echo.
echo  2. 全件棚卸し
echo     古い取りこぼしも含めてチャンネル全件を確認
echo.
echo  3. 1配信だけ再取得
echo     YouTube URL または動画IDを指定して取り直す
echo.
echo  4. 失敗動画台帳を見る
echo.
echo  5. 終了
echo.
set /p "choice=選択 (1-5): "

if "%choice%"=="1" goto :normal_update
if "%choice%"=="2" goto :full_scan
if "%choice%"=="3" goto :single_video
if "%choice%"=="4" goto :show_failures
if "%choice%"=="5" goto :eof

echo.
echo [!] 1～5を入力してください。
pause
goto :menu

:normal_update
cls
echo ======================================================
echo  通常更新
echo ======================================================
echo.
call %PYTHON_CMD% scripts\collect_chats.py --limit 10 --sleep 5
set "RUN_RESULT=%ERRORLEVEL%"
call :show_result %RUN_RESULT%
goto :menu

:full_scan
cls
echo ======================================================
echo  全件棚卸し
echo ======================================================
echo.
echo チャンネル全件を確認します。
echo 通常更新より時間がかかります。
echo.
set /p "confirm=実行しますか？ (y/N): "
if /I not "%confirm%"=="y" goto :menu

call %PYTHON_CMD% scripts\collect_chats.py --full-scan --limit 0 --sleep 5
set "RUN_RESULT=%ERRORLEVEL%"
call :show_result %RUN_RESULT%
goto :menu

:single_video
cls
echo ======================================================
echo  1配信だけ再取得
echo ======================================================
echo.
echo YouTube URL または11文字の動画IDを入力してください。
echo.
set /p "video_ref=URL / 動画ID: "
if "%video_ref%"=="" (
    echo.
    echo [!] 入力が空です。
    pause
    goto :menu
)

call %PYTHON_CMD% scripts\collect_chats.py --video "%video_ref%"
set "RUN_RESULT=%ERRORLEVEL%"
call :show_result %RUN_RESULT%
goto :menu

:show_failures
cls
call %PYTHON_CMD% scripts\collect_chats.py --show-failures
echo.
pause
goto :menu

:check_environment
where python > nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=python"
    goto :check_ytdlp
)

where py > nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=py -3"
    goto :check_ytdlp
)

echo [ERROR] Python が見つかりません。
echo Python 3 をインストールしてから再実行してください。
exit /b 1

:check_ytdlp
call %PYTHON_CMD% -m yt_dlp --version > nul 2>&1
if not errorlevel 1 exit /b 0

echo [!] yt-dlp がPython環境に見つかりません。
echo.
set /p "install_ytdlp=今インストールしますか？ (y/N): "
if /I not "%install_ytdlp%"=="y" (
    echo.
    echo 次のコマンドでインストールできます:
    echo   %PYTHON_CMD% -m pip install -U yt-dlp
    exit /b 1
)

echo.
echo yt-dlp をインストール中...
call %PYTHON_CMD% -m pip install -U yt-dlp
if errorlevel 1 (
    echo.
    echo [ERROR] yt-dlp のインストールに失敗しました。
    exit /b 1
)

call %PYTHON_CMD% -m yt_dlp --version > nul 2>&1
if errorlevel 1 (
    echo.
    echo [ERROR] yt-dlp をインストールしましたが、Pythonから読み込めません。
    exit /b 1
)

exit /b 0

:show_result
echo.
if "%~1"=="0" (
    echo ======================================================
    echo  完了しました。
    echo ======================================================
) else (
    echo ======================================================
    echo  [!] エラー終了しました。上の内容を確認してください。
    echo  失敗動画は可能な範囲で台帳に記録されます。
    echo ======================================================
)
echo.
pause
exit /b 0

:fatal
echo.
pause
exit /b 1
