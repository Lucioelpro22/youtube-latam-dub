@echo off
setlocal
cd /d "%~dp0"
echo Instalando YouTube Latam Dub...
where python >nul 2>nul
if errorlevel 1 (
  py -3 scripts\install.py
) else (
  python scripts\install.py
)
if errorlevel 1 (
  echo.
  echo No se completo la instalacion. Revisa el mensaje anterior.
) else (
  echo.
  echo Listo. Ahora ejecuta run_server.bat.
)
pause
