#requires -RunAsAdministrator
<#
.SYNOPSIS
    Switches the CP_BOT backend site to REVERSE-PROXY mode (IIS -> Uvicorn on a fixed port).
.DESCRIPTION
    Run elevated. Installs URL Rewrite + ARR, enables the ARR proxy, and writes a reverse-proxy
    web.config into the backend site that forwards all requests to http://127.0.0.1:<Port>.
    Uvicorn must be listening on that port (see Install-BackendService.ps1).
.EXAMPLE
    .\Setup-ReverseProxy.ps1 -BackendSite CP_BOT_Backend -Port 8000
#>
[CmdletBinding()]
param(
    [string]$BackendSite = 'CP_BOT_Backend',
    [string]$BackendPath,
    [int]$Port = 8000
)
$ErrorActionPreference = 'Stop'
function Info($m){ Write-Host "[+] $m"  -ForegroundColor Cyan }
function Warn($m){ Write-Host "[!] $m"  -ForegroundColor Yellow }
function Ok  ($m){ Write-Host "[OK] $m" -ForegroundColor Green }

$inetsrv = Join-Path $env:windir 'System32\inetsrv'
$arrDll  = Join-Path ${env:ProgramFiles} 'IIS\Application Request Routing\requestRouter.dll'

function Install-Msi($name,$url,$probePath){
    if (Test-Path $probePath) { Ok "$name present"; return }
    Info "Installing $name ..."
    $msi = Join-Path $env:TEMP (($name -replace '\W','_') + '.msi')
    try {
        Invoke-WebRequest $url -OutFile $msi -UseBasicParsing
        $p = Start-Process msiexec.exe -ArgumentList "/i `"$msi`" /qn /norestart" -Wait -PassThru
        if ($p.ExitCode -ne 0) { throw "msiexec exit $($p.ExitCode)" }
        Ok "$name installed"
    } catch { Warn "Auto-install of $name failed: $($_.Exception.Message). Install manually: $url" }
}

# URL Rewrite is a prerequisite for ARR - install it first
Install-Msi 'URL Rewrite 2.1' 'https://download.microsoft.com/download/1/2/8/128E2E22-C1B9-44A4-BE2A-5859ED1D4592/rewrite_amd64_en-US.msi' (Join-Path $inetsrv 'rewrite.dll')
Install-Msi 'ARR 3.0'         'https://download.microsoft.com/download/E/9/8/E9849D6A-020E-47E4-9FD0-A023E99B54EB/requestRouter_amd64.msi' $arrDll

Import-Module WebAdministration -ErrorAction Stop

# Enable the ARR reverse proxy at the server level
Set-WebConfigurationProperty -pspath 'MACHINE/WEBROOT/APPHOST' -filter 'system.webServer/proxy' -name 'enabled' -value 'True'
Ok 'ARR reverse proxy enabled (server level)'

# Resolve backend site physical path
if (-not $BackendPath) {
    if (-not (Test-Path "IIS:\Sites\$BackendSite")) { throw "Site '$BackendSite' not found. Pass -BackendPath explicitly." }
    $BackendPath = (Get-Item "IIS:\Sites\$BackendSite").physicalPath
}
Info "Backend site path: $BackendPath"

# Write the reverse-proxy web.config (with chosen port)
$tpl = Get-Content (Join-Path $PSScriptRoot 'web.config.reverseproxy') -Raw
$tpl.Replace('127.0.0.1:8000', "127.0.0.1:$Port") | Set-Content (Join-Path $BackendPath 'web.config') -Encoding UTF8
Ok "reverse-proxy web.config written -> http://127.0.0.1:$Port"

# Reload IIS so the ARR module is active
iisreset /restart | Out-Null
Ok 'IIS restarted'
Write-Host ''
Warn "Make sure Uvicorn is listening on 127.0.0.1:$Port (run Install-BackendService.ps1)."
