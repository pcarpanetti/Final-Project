@echo off
title RiskWatch
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 launch.py %*
) else (
  where python >nul 2>nul
  if errorlevel 1 (
    echo Python was not found. Install it from https://www.python.org/downloads/
    echo During setup, tick "Add python.exe to PATH". Then double-click start.bat again.
    pause
    exit /b 1
  )
  python launch.py %*
)
if errorlevel 1 pause
