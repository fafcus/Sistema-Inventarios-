@echo off
setlocal
cd /d "%~dp0"

echo ==========================================
echo  Sistema de Inventarios - Instalador
echo ==========================================
echo.

if not exist "dist\\SistemaInventarios\\SistemaInventarios.exe" (
    echo No existe el EXE. Ejecutando compilacion...
    call build_exe.bat
    if errorlevel 1 goto :error
)

if not exist "%ProgramFiles(x86)%\\Inno Setup 6\\ISCC.exe" (
    if not exist "%ProgramFiles%\\Inno Setup 6\\ISCC.exe" (
        echo.
        echo ERROR: Inno Setup 6 no esta instalado.
        echo Instala Inno Setup y vuelve a ejecutar este archivo.
        goto :error
    )
)

set "ISCC=%ProgramFiles(x86)%\\Inno Setup 6\\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\\Inno Setup 6\\ISCC.exe"

echo Generando instalador...
"%ISCC%" "installer\\SistemaInventarios.iss"
if errorlevel 1 goto :error

echo.
echo Instalador generado en:
echo   installer_output\\SistemaInventarios-Setup-1.0.0.exe
echo.
pause
exit /b 0

:error
echo.
echo ERROR durante la generacion del instalador.
pause
exit /b 1
