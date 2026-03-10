call .venv\Scripts\activate

start cmd /k python -m uvicorn server:app --host 0.0.0.0 --port 8000

timeout /t 3

start cmd /k ngrok http 8000