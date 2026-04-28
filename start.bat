@echo off
REM Quick-start for Windows: builds data, launches API + Streamlit
cd /d "%~dp0src"

echo === Step 1: Build data from Google Drive ===
python data_builder.py
if errorlevel 1 (
    echo ERROR: data_builder.py failed. Check your credentials.json.
    pause
    exit /b 1
)

echo.
echo === Step 2: Starting FastAPI on port 8000 ===
start "Market Breadth API" cmd /k "uvicorn api:app --host 0.0.0.0 --port 8000"

timeout /t 3 /nobreak > nul

echo.
echo === Step 3: Starting Streamlit on port 8501 ===
streamlit run app.py

pause
