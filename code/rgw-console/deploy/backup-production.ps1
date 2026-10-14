#Requires -Version 7.2
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$DeploymentDirectory,
    [Parameter(Mandatory)][string]$OutputDirectory
)

# Bundled PostgreSQL only. Writers are stopped together so DB rows and local
# evidence represent one application checkpoint. No source volume is removed.
$ErrorActionPreference = 'Stop'
$deploymentPath = [IO.Path]::GetFullPath($DeploymentDirectory)
$outputPath = [IO.Path]::GetFullPath($OutputDirectory)
if (-not (Test-Path -LiteralPath (Join-Path $deploymentPath 'compose.production.yml'))) {
    throw 'DeploymentDirectory must contain compose.production.yml'
}
if (Test-Path -LiteralPath $outputPath) { throw "Refusing to overwrite backup directory: $outputPath" }
$runtime = Get-Content -LiteralPath (Join-Path $deploymentPath '.env') -Raw
function Read-RuntimeValue([string]$Name) {
    $match = [regex]::Match($runtime, "(?m)^$Name=([^\r\n]+)$")
    if (-not $match.Success) { throw "Missing $Name in deployment .env" }
    $match.Groups[1].Value.Trim()
}
$project = Read-RuntimeValue 'COMPOSE_PROJECT_NAME'
if ($project -notmatch '^[a-z0-9][a-z0-9_-]{0,127}$') { throw 'Invalid Compose project name' }
$operationId = [guid]::NewGuid().ToString('N')
$backupTimer = [Diagnostics.Stopwatch]::StartNew()
$helperName = "slc-backup-$operationId"
$utf8 = [Text.UTF8Encoding]::new($false)
function Invoke-Docker([string[]]$Arguments) {
    $result = & docker @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Docker operation failed ($($Arguments[0])): $($result -join '\n')" }
    $result -join "`n"
}
function Inspect-Container([string]$Id) { (Invoke-Docker @('inspect', $Id) | ConvertFrom-Json)[0] }
function Write-Json([string]$Name, $Value) {
    [IO.File]::WriteAllText((Join-Path $outputPath $Name), (ConvertTo-Json -InputObject $Value -Depth 20) + "`n", $utf8)
}

$databaseIds = @((Invoke-Docker @('ps', '-q', '--filter', "label=com.docker.compose.project=$project", '--filter', 'label=com.docker.compose.service=postgres')) -split '\s+' | Where-Object { $_ })
if ($databaseIds.Count -ne 1) { throw 'Expected exactly one running bundled PostgreSQL container; external PostgreSQL is not supported by this script' }
$database = Inspect-Container $databaseIds[0]
$databaseName = $database.Id # Immutable ID: a replacement name cannot redirect exec/cp/cleanup.
if ($databaseName -notmatch '^[a-f0-9]{64}$' -or $database.Config.Labels.'com.docker.compose.project' -ne $project -or $database.Config.Labels.'com.docker.compose.service' -ne 'postgres' -or -not $database.State.Running) { throw 'Exact running source PostgreSQL identity required' }
$databaseImage = $database.Image
$applicationImageReference = Read-RuntimeValue 'STORAGE_LAB_CONSOLE_IMAGE'
$applicationImage = (Invoke-Docker @('image', 'inspect', $applicationImageReference) | ConvertFrom-Json)[0].Id
$packagedMetadata = Invoke-Docker @('run', '--rm', '--network', 'none', '--read-only', '--entrypoint', 'python', $applicationImage, '/opt/storage-lab-console/bin/version_info.py') | ConvertFrom-Json
$expectedSchema = [int]$packagedMetadata.database_schema
if ($expectedSchema -lt 1 -or $expectedSchema -gt 9999) { throw 'Application image schema metadata is invalid' }
if (@($database.Config.Env) -notcontains 'POSTGRES_USER=storage_lab_console' -or @($database.Config.Env) -notcontains 'POSTGRES_DB=storage_lab_console') {
    throw 'Bundled PostgreSQL must use storage_lab_console for both user and database'
}
$schema = [int](Invoke-Docker @('exec', '-u', 'postgres', $databaseName, 'psql', '-U', 'storage_lab_console', '-d', 'storage_lab_console', '-At', '-v', 'ON_ERROR_STOP=1', '-c', 'SELECT max(version) FROM schema_migrations'))
if ($schema -ne $expectedSchema) { throw "Application image requires schema $expectedSchema before backup, observed $schema" }

New-Item -ItemType Directory -Path $outputPath | Out-Null
if ($IsWindows) {
    $operatorSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    & icacls $outputPath /inheritance:r /grant:r "*${operatorSid}:(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' *> $null
    if ($LASTEXITCODE -ne 0) { throw 'Could not restrict backup directory ACL' }
} else {
    & chmod 700 $outputPath
    if ($LASTEXITCODE -ne 0) { throw 'Could not restrict backup directory permissions' }
}

$runningIds = @((Invoke-Docker @('ps', '-q', '--filter', "label=com.docker.compose.project=$project")) -split '\s+' | Where-Object { $_ -and $_ -ne $databaseIds[0] })
$writers = @($runningIds | ForEach-Object { Inspect-Container $_ })
$ownerIds = @((Invoke-Docker @('ps', '-aq', '--filter', "label=com.docker.compose.project=$project")) -split '\s+' | Where-Object { $_ })
$allSourceContainers = @($ownerIds | ForEach-Object { Inspect-Container $_ })
foreach ($owner in $allSourceContainers) {
    if ($owner.Id -notmatch '^[a-f0-9]{64}$' -or $owner.Config.Labels.'com.docker.compose.project' -ne $project) { throw 'Exact source container identity required' }
}
$stopped = @()
$dumpPath = "/tmp/slc-$operationId.dump"
$asIsExportPath = "/tmp/slc-$operationId-as-is.jsonl"
$auditExportPath = "/tmp/slc-$operationId-audit.jsonl"
$asIsCheckpointPath = Join-Path $outputPath 'as-is-payload-checkpoint.jsonl'
$asIsSummary = @{ collections_verified=0; deleted_collections_verified=0 }
$volumeMetadata = @()
$startedAt = [DateTime]::UtcNow.ToString('o')
$registrySql = "SELECT coalesce(json_agg(x ORDER BY x.id), '[]'::json)::text FROM (SELECT id, uri, sha256, size_bytes FROM evidence_artifacts) x"
$migrationsSql = "SELECT json_agg(x ORDER BY x.version)::text FROM (SELECT version, name, checksum FROM schema_migrations) x"
$asIsSql = "SELECT json_build_object('id',id,'cluster_id',cluster_id,'fsid',fsid,'phase',phase,'sha256',sha256,'deleted_at',deleted_at,'deleted_by',deleted_by,'payload',payload)::text FROM as_is_collections ORDER BY id"
$asIsCheckCode = @'
import hashlib,json,pathlib,re
source=pathlib.Path('/checkpoint/as-is-payload-checkpoint.jsonl')
count=deleted=0; previous=None
with source.open('rb') as handle,pathlib.Path('/tmp/as-is-registry.jsonl').open('w',encoding='utf-8') as output:
    while True:
        line=handle.readline(32*1024*1024+1)
        if not line:break
        if len(line)>32*1024*1024:raise RuntimeError('As-is row exceeds bounded integrity-check limit')
        row=json.loads(line);payload=row.pop('payload')
        encoded=json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
        if not isinstance(payload,dict) or hashlib.sha256(encoded).hexdigest()!=row['sha256']:
            raise RuntimeError('As-is canonical payload SHA-256 does not match checkpoint')
        if not re.fullmatch('[0-9a-f]{64}',row['sha256']) or any(payload.get(key)!=row[key] for key in ('id','cluster_id','fsid','phase')):
            raise RuntimeError('As-is payload identity does not match checkpoint metadata')
        if previous is not None and row['id']<=previous:raise RuntimeError('As-is checkpoint order or duplicate ID is invalid')
        previous=row['id'];count+=1;deleted+=row['deleted_at'] is not None
        output.write(json.dumps(row,sort_keys=True,separators=(',',':'),ensure_ascii=False)+'\n')
print(json.dumps({'collections_verified':count,'deleted_collections_verified':deleted}))
'@
$archiveCode = @'
import hashlib,json,pathlib,tarfile,sys
root=pathlib.Path('/source'); output=pathlib.Path('/tmp'); name=sys.argv[1]
files=[]
with tarfile.open(output/(name+'.tar.gz'),'w:gz') as archive:
    for path in sorted(root.rglob('*')):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise RuntimeError('Unsupported entry in backup volume')
        relative=path.relative_to(root).as_posix()
        if path.is_file():
            digest=hashlib.sha256()
            with path.open('rb') as handle:
                for chunk in iter(lambda:handle.read(1048576),b''):digest.update(chunk)
            files.append({'path':relative,'sha256':digest.hexdigest(),'size_bytes':path.stat().st_size})
        archive.add(path,arcname=relative,recursive=False)
(output/(name+'.inventory.json')).write_text(json.dumps(files,sort_keys=True)+'\n')
'@

try {
    foreach ($writer in $writers) {
        if ($writer.Id -notmatch '^[a-f0-9]{64}$' -or $writer.Config.Labels.'com.docker.compose.project' -ne $project) { throw 'Exact checkpoint writer identity required' }
        # Register recovery first, including a stop that partially succeeds.
        $stopped += $writer.Id
        Invoke-Docker @('stop', '-t', '45', $writer.Id) | Out-Null
    }
    # Check the application namespace stayed quiescent; service restarters must
    # be disabled during this maintenance window by the deployment operator.
    $stillRunning = @((Invoke-Docker @('ps', '-q', '--filter', "label=com.docker.compose.project=$project")) -split '\s+' | Where-Object { $_ -and $_ -ne $databaseIds[0] })
    if ($stillRunning.Count) { throw 'Application services restarted during backup checkpoint' }
    Invoke-Docker @('exec', '-u', 'postgres', $databaseName, 'pg_dump', '-U', 'storage_lab_console', '-d', 'storage_lab_console', '--format=custom', '--file', $dumpPath) | Out-Null
    Invoke-Docker @('cp', "${databaseName}:$dumpPath", (Join-Path $outputPath 'database.dump')) | Out-Null
    $registry = @(Invoke-Docker @('exec', '-u', 'postgres', $databaseName, 'psql', '-U', 'storage_lab_console', '-d', 'storage_lab_console', '-At', '-v', 'ON_ERROR_STOP=1', '-c', $registrySql) | ConvertFrom-Json)
    Write-Json 'evidence-registry.json' @($registry)
    $migrations = @(Invoke-Docker @('exec', '-u', 'postgres', $databaseName, 'psql', '-U', 'storage_lab_console', '-d', 'storage_lab_console', '-At', '-v', 'ON_ERROR_STOP=1', '-c', $migrationsSql) | ConvertFrom-Json)
    if ($migrations.Count -ne $expectedSchema -or (@($migrations.version) -join ',') -ne ((1..$expectedSchema) -join ',')) { throw 'Expected the complete contiguous migration history at the backup checkpoint' }
    Write-Json 'migrations.json' $migrations
    if ($schema -ge 21) {
        $auditSql = "SELECT row_to_json(x)::text FROM (SELECT id,collection_id,event_type,actor,occurred_at,sha256 FROM as_is_collection_events ORDER BY id) x"
        Invoke-Docker @('exec', '-u', 'postgres', $databaseName, 'psql', '-U', 'storage_lab_console', '-d', 'storage_lab_console', '-At', '-v', 'ON_ERROR_STOP=1', '--output', $auditExportPath, '-c', $auditSql) | Out-Null
        Invoke-Docker @('cp', "${databaseName}:$auditExportPath", (Join-Path $outputPath 'as-is-audit.jsonl')) | Out-Null
        # Stream one row at a time to a fixed operation file; never aggregate
        # full collection payloads in PowerShell or print them to the terminal.
        Invoke-Docker @('exec', '-u', 'postgres', $databaseName, 'psql', '-U', 'storage_lab_console', '-d', 'storage_lab_console', '-At', '-v', 'ON_ERROR_STOP=1', '--output', $asIsExportPath, '-c', $asIsSql) | Out-Null
        Invoke-Docker @('cp', "${databaseName}:$asIsExportPath", $asIsCheckpointPath) | Out-Null
        # The fixed integrity helper reads an operator-private 0700 Linux
        # directory via a READ-ONLY mount. UID0/DAC_OVERRIDE is scoped to this
        # networkless disposable helper, not the API; no secrets/socket mount.
        # Its only output is its own /tmp layer for docker cp after exit.
        $asIsSummary = Invoke-Docker @('run', '--name', $helperName, '--label', "storage-lab-console.backup=$operationId", '--network', 'none', '--memory', '512m', '--cpus', '1', '--pids-limit', '32', '--user', '0:0', '--cap-drop', 'ALL', '--cap-add', 'DAC_OVERRIDE', '--security-opt', 'no-new-privileges:true', '--mount', "type=bind,source=$outputPath,target=/checkpoint,readonly", '--entrypoint', 'python', $applicationImage, '-c', $asIsCheckCode) | ConvertFrom-Json
        Invoke-Docker @('cp', "${helperName}:/tmp/as-is-registry.jsonl", (Join-Path $outputPath 'as-is-registry.jsonl')) | Out-Null
        Invoke-Docker @('rm', $helperName) | Out-Null
        # The DB dump retains the data. Remove only this duplicate transient
        # export, leaving the compact integrity registry in the backup set.
        Remove-Item -LiteralPath $asIsCheckpointPath
    }
    foreach ($role in @('evidence', 'executor-state')) {
        $volumes = @((Invoke-Docker @('volume', 'ls', '-q', '--filter', "label=com.docker.compose.project=$project", '--filter', "label=com.docker.compose.volume=$role")) -split '\s+' | Where-Object { $_ })
        if ($volumes.Count -gt 1) { throw "Ambiguous source volume for $role" }
        if (-not $volumes.Count) {
            $volumeMetadata += @{ role=$role; status='NOT_PRESENT'; source_volume=$null }
            continue
        }
        $volumeIdentity = (Invoke-Docker @('volume', 'inspect', $volumes[0]) | ConvertFrom-Json)[0]
        if ($volumeIdentity.Name -ne $volumes[0] -or $volumeIdentity.Labels.'com.docker.compose.project' -ne $project -or $volumeIdentity.Labels.'com.docker.compose.volume' -ne $role) { throw 'Source volume identity mismatch' }
        $ownerService = if ($role -eq 'evidence') { 'api' } else { 'executor' }
        $expectedTarget = if ($role -eq 'evidence') { '/var/lib/storage-lab-console/evidence' } else { '/var/lib/rbd-executor' }
        foreach ($writer in $allSourceContainers | Where-Object { $_.Config.Labels.'com.docker.compose.service' -eq $ownerService }) {
            $mount = @($writer.Mounts | Where-Object Destination -eq $expectedTarget)
            if ($mount.Count -ne 1 -or $mount[0].Type -ne 'volume' -or $mount[0].Name -ne $volumes[0]) { throw 'Selected source volume is not the application mount' }
        }
        Invoke-Docker @('run', '--name', $helperName, '--label', "storage-lab-console.backup=$operationId", '--network', 'none', '--user', '10001:10001', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true', '--mount', "type=volume,source=$($volumes[0]),target=/source,readonly", '--entrypoint', 'python', $applicationImage, '-c', $archiveCode, $role) | Out-Null
        Invoke-Docker @('cp', "${helperName}:/tmp/$role.tar.gz", (Join-Path $outputPath "$role.tar.gz")) | Out-Null
        Invoke-Docker @('cp', "${helperName}:/tmp/$role.inventory.json", (Join-Path $outputPath "$role.inventory.json")) | Out-Null
        Invoke-Docker @('rm', $helperName) | Out-Null
        $volumeMetadata += @{ role=$role; status='BACKED_UP'; source_volume=$volumes[0]; archive="$role.tar.gz"; inventory="$role.inventory.json" }
    }
    if (@($registry).Count -and -not ($volumeMetadata | Where-Object { $_.role -eq 'evidence' -and $_.status -eq 'BACKED_UP' })) {
        throw 'Database has evidence registry rows but no evidence volume was found'
    }
    $artifacts = @(Get-ChildItem -LiteralPath $outputPath -File | Sort-Object Name | ForEach-Object {
        @{ name=$_.Name; size_bytes=$_.Length; sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant() }
    })
    Write-Json 'backup-metadata.json' @{
        format_version=1; status='COMPLETE'; operation_id=$operationId; started_at=$startedAt; completed_at=[DateTime]::UtcNow.ToString('o')
        duration_seconds=[math]::Round($backupTimer.Elapsed.TotalSeconds,3); audit_checkpoint='as-is-audit.jsonl'
        source_project=$project; schema_version=$schema; application_image_reference=$applicationImageReference; application_image_id=$applicationImage
        postgres_image_id=$databaseImage; database='storage_lab_console'; database_user='storage_lab_console'
        volumes=$volumeMetadata; artifacts=$artifacts; registry_rows=@($registry).Count
        as_is_integrity=$asIsSummary
        checkpoint='All running application containers in source Compose project stopped; database remained running'
        limitations=@('Bundled PostgreSQL only', 'Database roles and credentials are not exported', 'External DB writers must be quiesced independently', 'Secrets/TLS/config and encryption are managed separately')
    }
    Write-Host "Backup complete: $outputPath"
    Write-Host "Schema: $schema; registered evidence artifacts: $(@($registry).Count)"
    Write-Host "As-is payloads verified: $($asIsSummary.collections_verified); soft-deleted: $($asIsSummary.deleted_collections_verified)"
} finally {
    & docker exec -u postgres $databaseName rm -f $dumpPath *> $null
    & docker exec -u postgres $databaseName rm -f $asIsExportPath *> $null
    & docker exec -u postgres $databaseName rm -f $auditExportPath *> $null
    $cleanupFailures = @()
    try { if (Test-Path -LiteralPath $asIsCheckpointPath) { Remove-Item -LiteralPath $asIsCheckpointPath } } catch { $cleanupFailures += 'TRANSIENT_CHECKPOINT_REMOVAL_FAILED' }
    # Remove only the helper carrying this operation's exact label.
    try {
        $helper = & docker inspect $helperName 2>$null | ConvertFrom-Json
        if ($LASTEXITCODE -eq 0 -and $helper[0].Config.Labels.'storage-lab-console.backup' -eq $operationId) {
            & docker rm -f $helper[0].Id *> $null
            if ($LASTEXITCODE -ne 0) { throw 'Helper removal failed' }
        }
    } catch { $cleanupFailures += 'DISPOSABLE_BACKUP_HELPER_REMOVAL_FAILED' }
    foreach ($id in $stopped) {
        try {
            $container = Inspect-Container $id
            if ($container.Id -ne $id -or $container.Config.Labels.'com.docker.compose.project' -ne $project) { throw 'Checkpoint restart target failed project identity check' }
            Invoke-Docker @('start', $id) | Out-Null
        } catch { $cleanupFailures += "CHECKPOINT_RESTART_FAILED_$id" }
    }
    if ($cleanupFailures.Count) { throw ('Backup cleanup/recovery incomplete; all remaining targets attempted: ' + ($cleanupFailures -join ', ')) }
}
