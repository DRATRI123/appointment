# Windows PowerShell: set up and run the Next.js frontend.
Set-Location "$PSScriptRoot\..\frontend"
if (-not (Test-Path "node_modules")) { npm install }
# No .env needed: the website talks to the API at http://127.0.0.1:8000 by default (see .env.example, "Frontend").
npm run dev
