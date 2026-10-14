#Requires -Version 7.2
[CmdletBinding(SupportsShouldProcess, ConfirmImpact='Medium')]
param(
    [Parameter(Mandatory)][string]$ImageDigest,
    [Parameter(Mandatory)][string]$PrivateKey,
    [Parameter(Mandatory)][string]$PublicKey,
    [Parameter(Mandatory)][string]$PasswordFile,
    [Parameter(Mandatory)][string]$OutputDirectory,
    [string]$Cosign = 'cosign'
)
# Signing publishes a signature and potentially a transparency-log record.
# The receiving unit must separately approve this public key/trust policy.
$ErrorActionPreference = 'Stop'
if ($ImageDigest -notmatch '^dang7904/storage-lab-console@sha256:[a-f0-9]{64}$') { throw 'Exact authorized Docker Hub repository digest required' }
foreach ($file in @($PrivateKey,$PublicKey,$PasswordFile)) { if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw 'Signing key/password file unavailable' } }
$cosignCommand = Get-Command $Cosign -ErrorAction Stop
$outputPath = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $outputPath) { throw 'Refusing to replace an existing signature verification receipt' }
if (-not $PSCmdlet.ShouldProcess($ImageDigest,'Publish image signature and verify using approved public key')) { return }
New-Item -ItemType Directory -Path $outputPath | Out-Null
$previousPassword = [Environment]::GetEnvironmentVariable('COSIGN_PASSWORD','Process')
try {
    $secret = [IO.File]::ReadAllText((Resolve-Path -LiteralPath $PasswordFile).Path).TrimEnd("`r","`n")
    if (-not $secret -or $secret.Length -gt 4096) { throw 'Invalid signing password file' }
    [Environment]::SetEnvironmentVariable('COSIGN_PASSWORD',$secret,'Process')
    & $cosignCommand.Source sign --yes --key (Resolve-Path -LiteralPath $PrivateKey).Path $ImageDigest *> (Join-Path $outputPath 'sign.log')
    if ($LASTEXITCODE -ne 0) { throw 'Image signing failed; no release acceptance is implied' }
    & $cosignCommand.Source verify --key (Resolve-Path -LiteralPath $PublicKey).Path $ImageDigest *> (Join-Path $outputPath 'verify.log')
    if ($LASTEXITCODE -ne 0) { throw 'Published image signature verification failed' }
    $receipt = @{status='SIGNATURE_VERIFIED';image_digest=$ImageDigest;checked_at=[DateTime]::UtcNow.ToString('o');public_key_sha256=(Get-FileHash -LiteralPath $PublicKey -Algorithm SHA256).Hash.ToLowerInvariant();receiving_unit_trust_policy='REQUIRES_SEPARATE_APPROVAL';production_approved=$false}
    [IO.File]::WriteAllText((Join-Path $outputPath 'signature-receipt.json'),($receipt|ConvertTo-Json -Depth 10)+"`n",[Text.UTF8Encoding]::new($false))
} finally {
    [Environment]::SetEnvironmentVariable('COSIGN_PASSWORD',$previousPassword,'Process')
    $secret = $null
}
