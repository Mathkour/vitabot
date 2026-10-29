#requires -RunAsAdministrator
<#
.SYNOPSIS
    Configures IIS on THIS server to host the CP_BOT publish package (frontend + backend).

.DESCRIPTION
    Run this elevated, from inside the extracted publish package (the folder that contains
    .\frontend and .\backend). It will:
      1. Copy frontend + backend into -InstallRoot (default C:\inetpub\cpbot).
      2. Create the backend Python venv and install requirements (needs Python 3.10+).
      3. Stamp the backend web.config with the real install path.
      4. Ensure IIS features + install URL Rewrite and HttpPlatformHandler modules.
      5. Import your TLS certificate (PFX) or use an existing thumbprint.
      6. Create app pools + sites + HTTPS (SNI) bindings.
      7. Grant the app pool identities the needed filesystem permissions.

.EXAMPLE
    .\Setup-Server.ps1 -Domain credit-plus.me -PfxPath C:\certs\wildcard.pfx

.EXAMPLE
    .\Setup-Server.ps1 -Domain credit-plus.me -CertThumbprint AABBCC... -InstallRoot D:\sites\cpbot
#>
[CmdletBinding(DefaultParameterSetName = 'Pfx')]
param(
    [string]$Domain,
    [string]$FrontendHost,
    [string]$BackendHost,
    [string]$InstallRoot = 'C:\inetpub\cpbot',

    [Parameter(ParameterSetName = 'Pfx')]      [string]$PfxPath,
    [Parameter(ParameterSetName = 'Pfx')]      [string]$PfxPassword,
    [Parameter(ParameterSetName = 'Thumbprint')][string]$CertThumbprint,

    [string]$FrontendPool = 'CP_BOT_Frontend',
    [string]$BackendPool  = 'CP_BOT_Backend',
    [string]$FrontendSite = 'CP_BOT_Frontend',
    [string]$BackendSite  = 'CP_BOT_Backend',

    [switch]$StopDefaultSite
)
$ErrorActionPreference = 'Stop'
function Info($m){ Write-Host "[+] $m"  -ForegroundColor Cyan }
function Warn($m){ Write-Host "[!] $m"  -ForegroundColor Yellow }
function Ok  ($m){ Write-Host "[OK] $m" -ForegroundColor Green }

# --- hosts ---
if (-not $FrontendHost) { if ($Domain) { $FrontendHost = "app.$Domain" } else { throw 'Provide -Domain (or -FrontendHost and -BackendHost).' } }
if (-not $BackendHost)  { if ($Domain) { $BackendHost  = "api.$Domain" } else { throw 'Provide -Domain (or -FrontendHost and -BackendHost).' } }

# --- package source (folder this script lives in) ---
$pkg = Split-Path -Parent $MyInvocation.MyCommand.Path
$srcFrontend = Join-Path $pkg 'frontend'
$srcBackend  = Join-Path $pkg 'backend'
if (-not (Test-Path $srcFrontend) -or -not (Test-Path $srcBackend)) {
    throw "Run this from inside the publish package (expected .\frontend and .\backend next to the script)."
}
$dstFrontend = Join-Path $InstallRoot 'frontend'
$dstBackend  = Join-Path $InstallRoot 'backend'
Info "Frontend: $FrontendHost  -> $dstFrontend"
Info "Backend : $BackendHost   -> $dstBackend"

# --- 1. copy into InstallRoot ---
New-Item -ItemType Directory -Force $InstallRoot | Out-Null
$samePlace = ((Resolve-Path $pkg).Path -ieq (Resolve-Path $InstallRoot -ErrorAction SilentlyContinue).Path)
if (-not $samePlace) {
    Info "Copying files to $InstallRoot ..."
    robocopy $srcFrontend $dstFrontend /MIR /XD logs /NFL /NDL /NJH /NJS /NP | Out-Null
    robocopy $srcBackend  $dstBackend  /E /XD .venv __pycache__ /XF .env /NFL /NDL /NJH /NJS /NP | Out-Null
    Ok 'files copied'
}
foreach ($d in 'logs','uploads\media') { New-Item -ItemType Directory -Force (Join-Path $dstBackend $d) | Out-Null }

# --- 2. backend Python venv ---
Info 'Setting up Python venv...'
$py = $null
foreach ($c in 'py','python') { if (Get-Command $c -ErrorAction SilentlyContinue) { $py = (Get-Command $c).Source; break } }
if (-not $py) { throw 'Python not found on PATH. Install Python 3.10+ (the backend is a Python/FastAPI app), then re-run.' }
$venvPy = Join-Path $dstBackend '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPy)) { & $py -m venv (Join-Path $dstBackend '.venv') }
& $venvPy -m pip install --upgrade pip  | Out-Null
& $venvPy -m pip install -r (Join-Path $dstBackend 'requirements.txt')
Ok 'venv ready'

# --- 3. stamp backend web.config absolute paths ---
$wc = Join-Path $dstBackend 'web.config'
(Get-Content $wc -Raw).Replace('C:\inetpub\cpbot\backend', $dstBackend) | Set-Content $wc -Encoding UTF8
Ok 'web.config paths set'

# --- .env check ---
if (-not (Test-Path (Join-Path $dstBackend '.env'))) {
    Warn "No .env in $dstBackend - backend will NOT start. Copy .env.example to .env and set OPENAI_API_KEY."
}

# --- 4. IIS features + modules ---
Info 'Ensuring IIS features...'
foreach ($f in 'IIS-WebServerRole','IIS-WebServer','IIS-StaticContent','IIS-DefaultDocument','IIS-HttpRedirect','IIS-HttpErrors','IIS-RequestFiltering','IIS-ManagementConsole','IIS-ManagementScriptingTools') {
    try { if ((Get-WindowsOptionalFeature -Online -FeatureName $f).State -ne 'Enabled') { Enable-WindowsOptionalFeature -Online -FeatureName $f -All -NoRestart | Out-Null; Ok "enabled $f" } }
    catch { Warn "feature $f : $($_.Exception.Message)" }
}
$inetsrv = Join-Path $env:windir 'System32\inetsrv'
function Install-Msi($name,$url,$dll){
    if (Test-Path (Join-Path $inetsrv $dll)) { Ok "$name present"; return }
    Info "Installing $name ..."
    $msi = Join-Path $env:TEMP (($name -replace '\W','_') + '.msi')
    try {
        Invoke-WebRequest $url -OutFile $msi -UseBasicParsing
        $p = Start-Process msiexec.exe -ArgumentList "/i `"$msi`" /qn /norestart" -Wait -PassThru
        if ($p.ExitCode -ne 0) { throw "msiexec exit $($p.ExitCode)" }
        Ok "$name installed"
    } catch { Warn "Auto-install of $name failed: $($_.Exception.Message). Install manually: $url" }
}
Install-Msi 'URL Rewrite 2.1'         'https://download.microsoft.com/download/1/2/8/128E2E22-C1B9-44A4-BE2A-5859ED1D4592/rewrite_amd64_en-US.msi' 'rewrite.dll'
Install-Msi 'HttpPlatformHandler 1.2' 'https://download.microsoft.com/download/D/D/C/DDCB48BB-9861-49A3-8A06-99A1B6C0EE2D/httpPlatformHandler_amd64.msi' 'httpPlatformHandler.dll'

try { Import-Module WebAdministration -ErrorAction Stop }
catch { throw "WebAdministration unavailable - reboot (pending IIS feature install) and re-run. ($($_.Exception.Message))" }

# --- 5. certificate ---
if ($PfxPath) {
    if (-not (Test-Path $PfxPath)) { throw "PFX not found: $PfxPath" }
    if ([string]::IsNullOrEmpty($PfxPassword)) { $sec = Read-Host -AsSecureString "PFX password for $PfxPath" }
    else { $sec = ConvertTo-SecureString $PfxPassword -AsPlainText -Force }
    $imported = Import-PfxCertificate -FilePath $PfxPath -CertStoreLocation Cert:\LocalMachine\My -Password $sec
    $CertThumbprint = $imported.Thumbprint
    Ok "imported cert $CertThumbprint"
}
if ([string]::IsNullOrEmpty($CertThumbprint)) { throw 'No certificate: pass -PfxPath or -CertThumbprint.' }
$cert = Get-Item "Cert:\LocalMachine\My\$CertThumbprint" -ErrorAction Stop
Info "Using cert: $($cert.Subject) [covers: $($cert.DnsNameList.Unicode -join ', ')]"

# --- 6. app pools ---
foreach ($p in @($FrontendPool,$BackendPool)) {
    if (-not (Test-Path "IIS:\AppPools\$p")) { New-WebAppPool -Name $p | Out-Null; Ok "created pool $p" }
    Set-ItemProperty "IIS:\AppPools\$p" -Name managedRuntimeVersion -Value ''   # No Managed Code
}
Set-ItemProperty "IIS:\AppPools\$BackendPool" -Name startMode -Value 'AlwaysRunning'

# --- 7. sites + bindings ---
function New-OrUpdateSite($name,$path,$pool,$hostHeader){
    if (-not (Test-Path "IIS:\Sites\$name")) { New-Website -Name $name -PhysicalPath $path -ApplicationPool $pool -HostHeader $hostHeader -Port 80 -Force | Out-Null; Ok "created site $name" }
    else { Set-ItemProperty "IIS:\Sites\$name" -Name physicalPath -Value $path; Set-ItemProperty "IIS:\Sites\$name" -Name applicationPool -Value $pool; Ok "updated site $name" }
}
function Add-Https($name,$hostHeader,$thumb){
    if (-not (Get-WebBinding -Name $name -Protocol https -HostHeader $hostHeader -Port 443 -ErrorAction SilentlyContinue)) {
        New-WebBinding -Name $name -Protocol https -Port 443 -HostHeader $hostHeader -SslFlags 1
    }
    (Get-WebBinding -Name $name -Protocol https -HostHeader $hostHeader -Port 443).AddSslCertificate($thumb,'My')
    Ok "https binding $hostHeader -> $name"
}
New-OrUpdateSite $FrontendSite $dstFrontend $FrontendPool $FrontendHost
Add-Https        $FrontendSite $FrontendHost $CertThumbprint
New-OrUpdateSite $BackendSite  $dstBackend  $BackendPool  $BackendHost
Add-Https        $BackendSite  $BackendHost  $CertThumbprint
if (Get-WebBinding -Name $BackendSite -Protocol http -Port 80 -ErrorAction SilentlyContinue) {
    Remove-WebBinding -Name $BackendSite -Protocol http -Port 80; Ok 'backend is HTTPS-only'
}
if ($StopDefaultSite -and (Test-Path 'IIS:\Sites\Default Web Site')) { Stop-Website 'Default Web Site'; Ok 'stopped Default Web Site' }

# --- 8. permissions ---
Info 'Granting filesystem permissions...'
$backendId  = "IIS AppPool\$BackendPool"
$frontendId = "IIS AppPool\$FrontendPool"
icacls $dstBackend  /grant "$($backendId):(OI)(CI)(RX)" /T /C /Q | Out-Null
foreach ($d in 'logs','uploads') { icacls (Join-Path $dstBackend $d) /grant "$($backendId):(OI)(CI)(M)" /T /C /Q | Out-Null }
icacls $dstFrontend /grant "$($frontendId):(OI)(CI)(RX)" /T /C /Q | Out-Null
Ok 'permissions applied'

# --- start ---
Restart-WebAppPool $FrontendPool; Restart-WebAppPool $BackendPool
Start-Website $FrontendSite -ErrorAction SilentlyContinue
Start-Website $BackendSite  -ErrorAction SilentlyContinue

Write-Host ''
Ok 'Done.'
Write-Host "  Frontend : https://$FrontendHost"       -ForegroundColor Green
Write-Host "  Backend  : https://$BackendHost/health" -ForegroundColor Green
Write-Host ''
Warn 'Remember: DNS for both hosts must point here, .env must exist with OPENAI_API_KEY, and PostgreSQL must be reachable at localhost:5433 (db.py).'
