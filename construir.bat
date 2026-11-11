@echo off
rem Recria dist\Plugue.exe a partir do codigo-fonte (precisa do Python instalado).
cd /d "%~dp0"
if not exist .venv python -m venv .venv
.venv\Scripts\python -m pip install --quiet -r requirements.txt pyinstaller
.venv\Scripts\python -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name Plugue --collect-all customtkinter ^
    --workpath build --specpath build app.py
echo.
echo Pronto: dist\Plugue.exe
pause
