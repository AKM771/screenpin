@echo off
rem Build ScreenPin exe (this file is ASCII-only; keep it that way)
setlocal
set "SRC=%~dp0"
set "STAGE=D:\build_screenpin"
if not exist "%STAGE%" mkdir "%STAGE%"
copy /y "%SRC%overlay.py" "%STAGE%\" >nul
copy /y "%SRC%av_player.py" "%STAGE%\" >nul
copy /y "%SRC%pin.ico" "%STAGE%\" >nul
rem fail fast if any local module missing from stage (root cause of missing av_player in exe once)
if not exist "%STAGE%\overlay.py" ( echo STAGE MISSING overlay.py & exit /b 1 )
if not exist "%STAGE%\av_player.py" ( echo STAGE MISSING av_player.py & exit /b 1 )
pushd "%STAGE%"
pyinstaller --onefile --noconsole --name screenpin --icon pin.ico --add-data "pin.ico;." --collect-all av --clean overlay.py
if errorlevel 1 (
  popd
  echo BUILD FAILED
  exit /b 1
)
if not exist "%STAGE%\dist\screenpin.exe" ( popd & echo BUILD OUTPUT MISSING & exit /b 1 )
copy /y "%STAGE%\dist\screenpin.exe" "%SRC%screenpin.exe" >nul
if errorlevel 1 (
  popd
  echo COPY FAILED - screenpin.exe may be RUNNING, close it and rebuild
  exit /b 1
)
popd
echo BUILD OK - copy verified
