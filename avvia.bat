@echo off
cd /d "%~dp0"
echo Avvio di Gestionale Angeleri in corso...
venv\Scripts\python.exe main.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ========================================================
    echo Si e' verificato un problema durante l'avvio.
    echo ========================================================
    echo.
    pause
)
