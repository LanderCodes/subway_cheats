@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 ..\subway_tool.py %*
) else (
    python ..\subway_tool.py %*
)
