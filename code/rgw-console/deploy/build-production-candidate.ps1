#Requires -Version 7.2
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Version,
    [Parameter(Mandatory)][string]$SourceRevision,
    [Parameter(Mandatory)][string]$OutputDirectory,
    [string]$Builder
)
# Produces an OCI candidate with attestations, not a production signoff or push.
$ErrorActionPreference = 'Stop'
if ($Version -notmatch '^\d+\.\d+\.\d+(?:-[a-z0-9.-]+)?$') { throw 'Invalid version' }
if ($SourceRevision -notmatch '^[a-f0-9]{40}$') { throw 'An exact committed Git revision is required' }
$codePath = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$repositoryPath = [IO.Path]::GetFullPath((Join-Path $codePath '..'))
& git -C $repositoryPath cat-file -e "$SourceRevision^{commit}" 2>$null
if ($LASTEXITCODE -ne 0) { throw 'Source revision does not exist locally' }
$inputs = @('code/.dockerignore','code/rgw-console/packaging','code/rgw-console/backend/app','code/rgw-console/backend/requirements.txt','code/rgw-console/backend/requirements.lock','code/rgw-console/frontend/src','code/rgw-console/frontend/index.html','code/rgw-console/frontend/package.json','code/rgw-console/frontend/package-lock.json','code/rgw-console/frontend/tsconfig.json','code/rgw-console/frontend/vite.config.ts','code/rgw-console/rbd-console/src','code/rgw-console/rbd-console/package.json','code/rgw-console/rbd-console/package-lock.json','code/osd-info-collector/collect_osd.py')
& git -C $repositoryPath diff --quiet $SourceRevision -- @inputs
if ($LASTEXITCODE -ne 0) { throw 'Image input files differ from declared source revision' }
$untracked = & git -C $repositoryPath ls-files --others --exclude-standard -- @inputs
if ($LASTEXITCODE -ne 0 -or $untracked) { throw 'Uncommitted new image inputs are not allowed' }
$outputPath = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $outputPath) { throw 'Output exists; refusing to replace a previous candidate' }
New-Item -ItemType Directory -Path $outputPath | Out-Null
$metadata = Join-Path $outputPath 'build-metadata.json'
$archive = Join-Path $outputPath "storage-lab-console-$Version.oci.tar"
$arguments = @('buildx','build','--platform','linux/amd64','--sbom=true','--provenance=mode=max','--metadata-file',$metadata,'--build-arg',"APP_VERSION=$Version",'--build-arg',"VCS_REF=$SourceRevision",'--build-arg',("BUILD_DATE="+[DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')),'--output',"type=oci,dest=$archive",'-f',(Join-Path $codePath 'rgw-console/packaging/Dockerfile'))
if ($Builder) { $arguments += @('--builder',$Builder) }
$arguments += $codePath
& docker @arguments
if ($LASTEXITCODE -ne 0) { throw 'Candidate build failed; incomplete output is retained for diagnostics' }
$result = Get-Content -LiteralPath $metadata -Raw | ConvertFrom-Json
if ($result.'containerimage.digest' -notmatch '^sha256:[a-f0-9]{64}$') { throw 'Build did not return an exact image digest' }
$receipt = @{kind='OCI_CANDIDATE_BUILD';status='BUILT_NOT_ACCEPTED';version=$Version;source_revision=$SourceRevision;platform='linux/amd64';digest=$result.'containerimage.digest';archive_sha256=(Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant();sbom_requested=$true;provenance_requested='mode=max';attestations_inspection='PENDING';registry_push='NOT_RUN';signature='NOT_RUN';production_approved=$false}
[IO.File]::WriteAllText((Join-Path $outputPath 'candidate-receipt.json'),($receipt|ConvertTo-Json -Depth 10)+"`n",[Text.UTF8Encoding]::new($false))
Write-Host "Built local OCI candidate only: $archive"
Write-Host 'Inspect attached attestations and run the full staging/recovery gates before publishing or signing a release.'
