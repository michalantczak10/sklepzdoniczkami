param(
    [ValidateSet("Install", "Remove")]
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

if ($Mode -eq "Install") {
    if (-not (Test-Path -LiteralPath $CertificatePath -PathType Leaf)) {
        throw "Provide the WSL Caddy root certificate with -CertificatePath."
    }
    $hostsContent = Get-Content -LiteralPath $hostsPath
    if ($hostsContent -contains $startMarker -or $hostsContent -contains $endMarker) {
        throw "A local-shop hosts block already exists; refusing to add a duplicate."
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
        @(
            $startMarker
            "127.0.0.1 sklepzdoniczkami.pl www.sklepzdoniczkami.pl"
            $endMarker
        ) | Add-Content -LiteralPath $hostsPath -Encoding ascii
        Clear-DnsClientCache
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

$reader = [System.IO.StreamReader]::new($hostsPath, $true)
$contentText = $reader.ReadToEnd()
$encoding = $reader.CurrentEncoding
$reader.Dispose()
$content = $contentText -split "\r?\n"
$start = [Array]::IndexOf($content, $startMarker)
$end = [Array]::IndexOf($content, $endMarker)
if ($start -lt 0 -and $end -lt 0) {
    Write-Output "No local-shop hosts override was found."
    return
}
if ($start -lt 0 -or $end -lt $start) {
    throw "The local-shop hosts block is incomplete; inspect the hosts file manually."
}
$remaining = @()
if ($start -gt 0) { $remaining += $content[0..($start - 1)] }
if ($end -lt ($content.Length - 1)) { $remaining += $content[($end + 1)..($content.Length - 1)] }
[System.IO.File]::WriteAllText(
    $hostsPath,
    (($remaining -join "`r`n").TrimEnd("`r", "`n") + "`r`n"),
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
