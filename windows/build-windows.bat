@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
    set "PY=py -3"
) else (
    set "PY=python"
)

%PY% -m pip install --upgrade pip
%PY% -m pip install -r requirements.txt
if errorlevel 1 goto :error

%PY% -m PyInstaller --noconfirm --clean subway.spec
if errorlevel 1 goto :error

echo.
echo Build complete:
echo   dist\subway.exe      (CLI)
echo   dist\subway-gui.exe  (GUI)
goto :eof

:error
echo.
echo Build failed.
exit /b 1
