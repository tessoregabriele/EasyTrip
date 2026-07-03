@echo off
REM Script di arresto completo EasyTrip (backend + frontend)
REM 1. Ferma il server Django (finestra "EasyTripServer")
REM 2. Ferma il dev server Vite del frontend (finestra "EasyTripFrontend")
REM 3. Ferma il database Docker (i dati restano nel volume)

echo === Arresto server Django ===
taskkill /FI "WINDOWTITLE eq EasyTripServer*" /T /F >nul 2>&1

echo === Arresto frontend Vite ===
taskkill /FI "WINDOWTITLE eq EasyTripFrontend*" /T /F >nul 2>&1

echo === Arresto database Docker ===
cd /d "%~dp0easytrip-backend"
docker compose down

cd /d "%~dp0"

echo.
echo Tutto fermato. I dati del database sono conservati nel volume Docker.
pause
