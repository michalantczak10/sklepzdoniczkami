[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('development', 'preprod', 'production')]
    [string]$Environment,

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
$sourceBranch = if ($Environment -eq 'development') { 'dev' } else { 'main' }
$Commit = $Commit.ToLowerInvariant()

if (-not (Test-Path -LiteralPath $SshKeyPath -PathType Leaf)) {
    throw "SSH key not found at $SshKeyPath."
}
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw 'Git is required.'
}
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw 'GitHub CLI is required to verify the required CI checks.'
}
if (-not (Get-Command ssh -ErrorAction SilentlyContinue)) {
    throw 'OpenSSH client is required.'
}

$null = & git fetch --quiet origin "refs/heads/${sourceBranch}:refs/remotes/origin/${sourceBranch}"
if ($LASTEXITCODE -ne 0) {
    throw "Could not fetch origin/$sourceBranch."
}

$null = & git merge-base --is-ancestor $Commit "origin/$sourceBranch"
if ($LASTEXITCODE -ne 0) {
    throw "Commit $Commit is not reachable from origin/$sourceBranch."
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

$scriptContents = & git show "$($Commit):scripts/deploy_ovh.sh"
if ($LASTEXITCODE -ne 0) {
    throw "Commit $Commit does not contain scripts/deploy_ovh.sh."
}
$payload = [Convert]::ToBase64String(
    [Text.Encoding]::UTF8.GetBytes([string]::Join("`n", $scriptContents))
)
$remoteCommand = "echo $payload | base64 -d | sudo -n bash -s -- $Environment $Commit"
& ssh -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=yes `
    -i $SshKeyPath $SshHost $remoteCommand
if ($LASTEXITCODE -ne 0) {
    throw "Deployment to $Environment failed with exit code $LASTEXITCODE."
}
