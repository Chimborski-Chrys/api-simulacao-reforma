@echo off
echo Iniciando backend Simulador IBS/CBS...
cd /d "%~dp0"
.venv\Scripts\uvicorn main:app --reload --host 0.0.0.0 --port 8000
