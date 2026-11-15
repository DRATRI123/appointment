# Windows PowerShell: set up and run the Next.js frontend.
Set-Location "$PSScriptRoot\..\frontend"
if (-not (Test-Path "node_modules")) { npm install }
# .env.development is loaded automatically by "npm run dev"; put personal overrides in .env.local.
npm run dev
