@echo off
cd /d C:\Users\10341953440\Downloads\previsao-jogos\backend
C:\Users\10341953440\Downloads\previsao-jogos\api\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000 --reload
