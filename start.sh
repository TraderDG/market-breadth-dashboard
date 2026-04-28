#!/usr/bin/env bash
# Quick-start script: builds data, then launches API + Streamlit concurrently
set -e

cd "$(dirname "$0")/src"

echo "=== Step 1: Build data from Google Drive ==="
python data_builder.py

echo ""
echo "=== Step 2: Starting FastAPI (port 8000) ==="
uvicorn api:app --host 0.0.0.0 --port 8000 &
API_PID=$!

sleep 2

echo ""
echo "=== Step 3: Starting Streamlit dashboard (port 8501) ==="
streamlit run app.py

# Cleanup API on exit
kill $API_PID 2>/dev/null || true
