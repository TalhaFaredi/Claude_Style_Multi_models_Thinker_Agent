# Multi-Mode AI Assistant - Backend

## Repository branches

- [main](https://github.com/TalhaFaredi/Claude_Style_Multi_models_Thinker_Agent/tree/main): backend source (default branch).
- [backend](https://github.com/TalhaFaredi/Claude_Style_Multi_models_Thinker_Agent/tree/backend): the same backend release.
- [frontend](https://github.com/TalhaFaredi/Claude_Style_Multi_models_Thinker_Agent/tree/frontend): Next.js frontend source.

Code keeps its original `backend/` or `frontend/` directory. Clone the backend and frontend branches into separate directories to run both services.

## Run the backend

Requires Python 3.11+. Create a root `.env` with your own `OPENROUTER_API_KEY` and optional `NVIDIA_API_KEY`. Provider keys, local databases, uploads and generated files are excluded from Git.

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

API docs: http://127.0.0.1:8000/docs. This application is intended for local use; bind to loopback. Docker's Linux engine and `python:3.12-alpine` image are required for the optional code sandbox.

## Verify

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

Provider-backed acceptance runners in `backend/tests/live_*acceptance.py` require explicit `--live` and have spending caps.

See [backend/README.md](backend/README.md) for configuration and source details.
