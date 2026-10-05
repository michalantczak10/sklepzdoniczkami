# Self-hosting on Windows 11

This project can run on a Windows 11 computer with a local PostgreSQL database.
The initial setup below creates a separate PostgreSQL 18 instance on
`127.0.0.1:5435`; it does not change the existing PostgreSQL Windows service,
Neon, Render, DNS, or router settings.

## Prepare a local test copy

Install Python and PostgreSQL 18, then from the repository root run:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\scripts\setup_windows_selfhost.ps1
```

The setup script creates a private development database and stores its
credentials under `%LOCALAPPDATA%\Sklepzdoniczkami`, outside Git. It binds the
project database to loopback only. The existing `.env` is not read or changed.

To create the separate production database on the dedicated laptop instead,
use `.\scripts\setup_windows_selfhost.ps1 -Environment production`. This creates
`sklepzdoniczkami_prod`; its private environment file uses
`APP_ENV=production` and requires the public domain to be served over HTTPS.

Start the application with:

```powershell
.\scripts\run_windows_selfhost.ps1
```

This checks that Django is using the local PostgreSQL development database,
applies migrations, collects static files, and starts Waitress on
`127.0.0.1:8000`. Open `http://127.0.0.1:8000/` on that computer. The initial
database is empty; production data must be copied separately before it can show
the live catalog or order history.

To create the first local copy of the current production database, run:

```powershell
.\.venv\Scripts\python.exe scripts\clone_render_production_to_local.py --confirm-empty-local-target
```

This reads the production database URL from the Render service using the
existing local `RENDER_API_KEY`, takes a private snapshot under
`%LOCALAPPDATA%\Sklepzdoniczkami\migration`, and restores it only to the empty,
loopback-only development database. It refuses to overwrite a snapshot or a
target containing users or orders. The snapshot contains production data and
must never be committed or copied to a public location. This initial snapshot
is not the final cutover copy; repeat the export during the planned cutover to
include later orders.

## Move the setup to the dedicated laptop

Clone or pull the repository on the laptop and run the same setup steps there.
Git transfers source code only. It must not contain the private environment
file, database credentials, PostgreSQL data directory, production database
dump, or uploaded media. Those items need a separate, protected transfer.

Keep the current Render site and Neon database unchanged until the laptop has a
verified PostgreSQL restore, media files, working admin login, and tested
checkout configuration. Do not run two writable production copies against
different databases during cutover.

## Public access

The local test server is deliberately bound to loopback and is not public.
Public production hosting requires a reverse proxy with HTTPS, firewall and
router rules for TCP ports 80/443, a domain DNS record, and a public routable IP.
Before opening ports, verify that Play has not placed the connection behind
CGNAT. A changing public IP additionally requires dynamic DNS. Stripe webhooks
and password-reset email delivery must be reconfigured for the final hostname;
both remain external providers unless replaced.

`Caddyfile.example` is the reverse-proxy configuration for the production
hostname. Caddy can obtain and renew HTTPS certificates automatically after
the domain points to the home IP and ports 80/443 reach the laptop. Expose only
ports 80/443 publicly; keep PostgreSQL `5435` and Waitress `8000` bound to
loopback. Configure Task Scheduler to start the PostgreSQL/Waitress script and
Caddy at boot, with restart-on-failure enabled. Do not point the public domain
at the current development computer.
