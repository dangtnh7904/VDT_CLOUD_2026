[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ApplicationImage,

    [Parameter(Mandatory = $true)]
    [string]$OutputDirectory,

    [string[]]$DependencyImages = @(),

    [string]$VulnerabilityReportPath,

    [switch]$SkipSbom
)

$ErrorActionPreference = "Stop"
$deployRoot = $PSScriptRoot
$outputPath = [IO.Path]::GetFullPath($OutputDirectory)

if (Test-Path -LiteralPath $outputPath) {
    throw "OutputDirectory already exists; refusing to overwrite it: $outputPath"
}

function Invoke-DockerChecked {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)

    & docker @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "docker $($Arguments -join ' ') failed with exit code $LASTEXITCODE"
    }
}

function Get-ImageMetadata {
    param([Parameter(Mandatory = $true)][string]$Reference)

    $raw = & docker image inspect $Reference
    if ($LASTEXITCODE -ne 0) {
        throw "Image is not available locally: $Reference"
    }
    $item = @($raw | ConvertFrom-Json)[0]
    [ordered]@{
        reference = $Reference
        image_id = $item.Id
        repo_digests = @($item.RepoDigests)
        os = $item.Os
        architecture = $item.Architecture
        size_bytes = $item.Size
        created = $item.Created
        user = $item.Config.User
    }
}

$applicationMetadata = Get-ImageMetadata -Reference $ApplicationImage
$dependencyMetadata = @(
    foreach ($reference in $DependencyImages) {
        Get-ImageMetadata -Reference $reference
    }
)

New-Item -ItemType Directory -Path $outputPath | Out-Null
$imagesDirectory = New-Item -ItemType Directory -Path (Join-Path $outputPath "images")
$artifactsDirectory = New-Item -ItemType Directory -Path (Join-Path $outputPath "artifacts")
New-Item -ItemType Directory -Path (Join-Path $outputPath "config/profiles") | Out-Null
New-Item -ItemType Directory -Path (Join-Path $outputPath "secrets") | Out-Null

Copy-Item -LiteralPath (Join-Path $deployRoot "compose.release.yml") -Destination $outputPath
Copy-Item -LiteralPath (Join-Path $deployRoot ".env.release.example") -Destination $outputPath
Copy-Item -LiteralPath (Join-Path $deployRoot "release-manifest.example.yaml") -Destination $outputPath
Copy-Item -LiteralPath (Join-Path $deployRoot "README.md") -Destination $outputPath
Copy-Item -LiteralPath (Join-Path $deployRoot "config/profiles/lab.yaml.example") -Destination (Join-Path $outputPath "config/profiles")
Copy-Item -LiteralPath (Join-Path $deployRoot "secrets/README.md") -Destination (Join-Path $outputPath "secrets")

$archivePath = Join-Path $imagesDirectory "storage-lab-console-images.tar"
$allImages = @($ApplicationImage) + @($DependencyImages)
Invoke-DockerChecked save --output $archivePath @allImages

$sbomStatus = "NOT_PROVIDED"
if (-not $SkipSbom) {
    $sbomPath = Join-Path $artifactsDirectory "storage-lab-console.spdx.json"
    Invoke-DockerChecked scout sbom --format spdx --output $sbomPath "local://$ApplicationImage"
    $sbomStatus = "INCLUDED"
}

$vulnerabilityStatus = "NOT_PROVIDED"
if ($VulnerabilityReportPath) {
    $resolvedReport = (Resolve-Path -LiteralPath $VulnerabilityReportPath).Path
    $reportName = [IO.Path]::GetFileName($resolvedReport)
    Copy-Item -LiteralPath $resolvedReport -Destination (Join-Path $artifactsDirectory $reportName)
    $vulnerabilityStatus = "INCLUDED_UNVERIFIED_BY_EXPORTER"
}

$metadata = [ordered]@{
    schema_version = 1
    status = "candidate_local_export"
    generated_at = (Get-Date).ToUniversalTime().ToString("o")
    application_image = $applicationMetadata
    dependency_images = $dependencyMetadata
    security_artifacts = [ordered]@{
        sbom = $sbomStatus
        vulnerability_report = $vulnerabilityStatus
    }
    acceptance = [ordered]@{
        registry_publication = "NOT_RUN"
        signature_verification = "NOT_RUN"
        lab_a = "NOT_RUN"
        second_environment_same_digest = "NOT_RUN"
        full_offline_compose = "NOT_RUN"
        backup_restore = "NOT_RUN"
    }
}
$metadataPath = Join-Path $outputPath "bundle-metadata.json"
$metadata | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $metadataPath -Encoding utf8NoBOM

$checksumPath = Join-Path $outputPath "SHA256SUMS"
$checksumLines = foreach ($file in Get-ChildItem -LiteralPath $outputPath -File -Recurse | Sort-Object FullName) {
    if ($file.FullName -eq $checksumPath) { continue }
    $relative = [IO.Path]::GetRelativePath($outputPath, $file.FullName).Replace("\", "/")
    $hash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    "$hash  $relative"
}
$checksumLines | Set-Content -LiteralPath $checksumPath -Encoding ascii

Write-Host "Offline candidate bundle created: $outputPath"
Write-Host "Application image ID: $($applicationMetadata.image_id)"
Write-Host "Images archive SHA-256: $((Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant())"
if ($vulnerabilityStatus -eq "NOT_PROVIDED") {
    Write-Warning "No vulnerability report was supplied. The bundle is not release-eligible until the security gate is completed."
}

