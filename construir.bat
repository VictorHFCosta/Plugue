@echo off
rem Recria dist\Plugue.exe a partir do codigo-fonte (precisa do Python instalado)
rem e, se o Inno Setup 6 estiver instalado, tambem o instalador dist\PlugueSetup.exe.
cd /d "%~dp0"
if not exist .venv python -m venv .venv
.venv\Scripts\python -m pip install --quiet -r requirements.txt pyinstaller
.venv\Scripts\python -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name Plugue --collect-all customtkinter ^
    --workpath build --specpath build app.py
if errorlevel 1 goto fim

set "ISCC="
for %%P in ("%LOCALAPPDATA%\Programs\Inno Setup 6" "%ProgramFiles(x86)%\Inno Setup 6" "%ProgramFiles%\Inno Setup 6") do if exist "%%~P\ISCC.exe" set "ISCC=%%~P\ISCC.exe"
if not defined ISCC (
    echo.
    echo Inno Setup 6 nao encontrado: so o dist\Plugue.exe foi gerado.
    echo Para gerar o instalador: winget install JRSoftware.InnoSetup
    goto fim
)
"%ISCC%" /Q instalador.iss
if errorlevel 1 goto fim
echo.
echo Pronto: dist\Plugue.exe e dist\PlugueSetup.exe

:fim
pause
