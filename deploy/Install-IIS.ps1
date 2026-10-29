#requires -RunAsAdministrator
<#
.SYNOPSIS
    Publishes the CP_BOT Angular frontend and FastAPI backend to IIS on this server.

.DESCRIPTION
    Run this ONCE, elevated (Administrator). It will:
      1. Enable the required IIS Windows features.
      2. Install the URL Rewrite + HttpPlatformHandler IIS modules (downloads them if missing).
      3. Import the TLS certificate from a .pfx (or use a thumbprint already in LocalMachine\My).
      4. Create two app pools and two sites:
           - Frontend  (static Angular)   ->  http/https  app.<domain>
           - Backend   (FastAPI/Uvicorn)  ->  https only  api.<domain>  via HttpPlatformHandler
      5. Bind HTTPS (SNI) using your certificate.
      6. Grant the backend app pool identity the filesystem permissions it needs
         (read+execute on code + venv, write on .\uploads and .\logs).

    IIS does NOT run Python. The backend's web.config tells HttpPlatformHandler to launch
    .venv\Scripts\python.exe -m uvicorn main:app and reverse-proxies to it.

.PARAMETER Domain
    Base domain. Frontend becomes app.<Domain>, backend api.<Domain>.
    (Or pass -FrontendHost / -BackendHost explicitly to override.)

.EXAMPLE
    # Wildcard PFX covering both subdomains:
    .\Install-IIS.ps1 -Domain contoso.com -PfxPath C:\certs\wildcard-contoso.pfx

.EXAMPLE
    # Cert already imported into LocalMachine\My:
    .\Install-IIS.ps1 -FrontendHost app.contoso.com -BackendHost api.contoso.com -CertThumbprint AABBCC...

.NOTES
    If Windows reports a pending reboot after enabling IIS features, reboot and re-run this script.
#>
[CmdletBinding(DefaultParameterSetName = 'Pfx')]
param(
    [string]$Domain,
    [string]$FrontendHost,
    [string]$BackendHost,
    [string]$ProjectRoot = 'C:\Work\CP_BOT',

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
function Info($m){ Write-Host "[+] $m" -ForegroundColor Cyan }
function Warn($m){ Write-Host "[!] $m" -ForegroundColor Yellow }
function Ok  ($m){ Write-Host "[OK] $m" -ForegroundColor Green }

# ---------------------------------------------------------------------------
# 0. Resolve hostnames + paths
# ---------------------------------------------------------------------------
if (-not $FrontendHost) { if ($Domain) { $FrontendHost = "app.$Domain" } else { throw 'Provide -Domain (or -FrontendHost and -BackendHost).' } }
if (-not $BackendHost)  { if ($Domain) { $BackendHost  = "api.$Domain" } else { throw 'Provide -Domain (or -FrontendHost and -BackendHost).' } }

$FrontendPath = Join-Path $ProjectRoot 'frontend\dist\frontend\browser'
$BackendPath  = $ProjectRoot

Info "Frontend host : $FrontendHost  -> $FrontendPath"
Info "Backend  host : $BackendHost   -> $BackendPath"

if (-not (Test-Path $FrontendPath)) {
    Warn "Frontend build not found at $FrontendPath. Run 'npm run build' in .\frontend first (sites will still be created)."
}
if (-not (Test-Path (Join-Path $ProjectRoot '.env'))) {
    Warn "No .env found in $ProjectRoot. The backend will FAIL to start without OPENAI_API_KEY. Create it from .env.example."
}

# ---------------------------------------------------------------------------
# 1. Enable IIS Windows features
# ---------------------------------------------------------------------------
Info 'Enabling IIS Windows features...'
$features = @(
    'IIS-WebServerRole','IIS-WebServer','IIS-CommonHttpFeatures','IIS-StaticContent',
    'IIS-DefaultDocument','IIS-HttpErrors','IIS-HttpRedirect','IIS-RequestFiltering',
    'IIS-HttpLogging','IIS-HttpCompressionStatic','IIS-ApplicationDevelopment',
    'IIS-ManagementConsole','IIS-ManagementScriptingTools'
)
foreach ($f in $features) {
    try {
        $state = (Get-WindowsOptionalFeature -Online -FeatureName $f).State
        if ($state -ne 'Enabled') {
            Enable-WindowsOptionalFeature -Online -FeatureName $f -All -NoRestart | Out-Null
            Ok "enabled $f"
        }
    } catch { Warn "could not enable $f : $($_.Exception.Message)" }
}

# ---------------------------------------------------------------------------
# 2. Install IIS modules (URL Rewrite + HttpPlatformHandler)
# ---------------------------------------------------------------------------
$inetsrv = Join-Path $env:windir 'System32\inetsrv'
function Install-Msi($name, $url, $probeDll) {
    if (Test-Path (Join-Path $inetsrv $probeDll)) { Ok "$name already installed"; return }
    Info "Installing $name ..."
    $msi = Join-Path $env:TEMP ("{0}.msi" -f ($name -replace '\W','_'))
    try {
        Invoke-WebRequest -Uri $url -OutFile $msi -UseBasicParsing
        $p = Start-Process msiexec.exe -ArgumentList "/i `"$msi`" /qn /norestart" -Wait -PassThru
        if ($p.ExitCode -ne 0) { throw "msiexec exit code $($p.ExitCode)" }
        Ok "$name installed"
    } catch {
        Warn "Automatic install of $name failed: $($_.Exception.Message)"
        Warn "Download and install it manually, then re-run: $url"
    }
}
Install-Msi 'URL Rewrite 2.1' 'https://download.microsoft.com/download/1/2/8/128E2E22-C1B9-44A4-BE2A-5859ED1D4592/rewrite_amd64_en-US.msi' 'rewrite.dll'
Install-Msi 'HttpPlatformHandler 1.2' 'https://download.microsoft.com/download/D/D/C/DDCB48BB-9861-49A3-8A06-99A1B6C0EE2D/httpPlatformHandler_amd64.msi' 'httpPlatformHandler.dll'

# ---------------------------------------------------------------------------
# 3. Load WebAdministration
# ---------------------------------------------------------------------------
try { Import-Module WebAdministration -ErrorAction Stop }
catch { throw "WebAdministration module unavailable. A reboot is likely pending after enabling IIS features - reboot and re-run this script. ($($_.Exception.Message))" }

# ---------------------------------------------------------------------------
# 4. Certificate
# ---------------------------------------------------------------------------
if ($PfxPath) {
    if (-not (Test-Path $PfxPath)) { throw "PFX not found: $PfxPath" }
    if ([string]::IsNullOrEmpty($PfxPassword)) { $sec = Read-Host -AsSecureString "PFX password for $PfxPath" }
    else { $sec = ConvertTo-SecureString $PfxPassword -AsPlainText -Force }
    Info "Importing certificate from $PfxPath ..."
    $imported = Import-PfxCertificate -FilePath $PfxPath -CertStoreLocation Cert:\LocalMachine\My -Password $sec
    $CertThumbprint = $imported.Thumbprint
    Ok "imported, thumbprint $CertThumbprint"
}
if ([string]::IsNullOrEmpty($CertThumbprint)) { throw 'No certificate: pass -PfxPath or -CertThumbprint.' }
$cert = Get-Item "Cert:\LocalMachine\My\$CertThumbprint" -ErrorAction Stop
$dns  = ($cert.DnsNameList.Unicode -join ', ')
Info "Using cert: $($cert.Subject)  [covers: $dns]"
foreach ($h in @($FrontendHost,$BackendHost)) {
    $match = $cert.DnsNameList.Unicode | Where-Object { $_ -eq $h -or ($_ -like '*.*' -and $h -like ($_ -replace '^\*','*')) }
    if (-not $match) { Warn "Certificate does not appear to cover $h (has: $dns)." }
}

# ---------------------------------------------------------------------------
# 5. App pools
# ---------------------------------------------------------------------------
foreach ($p in @($FrontendPool,$BackendPool)) {
    if (-not (Test-Path "IIS:\AppPools\$p")) { New-WebAppPool -Name $p | Out-Null; Ok "created app pool $p" }
    # No managed (.NET) code - both serve static files / native modules only
    Set-ItemProperty "IIS:\AppPools\$p" -Name managedRuntimeVersion -Value ''
}
Set-ItemProperty "IIS:\AppPools\$BackendPool" -Name startMode -Value 'AlwaysRunning'

# ---------------------------------------------------------------------------
# 6. Sites + bindings
# ---------------------------------------------------------------------------
function New-OrUpdateSite($name, $path, $pool, $hostHeader) {
    if (-not (Test-Path "IIS:\Sites\$name")) {
        New-Website -Name $name -PhysicalPath $path -ApplicationPool $pool -HostHeader $hostHeader -Port 80 -Force | Out-Null
        Ok "created site $name"
    } else {
        Set-ItemProperty "IIS:\Sites\$name" -Name physicalPath -Value $path
        Set-ItemProperty "IIS:\Sites\$name" -Name applicationPool -Value $pool
        Ok "updated site $name"
    }
}
function Add-Https($name, $hostHeader, $thumb) {
    if (-not (Get-WebBinding -Name $name -Protocol https -HostHeader $hostHeader -Port 443 -ErrorAction SilentlyContinue)) {
        New-WebBinding -Name $name -Protocol https -Port 443 -HostHeader $hostHeader -SslFlags 1
    }
    (Get-WebBinding -Name $name -Protocol https -HostHeader $hostHeader -Port 443).AddSslCertificate($thumb, 'My')
    Ok "https binding $hostHeader -> $name"
}

New-OrUpdateSite $FrontendSite $FrontendPath $FrontendPool $FrontendHost   # keeps http:80 for the HTTPS-redirect rule
Add-Https        $FrontendSite $FrontendHost $CertThumbprint

New-OrUpdateSite $BackendSite  $BackendPath  $BackendPool  $BackendHost
Add-Https        $BackendSite  $BackendHost  $CertThumbprint
# backend is HTTPS-only: drop its plain http binding
if (Get-WebBinding -Name $BackendSite -Protocol http -Port 80 -ErrorAction SilentlyContinue) {
    Remove-WebBinding -Name $BackendSite -Protocol http -Port 80
    Ok 'removed backend http:80 binding (https only)'
}

if ($StopDefaultSite -and (Test-Path 'IIS:\Sites\Default Web Site')) {
    Stop-Website 'Default Web Site'; Ok 'stopped Default Web Site'
}

# ---------------------------------------------------------------------------
# 7. Filesystem layout + permissions
# ---------------------------------------------------------------------------
foreach ($d in 'uploads\media','logs') { New-Item -ItemType Directory -Force (Join-Path $ProjectRoot $d) | Out-Null }

$backendId  = "IIS AppPool\$BackendPool"
$frontendId = "IIS AppPool\$FrontendPool"
Info "Granting filesystem permissions..."

# Backend: read+execute on code + venv (avoid recursing the huge frontend\node_modules)
icacls "$ProjectRoot" /grant "$($backendId):(OI)(CI)(RX)" /C /Q | Out-Null
Get-ChildItem -File $ProjectRoot | ForEach-Object { icacls $_.FullName /grant "$($backendId):(RX)" /C /Q | Out-Null }
foreach ($d in '.venv','core','services') {
    $sub = Join-Path $ProjectRoot $d
    if (Test-Path $sub) { icacls $sub /grant "$($backendId):(OI)(CI)(RX)" /T /C /Q | Out-Null }
}
# Backend: write on uploads + logs
foreach ($d in 'uploads','logs') {
    icacls (Join-Path $ProjectRoot $d) /grant "$($backendId):(OI)(CI)(M)" /T /C /Q | Out-Null
}
# Frontend: read static files
if (Test-Path $FrontendPath) { icacls $FrontendPath /grant "$($frontendId):(OI)(CI)(RX)" /T /C /Q | Out-Null }
Ok 'permissions applied'

# ---------------------------------------------------------------------------
# 8. Start everything
# ---------------------------------------------------------------------------
Restart-WebAppPool $FrontendPool
Restart-WebAppPool $BackendPool
Start-Website $FrontendSite -ErrorAction SilentlyContinue
Start-Website $BackendSite  -ErrorAction SilentlyContinue

Write-Host ''
Ok 'IIS deployment complete.'
Write-Host "  Frontend : https://$FrontendHost"            -ForegroundColor Green
Write-Host "  Backend  : https://$BackendHost/health"      -ForegroundColor Green
Write-Host ''
Warn 'Checklist:'
Write-Host "   - DNS: $FrontendHost and $BackendHost must resolve to this server."
Write-Host "   - .env with a valid OPENAI_API_KEY must sit in $ProjectRoot"
Write-Host "   - PostgreSQL must be reachable at localhost:5433 (see db.py)."
Write-Host "   - Backend startup logs: $ProjectRoot\logs\backend-stdout*.log"
