@echo off
title 屏幕贴图 - 重置程序
echo ============================================
echo   屏幕贴图 重置程序
echo ============================================
echo.
echo 本脚本只删除配置文件：
echo   %LOCALAPPDATA%\ScreenPin\config.json
echo 程序文件本身不受影响，下次打开恢复默认设置。
echo.
echo 注意：请先退出屏幕贴图（托盘图标右键-退出）再运行，
echo 否则程序退出时会把旧设置重新写回去。
echo.
tasklist /fi "imagename eq screenpin.exe" 2>nul | find /i "screenpin.exe" >nul
if not errorlevel 1 (
    echo [警告] 检测到屏幕贴图正在运行，请先退出后再运行本脚本。
    echo.
    pause
    exit /b 1
)
set /p OK=确认重置？输入 y 回车继续，其它键取消：
if /i not "%OK%"=="y" (
    echo 已取消。
    pause
    exit /b 0
)
del /f /q "%LOCALAPPDATA%\ScreenPin\config.json" 2>nul
if exist "%LOCALAPPDATA%\ScreenPin\config.json" (
    echo [失败] 配置文件删除失败，请检查权限。
) else (
    echo [完成] 已重置。下次打开屏幕贴图将从默认设置开始。
)
echo.
pause
