@echo off
setlocal
title YouTube Latam Dub - Servidor local
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Primero ejecuta install.bat para preparar este proyecto.
  pause
  exit /b 1
)
echo Servidor local: http://127.0.0.1:8000
echo Mantene esta ventana abierta mientras usas el doblaje.
".venv\Scripts\python.exe" backend\server.py
if errorlevel 1 echo No se pudo iniciar. Comprueba que no haya otro servidor en el puerto 8000.
pause
