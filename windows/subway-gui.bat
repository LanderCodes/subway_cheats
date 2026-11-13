@echo off
setlocal
cd /d "%~dp0"
where pyw >nul 2>nul
if %errorlevel%==0 (
    pyw -3 subway_gui_tk.py %*
    goto :eof
)
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 subway_gui_tk.py %*
) else (
    python subway_gui_tk.py %*
)
