@echo off
setlocal
cd /d "%~dp0"

echo ==========================================
echo  Sistema de Inventarios - Compilacion EXE
echo ==========================================
echo.

if not exist ".venv\\Scripts\\python.exe" (
    echo [1/4] Creando entorno virtual...
    py -m venv .venv
    if errorlevel 1 goto :error
)

echo [2/4] Instalando dependencias...
".venv\\Scripts\\python.exe" -m pip install --upgrade pip
".venv\\Scripts\\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo [3/4] Generando ejecutable...
".venv\\Scripts\\pyinstaller.exe" --noconfirm --clean --onedir --windowed --name "SistemaInventarios" --add-data "plantillas;plantillas" inicio.py
if errorlevel 1 goto :error

echo [4/4] Compilacion terminada.
echo.
echo Ejecutable:
echo   dist\\SistemaInventarios\\SistemaInventarios.exe
echo.
pause
exit /b 0

:error
echo.
echo ERROR durante la compilacion.
pause
exit /b 1
