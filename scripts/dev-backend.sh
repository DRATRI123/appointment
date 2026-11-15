#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../backend"
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
pip install -q --upgrade pip && pip install -q -r requirements.txt
[ -f .env ] || cp .env.development .env
alembic upgrade head
python ../scripts/seed.py
uvicorn app.main:app --reload --port 8000
