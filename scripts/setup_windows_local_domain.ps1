param(
    [ValidateSet("Install", "Refresh", "Remove")]
    [string]$Mode = "Install",
    [string]$CertificatePath = ""
)

$ErrorActionPreference = "Stop"
$startMarker = "# BEGIN sklepzdoniczkami local WSL override"
$endMarker = "# END sklepzdoniczkami local WSL override"
$hostsPath = Join-Path $env:windir "System32\drivers\etc\hosts"
$hostsBackup = "$hostsPath.sklepzdoniczkami.backup"

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run this script from PowerShell opened with 'Run as administrator'."
}

function Get-WslGuestIPv4 {
    $wslExecutable = Join-Path $env:windir "System32\wsl.exe"
    $addresses = & $wslExecutable --distribution Ubuntu-24.04 --exec hostname -I
    if ($LASTEXITCODE -ne 0) {
        throw "Could not start Ubuntu-24.04 to determine its current WSL address."
    }
    $address = $addresses -split "\s+" |
        Where-Object { $_ -match '^(?:\d{1,3}\.){3}\d{1,3}$' -and $_ -notlike "127.*" } |
        Select-Object -First 1
    if (-not $address) {
        throw "Ubuntu-24.04 did not report a usable IPv4 address."
    }
    return $address
}

function Update-HostsBlock {
    param([switch]$RequireExisting)

    $reader = [System.IO.StreamReader]::new($hostsPath, $true)
    $text = $reader.ReadToEnd()
    $encoding = $reader.CurrentEncoding
    $reader.Dispose()

    $hasStart = $text.Contains($startMarker)
    $hasEnd = $text.Contains($endMarker)
    if ($hasStart -ne $hasEnd) {
        throw "The local-shop hosts block is incomplete; inspect the hosts file manually."
    }
    if ($RequireExisting -and -not $hasStart) {
        throw "No local-shop hosts block exists; run with -Mode Install first."
    }

    $address = Get-WslGuestIPv4
    $block = "$startMarker`r`n$address sklepzdoniczkami.pl www.sklepzdoniczkami.pl`r`n$endMarker"
    if ($hasStart) {
        $pattern = [regex]::Escape($startMarker) + '(?s).*?' + [regex]::Escape($endMarker)
        $text = [regex]::Replace($text, $pattern, $block)
    }
    else {
        $text = $text.TrimEnd("`r", "`n")
        if ($text.Length -gt 0) { $text += "`r`n" }
        $text += $block
    }

    [System.IO.File]::WriteAllText($hostsPath, ($text.TrimEnd("`r", "`n") + "`r`n"), $encoding)
    Clear-DnsClientCache
    Write-Output "Local hosts mapping now targets WSL address $address."
}

if ($Mode -eq "Install") {
    if (-not (Test-Path -LiteralPath $CertificatePath -PathType Leaf)) {
        throw "Provide the WSL Caddy root certificate with -CertificatePath."
    }
    $hostsText = [System.IO.File]::ReadAllText($hostsPath)
    if ($hostsText.Contains($startMarker) -ne $hostsText.Contains($endMarker)) {
        throw "The local-shop hosts block is incomplete; inspect the hosts file manually."
    }

    $certificate = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new(
        (Resolve-Path -LiteralPath $CertificatePath).Path
    )
    $basicConstraints = $certificate.Extensions |
        Where-Object { $_.Oid.Value -eq "2.5.29.19" }
    if (-not $basicConstraints -or
        -not ([System.Security.Cryptography.X509Certificates.X509BasicConstraintsExtension]$basicConstraints).CertificateAuthority -or
        $certificate.Subject -notmatch "^CN=Caddy Local Authority - .+ Root$") {
        throw "The certificate is not Caddy's local root CA; refusing to trust it."
    }
    $trustedRoot = Get-ChildItem Cert:\CurrentUser\Root |
        Where-Object Thumbprint -eq $certificate.Thumbprint
    $certificateAdded = $false
    if (-not $trustedRoot) {
        Import-Certificate -FilePath $CertificatePath -CertStoreLocation Cert:\CurrentUser\Root |
            Out-Null
        $certificateAdded = $true
    }

    try {
        if (-not (Test-Path -LiteralPath $hostsBackup)) {
            Copy-Item -LiteralPath $hostsPath -Destination $hostsBackup
        }
        Update-HostsBlock
        Write-Output "Local-only domain override installed. Public DNS was not changed."
    }
    catch {
        if ($certificateAdded) {
            Remove-Item -LiteralPath "Cert:\CurrentUser\Root\$($certificate.Thumbprint)"
        }
        throw
    }
    return
}

if ($Mode -eq "Refresh") {
    Update-HostsBlock -RequireExisting
    return
}

$reader = [System.IO.StreamReader]::new($hostsPath, $true)
$contentText = $reader.ReadToEnd()
$encoding = $reader.CurrentEncoding
$reader.Dispose()
$start = $contentText.IndexOf($startMarker, [System.StringComparison]::Ordinal)
$end = $contentText.IndexOf($endMarker, [System.StringComparison]::Ordinal)
if ($start -lt 0 -and $end -lt 0) {
    Write-Output "No local-shop hosts override was found."
    return
}
if ($start -lt 0 -or $end -lt $start) {
    throw "The local-shop hosts block is incomplete; inspect the hosts file manually."
}
$end += $endMarker.Length
$remaining = $contentText.Remove($start, $end - $start).TrimEnd("`r", "`n")
[System.IO.File]::WriteAllText(
    $hostsPath,
    ($remaining + "`r`n"),
    $encoding
)
Clear-DnsClientCache

if ($CertificatePath -and (Test-Path -LiteralPath $CertificatePath -PathType Leaf)) {
    $certificate = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new(
        (Resolve-Path -LiteralPath $CertificatePath).Path
    )
    $trustedRootPath = "Cert:\CurrentUser\Root\$($certificate.Thumbprint)"
    if (Test-Path -LiteralPath $trustedRootPath) {
        Remove-Item -LiteralPath $trustedRootPath
    }
}
Write-Output "Local-only domain override removed. Public DNS was not changed."
