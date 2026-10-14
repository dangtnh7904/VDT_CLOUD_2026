#Requires -Version 7.2
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Version,
    [Parameter(Mandatory)][string]$SourceRevision,
    [Parameter(Mandatory)][string]$OutputDirectory,
    [string]$Builder,
    [switch]$Load,
    [string]$ImageTag
)
# Produces an OCI candidate with attestations, not a production signoff or push.
$ErrorActionPreference = 'Stop'
if ($Version -notmatch '^\d+\.\d+\.\d+(?:-[a-z0-9.-]+)?$') { throw 'Invalid version' }
if ($SourceRevision -notmatch '^[a-f0-9]{40}$') { throw 'An exact committed Git revision is required' }
if ($Load -and -not $ImageTag) { throw '-Load requires an explicit local ImageTag' }
if ($ImageTag -and -not $Load) { throw 'ImageTag is only valid together with -Load' }
if ($ImageTag -and $ImageTag -notmatch '^[a-z0-9]+(?:[._-][a-z0-9]+)*(?:(?::[0-9]+)?/[a-z0-9]+(?:[._-][a-z0-9]+)*)*:[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$') { throw 'Invalid image repository:tag' }
$codePath = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$repositoryPath = [IO.Path]::GetFullPath((Join-Path $codePath '..'))

function Invoke-CheckedGit([string]$Repository, [string[]]$GitArguments) {
    $result = & git -C $Repository @GitArguments
    if ($LASTEXITCODE -ne 0) { throw "Git preparation failed: $($GitArguments[0])" }
    return $result
}
function Get-MainIndexHash {
    $indexPath = [string](Invoke-CheckedGit $repositoryPath @('rev-parse','--git-path','index'))
    if (-not [IO.Path]::IsPathRooted($indexPath)) { $indexPath = Join-Path $repositoryPath $indexPath }
    if (-not (Test-Path -LiteralPath $indexPath -PathType Leaf)) { return $null }
    return (Get-FileHash -LiteralPath $indexPath -Algorithm SHA256).Hash.ToLowerInvariant()
}

$resolvedRevision = [string](Invoke-CheckedGit $repositoryPath @('rev-parse','--verify',"$SourceRevision^{commit}"))
if ($resolvedRevision -cne $SourceRevision) { throw 'Source revision must resolve to the exact requested commit' }
$sourceRemote = [string](Invoke-CheckedGit $repositoryPath @('config','--get','remote.origin.url'))
# Preserve an inspectable repository identity, never a local path or embedded token.
$remoteUri = $null
$httpsRemote = [Uri]::TryCreate($sourceRemote,[UriKind]::Absolute,[ref]$remoteUri) -and $remoteUri.Scheme -eq 'https' -and -not $remoteUri.UserInfo -and -not $remoteUri.Query -and -not $remoteUri.Fragment
$sshRemote = $sourceRemote -match '^git@[a-zA-Z0-9.-]+:[a-zA-Z0-9._/-]+$'
if (-not ($httpsRemote -or $sshRemote)) { throw 'Origin must be a credential-free HTTPS or git SSH repository URL' }
if ($Load) {
    $buildxVersion = [string](& docker buildx version)
    if ($LASTEXITCODE -ne 0 -or $buildxVersion -notmatch 'v(\d+)\.(\d+)\.(\d+)') { throw 'Could not identify Buildx version' }
    if ([Version]::new([int]$Matches[1],[int]$Matches[2],[int]$Matches[3]) -lt [Version]::new(0,13,0)) { throw 'Buildx 0.13+ is required for OCI plus local-image exporters' }
    $driverStatusJson = & docker info --format '{{json .DriverStatus}}'
    if ($LASTEXITCODE -ne 0) { throw 'Docker Engine is not ready for local image loading' }
    $driverStatus = $driverStatusJson | ConvertFrom-Json
    if (-not @($driverStatus | Where-Object { $_[0] -eq 'driver-type' -and $_[1] -eq 'io.containerd.snapshotter.v1' })) { throw '-Load requires the containerd image store to retain attached attestations' }
}
$outputPath = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $outputPath) { throw 'Output exists; refusing to replace a previous candidate' }
$mainIndexBefore = Get-MainIndexHash
New-Item -ItemType Directory -Path $outputPath | Out-Null
$contextRepository = Join-Path $outputPath 'source-context'
try {
    # Buildx records checkout HEAD independently of the VCS_REF build argument.
    # A committed, detached clone avoids stale provenance from the user's dirty
    # main checkout, and never copies that checkout's .env or other untracked data.
    & git clone --no-checkout --shared -- $repositoryPath $contextRepository
    if ($LASTEXITCODE -ne 0) { throw 'Could not create isolated committed source context' }
    Invoke-CheckedGit $contextRepository @('config','core.autocrlf','false') | Out-Null
    Invoke-CheckedGit $contextRepository @('config','core.eol','lf') | Out-Null
    $disabledHooks = Join-Path $outputPath 'disabled-hooks'
    New-Item -ItemType Directory -Path $disabledHooks | Out-Null
    Invoke-CheckedGit $contextRepository @('config','core.hooksPath',$disabledHooks) | Out-Null
    Invoke-CheckedGit $contextRepository @('remote','set-url','origin',$sourceRemote) | Out-Null
    Invoke-CheckedGit $contextRepository @('sparse-checkout','init','--cone') | Out-Null
    Invoke-CheckedGit $contextRepository @('sparse-checkout','set','--cone','code') | Out-Null
    Invoke-CheckedGit $contextRepository @('checkout','--detach',$SourceRevision) | Out-Null
    $contextHead = [string](Invoke-CheckedGit $contextRepository @('rev-parse','HEAD'))
    if ($contextHead -cne $SourceRevision) { throw 'Isolated source HEAD does not match declared revision' }
    $contextStatus = @(Invoke-CheckedGit $contextRepository @('status','--porcelain','--untracked-files=all'))
    if ($contextStatus.Count -ne 0) { throw 'Isolated source context is not clean' }
    $trackedCode = @(Invoke-CheckedGit $contextRepository @('ls-files','--','code'))
    $secretPaths = @($trackedCode | Where-Object {
        ($_ -match '(^|/)\.env(?:\.[^/]+)?$' -and $_ -notmatch '\.example$') -or
        $_ -match '\.(?:key|pem|pfx|p12)$' -or $_ -match '(^|/)(?:id_rsa|id_ed25519)$'
    })
    if ($secretPaths.Count -ne 0) { throw 'Committed code contains secret-bearing file paths; refusing build context' }
    $isolatedCodePath = Join-Path $contextRepository 'code'
    $dockerfile = Join-Path $isolatedCodePath 'rgw-console/packaging/Dockerfile'
    foreach ($requiredPath in @($dockerfile,(Join-Path $isolatedCodePath '.dockerignore'))) {
        if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) { throw 'Committed context is missing a required packaging file' }
    }
    $preparation = @{kind='COMMITTED_SOURCE_CONTEXT';source_revision=$SourceRevision;context_head=$contextHead;origin=$sourceRemote;tracked_code_files=$trackedCode.Count;context_clean=$true;main_index_sha256_before=$mainIndexBefore;main_index_unchanged=((Get-MainIndexHash) -ceq $mainIndexBefore);untracked_user_files_copied=$false}
    if (-not $preparation.main_index_unchanged) { throw 'Main index changed during source preparation; no user state was reset' }
    [IO.File]::WriteAllText((Join-Path $outputPath 'source-context-receipt.json'),($preparation|ConvertTo-Json -Depth 10)+"`n",[Text.UTF8Encoding]::new($false))

    $metadata = Join-Path $outputPath 'build-metadata.json'
    $archive = Join-Path $outputPath "storage-lab-console-$Version.oci.tar"
    $arguments = @('buildx','build','--platform','linux/amd64','--sbom=true','--provenance=mode=max','--metadata-file',$metadata,'--build-arg',"APP_VERSION=$Version",'--build-arg',"VCS_REF=$SourceRevision",'--build-arg',("BUILD_DATE="+[DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')),'--output',"type=oci,dest=$archive",'-f',$dockerfile)
    if ($Load) { $arguments += @('--output','type=docker','--tag',$ImageTag) }
    if ($Builder) { $arguments += @('--builder',$Builder) }
    $arguments += $isolatedCodePath
    & docker @arguments 2>&1 | Tee-Object -FilePath (Join-Path $outputPath 'build.log')
    if ($LASTEXITCODE -ne 0) { throw 'Candidate build failed; isolated source and incomplete output are retained for diagnostics' }
    $result = Get-Content -LiteralPath $metadata -Raw | ConvertFrom-Json
    if ($result.'containerimage.digest' -notmatch '^sha256:[a-f0-9]{64}$') { throw 'Build did not return an exact image digest' }
    $loadedDigest = $null
    if ($Load) {
        $loadedImageJson = & docker image inspect $ImageTag
        if ($LASTEXITCODE -ne 0) { throw 'Local image load could not be inspected' }
        $loadedImage = @($loadedImageJson | ConvertFrom-Json)[0]
        if ($loadedImage.Config.Labels.'org.opencontainers.image.revision' -cne $SourceRevision -or $loadedImage.Config.Labels.'org.opencontainers.image.version' -cne $Version) { throw 'Loaded image source/version does not match the candidate' }
        if ($loadedImage.Descriptor.mediaType -ne 'application/vnd.oci.image.index.v1+json' -or $loadedImage.Descriptor.digest -notmatch '^sha256:[a-f0-9]{64}$') { throw 'Loaded image has no inspectable OCI index for attestations' }
        $loadedDigest = $loadedImage.Descriptor.digest
    }
    $receipt = @{kind='OCI_CANDIDATE_BUILD';status='BUILT_NOT_ACCEPTED';version=$Version;source_revision=$SourceRevision;context_head=$contextHead;context_clean=$true;platform='linux/amd64';digest=$result.'containerimage.digest';archive_sha256=(Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant();sbom_requested=$true;provenance_requested='mode=max';attestations_inspection='PENDING';local_image_tag=$ImageTag;local_image_index_digest=$loadedDigest;registry_push='NOT_RUN';signature='NOT_RUN';production_approved=$false;main_index_unchanged=((Get-MainIndexHash) -ceq $mainIndexBefore)}
    if (-not $receipt.main_index_unchanged) { throw 'Main index changed during build; no user state was reset' }
    [IO.File]::WriteAllText((Join-Path $outputPath 'candidate-receipt.json'),($receipt|ConvertTo-Json -Depth 10)+"`n",[Text.UTF8Encoding]::new($false))
    Write-Host "Built local OCI candidate only: $archive"
    if ($Load) { Write-Host "Loaded local candidate tag: $ImageTag" }
    Write-Host 'Inspect actual attached attestations and run staging/recovery gates before publishing or signing a release.'
} finally {
    if ((Get-MainIndexHash) -cne $mainIndexBefore) { throw 'Main index changed while the candidate command ran; it was not restored or overwritten' }
}
