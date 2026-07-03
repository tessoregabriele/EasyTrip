@echo off
REM Script di avvio completo EasyTrip (backend + frontend)
REM 1. Avvia il database Docker
REM 2. Avvia il server Django in una finestra separata
REM 3. Avvia il dev server Vite (frontend) in un'altra finestra separata

cd /d "%~dp0"

echo === Avvio database Docker ===
cd /d "%~dp0easytrip-backend"
docker compose up -d

echo === Avvio server Django ===
start "EasyTripServer" cmd /k "venv\Scripts\activate.bat && python manage.py runserver"

echo === Avvio frontend Vite ===
cd /d "%~dp0easytrip-frontend"
start "EasyTripFrontend" cmd /k "npm run dev"

cd /d "%~dp0"

echo.
echo Tutto avviato:
echo   Backend:  http://localhost:8000
echo   Frontend: http://localhost:3000
pause
