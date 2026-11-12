#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../frontend"
[ -d node_modules ] || npm install
[ -f .env.local ] || cp .env.example .env.local
npm run dev
