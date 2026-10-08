[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('(?i)^[0-9a-f]{40}$')]
    [string]$Commit,

    [string]$SshHost = 'ubuntu@141.94.224.49',

    [string]$SshKeyPath = (Join-Path $HOME '.ssh\sklep-vps')
)

$ErrorActionPreference = 'Stop'
$repository = 'michalantczak10/sklepzdoniczkami'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$null = Set-Location -LiteralPath $repositoryRoot
$Commit = $Commit.ToLowerInvariant()

if (-not (Test-Path -LiteralPath $SshKeyPath -PathType Leaf)) {
    throw "SSH key not found at $SshKeyPath."
}
foreach ($command in @('git', 'gh', 'ssh')) {
    if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
        throw "$command is required."
    }
}

$null = & git fetch --quiet origin "refs/heads/main:refs/remotes/origin/main"
if ($LASTEXITCODE -ne 0) {
    throw 'Could not fetch origin/main.'
}

$null = & git merge-base --is-ancestor $Commit 'origin/main'
if ($LASTEXITCODE -ne 0) {
    throw "Commit $Commit is not reachable from origin/main."
}

$checksJson = & gh api "repos/$repository/commits/$Commit/check-runs?per_page=100"
if ($LASTEXITCODE -ne 0) {
    throw "Could not read GitHub check runs for $Commit."
}
$checkRuns = $checksJson | ConvertFrom-Json
foreach ($requiredCheck in @(
    'Django tests',
    'End-to-end tests (Playwright)',
    'PostgreSQL tests'
)) {
    $latestCheck = $checkRuns.check_runs |
        Where-Object { $_.name -eq $requiredCheck } |
        Sort-Object -Property started_at |
        Select-Object -Last 1
    if (-not $latestCheck -or $latestCheck.conclusion -ne 'success') {
        throw "Required check '$requiredCheck' has not succeeded for $Commit."
    }
}

$installerContents = & git show "$($Commit):scripts/install_ovh_backup.sh"
if ($LASTEXITCODE -ne 0) {
    throw "Commit $Commit does not contain scripts/install_ovh_backup.sh."
}
$payload = [Convert]::ToBase64String(
    [Text.Encoding]::UTF8.GetBytes([string]::Join("`n", $installerContents))
)
$remoteCommand = "echo $payload | base64 -d | sudo -n bash -s -- $Commit"
& ssh -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=yes `
    -i $SshKeyPath $SshHost $remoteCommand
if ($LASTEXITCODE -ne 0) {
    throw "Backup tooling installation failed with exit code $LASTEXITCODE."
}
