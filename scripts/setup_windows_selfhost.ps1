param(
    [string]$PostgreSqlBin = "C:\Program Files\PostgreSQL\18\bin",
    [int]$Port = 5435,
    [ValidateSet("development", "production")]
    [string]$Environment = "development"
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$localRoot = Join-Path $env:LOCALAPPDATA "Sklepzdoniczkami"
$dataDirectory = Join-Path $localRoot "postgresql"
$logFile = Join-Path $localRoot "postgresql.log"
$envFile = Join-Path $localRoot ".env.selfhost"
$adminPasswordFile = Join-Path $localRoot "postgres_admin_password.txt"
$initdb = Join-Path $PostgreSqlBin "initdb.exe"
$pgCtl = Join-Path $PostgreSqlBin "pg_ctl.exe"
$psql = Join-Path $PostgreSqlBin "psql.exe"
$environmentSuffix = $Environment.ToUpperInvariant()
if ($Environment -eq "production") {
    $databaseName = "sklepzdoniczkami_prod"
    $debug = "False"
    $allowedHosts = "sklepzdoniczkami.pl,www.sklepzdoniczkami.pl,localhost,127.0.0.1"
    $csrfOrigins = "https://sklepzdoniczkami.pl,https://www.sklepzdoniczkami.pl"
    $siteUrl = "https://sklepzdoniczkami.pl"
}
else {
    $databaseName = "sklepzdoniczkami_dev"
    $debug = "True"
    $allowedHosts = "localhost,127.0.0.1"
    $csrfOrigins = "http://localhost,http://127.0.0.1"
    $siteUrl = "http://127.0.0.1:8000"
}

foreach ($tool in @($initdb, $pgCtl, $psql)) {
    if (-not (Test-Path $tool)) {
        throw "PostgreSQL tool not found: $tool"
    }
}

function New-RandomHex {
    param([int]$ByteCount = 32)

    $bytes = New-Object byte[] $ByteCount
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $generator.GetBytes($bytes)
    }
    finally {
        $generator.Dispose()
    }
    return [BitConverter]::ToString($bytes).Replace("-", "").ToLowerInvariant()
}

New-Item -ItemType Directory -Path $localRoot -Force | Out-Null

if (Test-Path (Join-Path $dataDirectory "PG_VERSION")) {
    if (-not (Test-Path $envFile) -or -not (Test-Path $adminPasswordFile)) {
        throw "Existing local database found, but its private configuration is missing. No files were changed."
    }

    & $pgCtl -D $dataDirectory status
    if ($LASTEXITCODE -ne 0) {
        & $pgCtl -D $dataDirectory -l $logFile -o "-h 127.0.0.1 -p $Port" -w start
        if ($LASTEXITCODE -ne 0) {
            throw "Could not start the existing local PostgreSQL instance."
        }
    }
    Write-Output "The private local PostgreSQL instance is ready on 127.0.0.1:$Port."
    return
}

if (Test-Path $envFile) {
    throw "The private environment file already exists but the local database does not. Refusing to overwrite either."
}

if ((Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) -or
    (Test-Path $dataDirectory)) {
    throw "The target port or data directory is already in use. No existing database was changed."
}

New-Item -ItemType Directory -Path $dataDirectory -Force | Out-Null
$adminPassword = New-RandomHex
$appPassword = New-RandomHex
$djangoSecret = New-RandomHex
$pwFile = Join-Path $localRoot "initdb-password.tmp"
$sqlFile = Join-Path $localRoot "create-app-database.tmp.sql"
$connectionUrl = "postgresql://${databaseName}:${appPassword}@127.0.0.1:${Port}/${databaseName}"
$mediaDirectory = (Join-Path $localRoot "media").Replace("\", "/")

try {
    [System.IO.File]::WriteAllText($pwFile, $adminPassword, [System.Text.Encoding]::ASCII)
    & $initdb `
        -D $dataDirectory `
        -U postgres `
        "--pwfile=$pwFile" `
        --encoding=UTF8 `
        --locale=C `
        --auth-local=scram-sha-256 `
        --auth-host=scram-sha-256
    if ($LASTEXITCODE -ne 0) {
        throw "PostgreSQL initialization failed."
    }

    Add-Content -LiteralPath (Join-Path $dataDirectory "postgresql.conf") `
        -Value "`nlisten_addresses = '127.0.0.1'`nport = $Port" `
        -Encoding ASCII

    & $pgCtl -D $dataDirectory -l $logFile -o "-h 127.0.0.1 -p $Port" -w start
    if ($LASTEXITCODE -ne 0) {
        throw "The local PostgreSQL instance did not start."
    }

    $sql = @"
CREATE ROLE $databaseName LOGIN PASSWORD '$appPassword';
CREATE DATABASE $databaseName OWNER $databaseName;
"@
    [System.IO.File]::WriteAllText($sqlFile, $sql, [System.Text.Encoding]::ASCII)

    $env:PGPASSWORD = $adminPassword
    & $psql `
        -h 127.0.0.1 `
        -p $Port `
        -U postgres `
        -d postgres `
        -v ON_ERROR_STOP=1 `
        -f $sqlFile
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create the local application database."
    }
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue

    $environment = @"
APP_ENV=$Environment
DATABASE_NAME_$environmentSuffix=$databaseName
DATABASE_URL_$environmentSuffix=$connectionUrl
DJANGO_SECRET_KEY_$environmentSuffix=$djangoSecret
DEBUG=$debug
ALLOWED_HOSTS=$allowedHosts
CSRF_TRUSTED_ORIGINS=$csrfOrigins
SITE_NAME=Sklepzdoniczkami
SITE_URL=$siteUrl
MEDIA_ROOT=$mediaDirectory
"@
    if ($Environment -eq "development") {
        $environment += "`nEMAIL_BACKEND=django.core.mail.backends.console.EmailBackend"
    }
    [System.IO.File]::WriteAllText(
        $envFile,
        $environment,
        (New-Object System.Text.UTF8Encoding($false))
    )
    [System.IO.File]::WriteAllText(
        $adminPasswordFile,
        $adminPassword,
        [System.Text.Encoding]::ASCII
    )

    Write-Output "Created a separate $Environment PostgreSQL database, listening only on 127.0.0.1:$Port."
    Write-Output "Private credentials were saved under LocalAppData; the VPS and domain DNS were not changed."
}
finally {
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    Remove-Item $pwFile, $sqlFile -Force -ErrorAction SilentlyContinue
}
