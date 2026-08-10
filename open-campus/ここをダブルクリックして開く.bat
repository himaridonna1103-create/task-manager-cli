@echo off
cd /d "%~dp0"
start "" cmd /c "timeout /t 1 >nul & start http://localhost:8932/index.html"
python -m http.server 8932
