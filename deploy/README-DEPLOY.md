# Publishing CP_BOT to IIS

Two IIS sites on this Windows server:

| Site                 | URL                       | Physical path                              | How it runs |
|----------------------|---------------------------|--------------------------------------------|-------------|
| Frontend (Angular)   | `https://app.<domain>`    | `frontend\dist\frontend\browser`           | Static files + URL Rewrite (SPA routing) |
| Backend (FastAPI)    | `https://api.<domain>`    | `C:\Work\CP_BOT`                           | HttpPlatformHandler launches `.venv\Scripts\python.exe -m uvicorn main:app` |

IIS cannot run Python directly. For the backend, the **HttpPlatformHandler** module starts Uvicorn on a private localhost port and IIS reverse-proxies HTTPS traffic to it. The frontend is plain static hosting with a SPA fallback rule.

---

## Prerequisites

- Windows with admin rights (the install script must run elevated).
- **Python** available as `py` (used to build the venv) — already done: `.venv` is created.
- **Node.js** (for building the frontend) — already installed.
- **PostgreSQL** reachable at `localhost:5433` (the connection string is hardcoded in `db.py`).
- A **TLS certificate** covering `app.<domain>` and `api.<domain>` (a wildcard `*.<domain>` works for both).
- **DNS**: `app.<domain>` and `api.<domain>` must resolve to this server. For local testing, add entries to
  `C:\Windows\System32\drivers\etc\hosts`:
  ```
  127.0.0.1   app.<domain>
  127.0.0.1   api.<domain>
  ```

---

## One-time setup steps

### 1. Backend environment file
Copy `.env.example` to `.env` (in `C:\Work\CP_BOT`, next to `main.py`) and set a real key:
```
OPENAI_API_KEY=sk-...
```
The backend imports the OpenAI client at startup and **will not start without this**.

### 2. Confirm the API URL + CORS (already wired for your domain)
- `frontend/src/environments/environment.ts` -> `apiBaseUrl: 'https://api.<domain>'`
- `main.py` CORS `allow_origins` includes `https://app.<domain>`

### 3. Build the frontend
**Node version matters:** Angular 22 needs Node `v22.22.3+`, `v24.15.0+`, or `v26+`. The machine's
default Node (v24.14.1) is too old, so use the nvm-installed Node 22 LTS for the build:
```powershell
cd C:\Work\CP_BOT\frontend
$env:Path = "C:\Users\mathk\AppData\Local\nvm\v22.22.3;" + $env:Path   # use a compliant Node for this shell
npm run build
```
(Or permanently: run `nvm use 22.22.3` in an elevated shell, or upgrade the standalone Node.)
Output lands in `frontend\dist\frontend\browser` (the `web.config` from `frontend\public` is copied in automatically).

### 4. Run the IIS installer (elevated)
Open an **Administrator** PowerShell:
```powershell
cd C:\Work\CP_BOT\deploy

# If you have a wildcard PFX:
.\Install-IIS.ps1 -Domain <domain> -PfxPath C:\path\to\cert.pfx

# Or if the cert is already imported into LocalMachine\My:
.\Install-IIS.ps1 -Domain <domain> -CertThumbprint <THUMBPRINT>
```
The script enables IIS features, installs URL Rewrite + HttpPlatformHandler, imports the cert, and creates both
sites/app pools/bindings with the right filesystem permissions.

> If it reports a pending reboot after enabling IIS features, reboot and run it again.

---

## Verify

```powershell
# Backend (through IIS):
curl.exe -k https://api.<domain>/health      # -> {"status":"ok"}

# Frontend:
start https://app.<domain>
```
Backend startup output: `C:\Work\CP_BOT\logs\backend-stdout*.log`.

---

## Updating after code changes

- **Frontend:** `cd frontend; npm run build` (no IIS restart needed — static files).
- **Backend:** restart the app pool so Uvicorn relaunches:
  ```powershell
  Restart-WebAppPool CP_BOT_Backend
  ```
  If you add Python packages: `.\.venv\Scripts\python -m pip install -r requirements.txt`, then restart the pool.

---

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| Backend 502.3 / 500.19 | HttpPlatformHandler not installed, or app pool isn't "No Managed Code". Re-run the installer. |
| Backend won't start, log shows OpenAI error | `.env` missing or `OPENAI_API_KEY` invalid. |
| Backend log shows DB connection refused | PostgreSQL not running / not on `localhost:5433`. |
| Frontend deep links 404 on refresh | URL Rewrite module missing (SPA fallback rule can't run). |
| CORS errors in browser console | `main.py` `allow_origins` doesn't match `https://app.<domain>`. |
| Cert warning / wrong cert | Thumbprint/PFX doesn't cover the host; check `Install-IIS.ps1` output. |
| Uploads fail to save | App pool lacks write on `.\uploads` (installer grants this; re-run if needed). |
