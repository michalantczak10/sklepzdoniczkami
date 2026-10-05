param(
    [string]$PostgreSqlBin = "C:\Program Files\PostgreSQL\18\bin",
    [int]$Port = 5435
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$localRoot = Join-Path $env:LOCALAPPDATA "Sklepzdoniczkami"
$dataDirectory = Join-Path $localRoot "postgresql"
$logFile = Join-Path $localRoot "postgresql.log"
$envFile = Join-Path $localRoot ".env.selfhost"
$python = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
$waitress = Join-Path $repositoryRoot ".venv\Scripts\waitress-serve.exe"
$pgCtl = Join-Path $PostgreSqlBin "pg_ctl.exe"

if (-not (Test-Path $envFile)) {
    throw "Run scripts\setup_windows_selfhost.ps1 first to create a private local configuration."
}
if (-not (Test-Path $python) -or -not (Test-Path $waitress) -or -not (Test-Path $pgCtl)) {
    throw "Install the project requirements in .venv before starting the local server."
}

& $pgCtl -D $dataDirectory status
if ($LASTEXITCODE -ne 0) {
    & $pgCtl -D $dataDirectory -l $logFile -o "-h 127.0.0.1 -p $Port" -w start
    if ($LASTEXITCODE -ne 0) {
        throw "The isolated local PostgreSQL database could not be started."
    }
}

$env:DJANGO_ENV_FILE = $envFile
$env:DJANGO_SETTINGS_MODULE = "config.settings"

$databaseTarget = @'
import os
import django
django.setup()
from django.conf import settings
database = settings.DATABASES["default"]
expected_port = os.environ["SELFHOST_POSTGRES_PORT"]
if database["ENGINE"] != "django.db.backends.postgresql":
    raise SystemExit("Refusing to start: expected the isolated PostgreSQL database.")
expected_names = {
    "development": "sklepzdoniczkami_dev",
    "production": "sklepzdoniczkami_prod",
}
expected_name = expected_names.get(settings.APP_ENV)
if expected_name is None:
    raise SystemExit("Refusing to start: unsupported local environment.")
if (
    database["HOST"] not in ("127.0.0.1", "localhost")
    or str(database["PORT"]) != expected_port
    or database["NAME"] != expected_name
    or database["USER"] != expected_name
):
    raise SystemExit("Refusing to start: the configured database is not the expected isolated local target.")
print(f"Verified isolated local PostgreSQL target: {expected_name} on loopback.")
'@
$env:SELFHOST_POSTGRES_PORT = "$Port"
try {
    $databaseTarget | & $python -
    $targetCheckExitCode = $LASTEXITCODE
}
finally {
    Remove-Item Env:SELFHOST_POSTGRES_PORT -ErrorAction SilentlyContinue
}
if ($targetCheckExitCode -ne 0) {
    throw "Local database safety check failed."
}

& $python (Join-Path $repositoryRoot "manage.py") migrate --noinput
if ($LASTEXITCODE -ne 0) {
    throw "Database migrations failed."
}

& $python (Join-Path $repositoryRoot "manage.py") collectstatic --noinput
if ($LASTEXITCODE -ne 0) {
    throw "Static file collection failed."
}

& $waitress --listen=127.0.0.1:8000 config.wsgi:application
