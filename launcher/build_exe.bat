@echo off
rem Simple ASCII wrapper: all build logic lives in build.py
cd /d "%~dp0"
echo === YroveeLauncher build ===
where py >nul 2>&1 && (py -3 build.py & goto end)
where python >nul 2>&1 && (python build.py & goto end)
echo Python not found. Install from python.org (check "Add to PATH") and run again.
pause
exit /b 1
:end
if errorlevel 1 (
  echo BUILD FAILED - see messages above.
  pause
  exit /b 1
)
echo.
echo You can close this window.
pause
