# Windows PowerShell: set up and run the Next.js frontend.
Set-Location "$PSScriptRoot\..\frontend"
if (-not (Test-Path "node_modules")) { npm install }
if (-not (Test-Path ".env.local")) { Copy-Item .env.example .env.local }
npm run dev
