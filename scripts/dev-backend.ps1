# Windows PowerShell: set up and run the FastAPI backend.
Set-Location "$PSScriptRoot\..\backend"
if (-not (Test-Path ".venv")) { py -3 -m venv .venv }
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
if (-not (Test-Path ".env")) { Copy-Item .env.development .env }
alembic upgrade head
python ..\scripts\seed.py
uvicorn app.main:app --reload --port 8000
