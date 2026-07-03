@echo off
REM Setup completo di EasyTrip al primo avvio su una macchina nuova.
REM Da eseguire una sola volta dopo il clone della repo.
REM Richiede: Python 3.11+, Node.js 18+, Docker.

setlocal
cd /d "%~dp0"

echo ============================================
echo   EasyTrip - Setup iniziale
echo ============================================
echo.

where docker >nul 2>&1
if errorlevel 1 (
    echo [ERRORE] Docker non trovato nel PATH. Installalo e riprova.
    goto :error
)
where python >nul 2>&1
if errorlevel 1 (
    echo [ERRORE] Python non trovato nel PATH. Installalo e riprova.
    goto :error
)
where npm >nul 2>&1
if errorlevel 1 (
    echo [ERRORE] Node.js/npm non trovato nel PATH. Installalo e riprova.
    goto :error
)

echo === 1. Avvio database Docker (PostgreSQL + pgvector) ===
cd /d "%~dp0easytrip-backend"
docker compose up -d
if errorlevel 1 goto :error

echo.
echo === 2. Creazione virtualenv Python ===
if not exist venv (
    python -m venv venv
    if errorlevel 1 goto :error
) else (
    echo Virtualenv gia' presente, salto.
)

echo.
echo === 3. Installazione dipendenze backend ===
call venv\Scripts\activate.bat
pip install -r requirements.txt
if errorlevel 1 goto :error

echo.
echo === 4. Configurazione .env backend ===
if not exist .env (
    copy .env.example .env >nul
    for /f "delims=" %%K in ('python -c "import secrets; print(secrets.token_urlsafe(50))"') do set SECRET_KEY_VALUE=%%K
    powershell -NoProfile -Command "(Get-Content .env) -replace '^SECRET_KEY=.*', 'SECRET_KEY=%SECRET_KEY_VALUE%' | Set-Content .env"
    echo Creato .env con una nuova SECRET_KEY generata automaticamente.
    echo ATTENZIONE: apri easytrip-backend\.env e inserisci la tua GROQ_API_KEY
    echo oppure GEMINI_API_KEY prima di usare la chat.
) else (
    echo .env gia' presente, non lo sovrascrivo.
)

echo.
echo === 5. Migrazioni database ===
python manage.py migrate
if errorlevel 1 goto :error

echo.
echo === 6. Creazione superuser Django ===
echo (ti verranno chiesti username, email e password)
python manage.py createsuperuser

echo.
echo === 7. Popolamento dati di esempio ===
python manage.py seed_data
if errorlevel 1 goto :error

echo.
echo === 8. Generazione embedding per il RAG ===
echo (al primo avvio scarica il modello da Hugging Face, puo' richiedere qualche minuto)
python manage.py generate_embeddings
if errorlevel 1 goto :error

call venv\Scripts\deactivate.bat

echo.
echo === 9. Configurazione frontend ===
cd /d "%~dp0easytrip-frontend"
if not exist .env (
    copy .env.example .env >nul
    echo Creato easytrip-frontend\.env con i valori di default.
) else (
    echo .env gia' presente, non lo sovrascrivo.
)

echo.
echo === 10. Installazione dipendenze frontend ===
npm install
if errorlevel 1 goto :error

cd /d "%~dp0"

echo.
echo ============================================
echo   Setup completato!
echo ============================================
echo.
echo Prima di avviare il progetto con start_all.bat, verifica di aver
echo inserito una API key valida (Groq o Gemini) in:
echo   easytrip-backend\.env
echo.
pause
exit /b 0

:error
echo.
echo Setup interrotto per un errore. Controlla i messaggi sopra.
pause
exit /b 1
