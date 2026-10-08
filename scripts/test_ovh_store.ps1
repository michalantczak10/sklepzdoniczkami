[CmdletBinding()]
param(
    [ValidateSet('development', 'preprod', 'both')]
    [string]$Environment = 'both',

    [string]$SshHost = 'ubuntu@141.94.224.49',

    [string]$SshKeyPath,

    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'
$targets = @{
    development = @{
        Port = 8001
        Name = 'Development'
    }
    preprod = @{
        Port = 8002
        Name = 'Preprod'
    }
}
$selectedTargets = if ($Environment -eq 'both') {
    @('development', 'preprod')
} else {
    @($Environment)
}

if (-not $SshKeyPath) {
    $keyCandidates = @(
        (Join-Path $HOME '.ssh\sklep-vps'),
        (Join-Path $HOME '.ssh\sklepzdoniczkami_ovh_ed25519')
    )
    $SshKeyPath = $keyCandidates |
        Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
        Select-Object -First 1
}
if (-not $SshKeyPath -or -not (Test-Path -LiteralPath $SshKeyPath -PathType Leaf)) {
    throw 'SSH key not found. Pass -SshKeyPath with the key used for the OVH VPS.'
}

$sshCommand = Get-Command ssh.exe -ErrorAction SilentlyContinue
if (-not $sshCommand) {
    throw 'OpenSSH client (ssh.exe) is required.'
}
$curlCommand = Get-Command curl.exe -ErrorAction SilentlyContinue
if (-not $curlCommand) {
    throw 'curl.exe is required to check the store before opening it.'
}

foreach ($target in $selectedTargets) {
    $port = $targets[$target].Port
    if (Test-NetConnection -ComputerName 127.0.0.1 -Port $port `
            -InformationLevel Quiet -WarningAction SilentlyContinue) {
        throw "Local port $port is already in use. Close the existing SSH tunnel and try again."
    }
}

$sshArguments = @(
    '-N',
    '-T',
    '-o', 'BatchMode=yes',
    '-o', 'ConnectTimeout=10',
    '-o', 'ExitOnForwardFailure=yes',
    '-o', 'StrictHostKeyChecking=yes',
    '-i', "`"$SshKeyPath`""
)
foreach ($target in $selectedTargets) {
    $port = $targets[$target].Port
    $sshArguments += @('-L', "${port}:127.0.0.1:${port}")
}
$sshArguments += $SshHost

$sshProcess = $null
try {
    $sshProcess = Start-Process -FilePath $sshCommand.Source `
        -ArgumentList $sshArguments -WindowStyle Hidden -PassThru

    foreach ($target in $selectedTargets) {
        $port = $targets[$target].Port
        $url = "https://localhost:$port/"
        $healthy = $false

        for ($attempt = 0; $attempt -lt 30; $attempt++) {
            $sshProcess.Refresh()
            if ($sshProcess.HasExited) {
                throw "SSH tunnel stopped unexpectedly (exit code $($sshProcess.ExitCode))."
            }

            $status = & $curlCommand.Source -k -sS --max-time 5 `
                -o NUL -w '%{http_code}' $url 2>$null
            if ($LASTEXITCODE -eq 0 -and "$status".Trim() -eq '200') {
                $healthy = $true
                break
            }
            Start-Sleep -Seconds 1
        }

        if (-not $healthy) {
            throw "$($targets[$target].Name) did not return HTTP 200 at $url."
        }

        if ($CheckOnly) {
            Write-Host "$($targets[$target].Name): HTTP 200 - $url"
        } else {
            Write-Host "$($targets[$target].Name): HTTP 200 - opening $url"
            Start-Process -FilePath $url
        }
    }

    if (-not $CheckOnly) {
        Write-Host ''
        Write-Host 'The SSH tunnel is active. The browser may warn about the self-signed localhost certificate.'
        Write-Host 'Only continue past that warning for localhost. Press Enter here to close the tunnel.'
        $null = Read-Host
    }
}
finally {
    if ($sshProcess) {
        $sshProcess.Refresh()
        if (-not $sshProcess.HasExited) {
            Stop-Process -Id $sshProcess.Id -Force
        }
    }
}
