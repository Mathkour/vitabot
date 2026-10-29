# Deploy CP_BOT to the IIS server

This package contains everything to host the app on a Windows server that already has IIS.

```
publish\
  frontend\            Pre-built Angular site (static) -> serve as-is. Already contains web.config.
  backend\             FastAPI source + requirements.txt + web.config + .env.example
  Setup-Server.ps1     One-shot installer (recommended)
  SETUP-ON-SERVER.md   This file
```

| Site     | URL                       | Folder                | How it runs |
|----------|---------------------------|-----------------------|-------------|
| Frontend | `https://app.credit-plus.me` | `<root>\frontend`  | Static files + URL Rewrite (SPA routing) |
| Backend  | `https://api.credit-plus.me` | `<root>\backend`   | HttpPlatformHandler launches `.venv\Scripts\python.exe -m uvicorn main:app` |

> The frontend is already built and points at `https://api.credit-plus.me`. The backend already
> allows CORS from `https://app.credit-plus.me`. No rebuild needed unless those hosts change.

---

## Prerequisites on the server
- **IIS** with two extra modules: **URL Rewrite** and **HttpPlatformHandler** (the script installs them if missing).
- **Python 3.10+** (the backend is Python — Node is *not* required on the server; the frontend is pre-built).
  Install from [python.org](https://www.python.org/downloads/windows/) and tick **"Add python.exe to PATH"**
  (that also gives you the `py` launcher), or `winget install -e --id Python.Python.3.12`. Reopen PowerShell after.
- **TLS certificate** covering `app.credit-plus.me` and `api.credit-plus.me` (a wildcard `*.credit-plus.me` works).
- **DNS**: both hostnames must resolve to the server. For a quick test, add to
  `C:\Windows\System32\drivers\etc\hosts`:
  ```
  <server-ip>   app.credit-plus.me
  <server-ip>   api.credit-plus.me
  ```
- **PostgreSQL** reachable at `localhost:5433` (hardcoded in `db.py` — edit it if your DB is elsewhere).

---

## Option A — Scripted (recommended)

1. Copy the `publish` folder to the server (e.g. extract `CP_BOT_publish.zip`).
2. Create `backend\.env` from `backend\.env.example` and set a real `OPENAI_API_KEY`.
3. Open **PowerShell as Administrator** in the `publish` folder and run:
   ```powershell
   # wildcard PFX on disk:
   .\Setup-Server.ps1 -Domain credit-plus.me -PfxPath C:\certs\wildcard.pfx

   # ...or a cert already imported into LocalMachine\My:
   .\Setup-Server.ps1 -Domain credit-plus.me -CertThumbprint <THUMBPRINT>
   ```
   Add `-InstallRoot D:\sites\cpbot` to deploy somewhere other than `C:\inetpub\cpbot`.
   Add `-StopDefaultSite` if the IIS "Default Web Site" holds port 80.

The script copies files, builds the venv, stamps `web.config`, installs the IIS modules, imports the
cert, and creates both sites/app pools/bindings/permissions. Done.

---

## Option B — Manual (IIS Manager)

Assume you copy the folders to `C:\inetpub\cpbot\frontend` and `C:\inetpub\cpbot\backend`.

### 1. Install the IIS modules (once per server)
- **URL Rewrite 2.1** — https://www.iis.net/downloads/microsoft/url-rewrite
- **HttpPlatformHandler 1.2** — https://www.iis.net/downloads/microsoft/httpplatformhandler

### 2. Backend Python setup
```powershell
cd C:\inetpub\cpbot\backend
py -m venv .venv          # if 'py' is not recognized, use:  python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env      # then edit .env and set OPENAI_API_KEY
```
Open `backend\web.config` and replace both `C:\inetpub\cpbot\backend` paths with your actual backend
folder if it differs.

### 3. Frontend site
- IIS Manager → **Sites → Add Website**
  - Site name: `CP_BOT_Frontend`
  - Physical path: `C:\inetpub\cpbot\frontend`
  - Binding: **https**, port **443**, host name `app.credit-plus.me`, **Require SNI**, select your cert
- Add a second binding: **http** port **80**, host `app.credit-plus.me` (the bundled web.config redirects http→https).
- App pool for this site: **.NET CLR version = No Managed Code**.

### 4. Backend site
- **Sites → Add Website**
  - Site name: `CP_BOT_Backend`
  - Physical path: `C:\inetpub\cpbot\backend`
  - Binding: **https**, port **443**, host name `api.credit-plus.me`, **Require SNI**, select your cert
- App pool: **No Managed Code** (Python runs via HttpPlatformHandler, not .NET).

### 5. Permissions
Grant each site's app pool identity access (replace pool names if different):
```powershell
icacls C:\inetpub\cpbot\backend  /grant "IIS AppPool\CP_BOT_Backend:(OI)(CI)(RX)" /T
icacls C:\inetpub\cpbot\backend\uploads /grant "IIS AppPool\CP_BOT_Backend:(OI)(CI)(M)" /T
icacls C:\inetpub\cpbot\backend\logs    /grant "IIS AppPool\CP_BOT_Backend:(OI)(CI)(M)" /T
icacls C:\inetpub\cpbot\frontend /grant "IIS AppPool\CP_BOT_Frontend:(OI)(CI)(RX)" /T
```

### 6. Start & verify
```powershell
curl.exe -k https://api.credit-plus.me/health     # -> {"status":"ok"}
start https://app.credit-plus.me
```

---

## Updating later
- **Frontend change:** rebuild on a dev machine (`npm run build`), re-run `Make-Package.ps1`, copy the new
  `frontend\` over the server's, done (static — no restart).
- **Backend change:** copy changed `.py` files, then `Restart-WebAppPool CP_BOT_Backend`. If
  `requirements.txt` changed: `.\.venv\Scripts\python -m pip install -r requirements.txt` then restart the pool.

## Troubleshooting
| Symptom | Fix |
|---|---|
| Backend `502.3`/`500.19` | HttpPlatformHandler not installed, or app pool isn't "No Managed Code". |
| Backend won't start, log shows OpenAI error | `.env` missing / bad `OPENAI_API_KEY`. Log: `backend\logs\backend-stdout*.log`. |
| Backend log: DB connection refused | PostgreSQL not at `localhost:5433` — fix `db.py`. |
| Deep-link refresh → 404 | URL Rewrite module not installed. |
| CORS error in browser | Frontend host isn't `https://app.credit-plus.me` (would need a backend rebuild of `allow_origins`). |
| Cert/SNI warning | The bound cert doesn't cover the host. |
