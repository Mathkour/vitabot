<#
.SYNOPSIS
    Assembles the deployable publish package and zips it for copying to the server.
.DESCRIPTION
    Produces:  <repo>\publish\   (frontend\, backend\, Setup-Server.ps1, SETUP-ON-SERVER.md)
    and        <repo>\CP_BOT_publish.zip
    Run AFTER building the frontend (npm run build). Does NOT include node_modules,
    .venv, .git, .env, or uploads content.
#>
$ErrorActionPreference = 'Stop'
$repo   = Split-Path -Parent $PSScriptRoot           # repo root (parent of \deploy)
$deploy = $PSScriptRoot
$pub    = Join-Path $repo 'publish'
$dist   = Join-Path $repo 'frontend\dist\frontend\browser'

if (-not (Test-Path $dist)) { throw "Frontend build not found at $dist. Run 'npm run build' in \frontend first." }

Write-Host "Cleaning $pub ..." -ForegroundColor Cyan
if (Test-Path $pub) { Remove-Item $pub -Recurse -Force }
New-Item -ItemType Directory -Force (Join-Path $pub 'frontend'),
                                    (Join-Path $pub 'backend'),
                                    (Join-Path $pub 'backend\logs'),
                                    (Join-Path $pub 'backend\uploads\media') | Out-Null

# --- frontend (static build, already contains web.config) ---
Write-Host "Copying frontend..." -ForegroundColor Cyan
robocopy $dist (Join-Path $pub 'frontend') /E /NFL /NDL /NJH /NJS /NP | Out-Null

# --- backend (source only) ---
Write-Host "Copying backend..." -ForegroundColor Cyan
Copy-Item (Join-Path $repo 'main.py'),(Join-Path $repo 'db.py'),(Join-Path $repo 'requirements.txt'),(Join-Path $repo '.env.example') (Join-Path $pub 'backend')
robocopy (Join-Path $repo 'core')     (Join-Path $pub 'backend\core')     /E /XD __pycache__ /NFL /NDL /NJH /NJS /NP | Out-Null
robocopy (Join-Path $repo 'services') (Join-Path $pub 'backend\services') /E /XD __pycache__ /NFL /NDL /NJH /NJS /NP | Out-Null
Copy-Item (Join-Path $deploy 'web.config.server') (Join-Path $pub 'backend\web.config')
New-Item -ItemType File -Force (Join-Path $pub 'backend\logs\.gitkeep') | Out-Null

# --- installers + guide at package root ---
Copy-Item (Join-Path $deploy 'Setup-Server.ps1'),
          (Join-Path $deploy 'SETUP-ON-SERVER.md'),
          (Join-Path $deploy 'Setup-ReverseProxy.ps1'),
          (Join-Path $deploy 'Install-BackendService.ps1'),
          (Join-Path $deploy 'web.config.reverseproxy') $pub

# --- zip ---
$zip = Join-Path $repo 'CP_BOT_publish.zip'
if (Test-Path $zip) { Remove-Item $zip -Force }
Write-Host "Zipping -> $zip ..." -ForegroundColor Cyan
Compress-Archive -Path (Join-Path $pub '*') -DestinationPath $zip

Write-Host ""
Write-Host "[OK] Package ready:" -ForegroundColor Green
Write-Host "     Folder : $pub"
Write-Host "     Zip    : $zip"
