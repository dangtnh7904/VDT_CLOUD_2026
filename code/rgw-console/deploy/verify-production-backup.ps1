#Requires -Version 7.2
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$BackupDirectory,
    [string]$OutputDirectory,
    [switch]$RequireEvidence
)

# Restore rehearsal creates a fresh isolated PostgreSQL and fresh volumes. No
# source containers or production volumes are modified. Exact labeled rehearsal
# objects are removed on exit; the report directory is retained.
$ErrorActionPreference = 'Stop'
$backupPath = [IO.Path]::GetFullPath($BackupDirectory)
$metadata = Get-Content -LiteralPath (Join-Path $backupPath 'backup-metadata.json') -Raw | ConvertFrom-Json
if ($metadata.format_version -ne 1 -or $metadata.status -ne 'COMPLETE' -or $metadata.schema_version -lt 1 -or $metadata.schema_version -gt 9999) { throw 'Unsupported or incomplete backup metadata' }
# PowerShell 7.5+ materializes JSON ISO timestamps as DateTime by default.
# Re-parsing their culture-dependent string representation breaks on hosts
# whose date order differs; retain an existing typed instant, parse strings
# only with an explicit invariant ISO-compatible format.
if ($metadata.started_at -is [DateTime]) {
    $backupStartedAt = $metadata.started_at.ToUniversalTime()
} elseif ($metadata.started_at -is [DateTimeOffset]) {
    $backupStartedAt = $metadata.started_at.UtcDateTime
} else {
    $backupStartedAt = [DateTimeOffset]::Parse([string]$metadata.started_at, [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::RoundtripKind).UtcDateTime
}
$operationId = [guid]::NewGuid().ToString('N')
$restoreTimer = [Diagnostics.Stopwatch]::StartNew()
$restoreStartedAt = [DateTime]::UtcNow
if (-not $OutputDirectory) { $OutputDirectory = Join-Path (Split-Path -Parent $backupPath) "restore-check-$operationId" }
$outputPath = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $outputPath) { throw "Refusing to overwrite rehearsal report: $outputPath" }
$prefix = "slc-restore-$operationId"
$dbContainer = "$prefix-db"
$helperName = "$prefix-helper"
$createdVolumes = @()
$utf8 = [Text.UTF8Encoding]::new($false)
function Invoke-Docker([string[]]$Arguments) {
    $result = & docker @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Docker operation failed ($($Arguments[0])): $($result -join '\n')" }
    $result -join "`n"
}
foreach ($artifact in $metadata.artifacts) {
    if ($artifact.name -notmatch '^[a-z0-9][a-z0-9.-]+$') { throw 'Unsafe backup artifact name' }
    $path = Join-Path $backupPath $artifact.name
    $file = Get-Item -LiteralPath $path
    if ($file.Length -ne $artifact.size_bytes -or (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $artifact.sha256) { throw "Backup integrity check failed: $($artifact.name)" }
}
foreach ($required in @('database.dump', 'evidence-registry.json', 'migrations.json')) {
    if (-not ($metadata.artifacts | Where-Object name -eq $required)) { throw "Missing required backup artifact: $required" }
}
if ([int]$metadata.schema_version -ge 21 -and -not ($metadata.artifacts | Where-Object name -eq 'as-is-registry.jsonl')) { throw 'Schema 21+ backup requires the As-is integrity registry' }
Invoke-Docker @('image', 'inspect', $metadata.application_image_id) | Out-Null
Invoke-Docker @('image', 'inspect', $metadata.postgres_image_id) | Out-Null
$packagedMetadata = Invoke-Docker @('run', '--rm', '--network', 'none', '--read-only', '--entrypoint', 'python', $metadata.application_image_id, '/opt/storage-lab-console/bin/version_info.py') | ConvertFrom-Json
if ([int]$packagedMetadata.database_schema -ne [int]$metadata.schema_version) { throw 'Backup schema does not match the pinned application image' }
New-Item -ItemType Directory -Path $outputPath | Out-Null
if ($IsWindows) {
    $operatorSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    & icacls $outputPath /inheritance:r /grant:r "*${operatorSid}:(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' *> $null
    if ($LASTEXITCODE -ne 0) { throw 'Could not restrict rehearsal report directory ACL' }
} else {
    & chmod 700 $outputPath
    if ($LASTEXITCODE -ne 0) { throw 'Could not restrict rehearsal report directory permissions' }
}
$asIsExportPath = "/tmp/slc-$operationId-as-is.jsonl"
$auditCheckpointPath = Join-Path $outputPath 'restored-as-is-audit.jsonl'
$asIsCheckpointPath = Join-Path $outputPath 'as-is-payload-checkpoint.jsonl'
$asIsSummary = @{ collections_verified=0; deleted_collections_verified=0 }
$asIsCheckCode = @'
import hashlib,json,pathlib
count=deleted=0;previous=None
with pathlib.Path('/checkpoint/as-is-payload-checkpoint.jsonl').open('rb') as actual,pathlib.Path('/backup/as-is-registry.jsonl').open('rb') as expected:
    while True:
        line=actual.readline(32*1024*1024+1);reference=expected.readline(1024*1024+1)
        if not line and not reference:break
        if not line or not reference or len(line)>32*1024*1024 or len(reference)>1024*1024:
            raise RuntimeError('As-is restored registry coverage or bounded row limit differs')
        row=json.loads(line);payload=row.pop('payload')
        encoded=json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
        if not isinstance(payload,dict) or hashlib.sha256(encoded).hexdigest()!=row['sha256']:
            raise RuntimeError('Restored As-is canonical payload SHA-256 mismatch')
        if any(payload.get(key)!=row[key] for key in ('id','cluster_id','fsid','phase')) or row!=json.loads(reference):
            raise RuntimeError('Restored As-is identity/hash/phase/soft-delete metadata differs from checkpoint')
        if previous is not None and row['id']<=previous:raise RuntimeError('As-is restored order or duplicate ID is invalid')
        previous=row['id'];count+=1;deleted+=row['deleted_at'] is not None
print(json.dumps({'collections_verified':count,'deleted_collections_verified':deleted}))
'@
$restoreCode = @'
import hashlib,json,pathlib,tarfile,sys,os
name=sys.argv[1];root=pathlib.Path('/restored');source=pathlib.Path('/backup')
if any(root.iterdir()):raise RuntimeError('Restore target must be empty')
with tarfile.open(source/(name+'.tar.gz'),'r:gz') as archive:
    for member in archive.getmembers():
        target=(root/member.name).resolve()
        if not target.is_relative_to(root) or not (member.isfile() or member.isdir()):
            raise RuntimeError('Unsafe archive member')
    archive.extractall(root,filter='data')
expected=json.loads((source/(name+'.inventory.json')).read_text()); observed=[]
for path in sorted(root.rglob('*')):
    if path.is_symlink():raise RuntimeError('Unexpected restored symlink')
    if path.is_file():
        digest=hashlib.sha256()
        with path.open('rb') as handle:
            for chunk in iter(lambda:handle.read(1048576),b''):digest.update(chunk)
        observed.append({'path':path.relative_to(root).as_posix(),'sha256':digest.hexdigest(),'size_bytes':path.stat().st_size})
    os.chown(path,10001,10001)
os.chown(root,10001,10001)
if observed!=expected:raise RuntimeError('Restored volume inventory does not match backup')
links=0
if name=='evidence':
    for row in json.loads(pathlib.Path('/checkpoint/restored-evidence-registry.json').read_text()):
        if not row['uri'].startswith('filesystem:'):raise RuntimeError('Unsupported registry URI')
        relative=row['uri'][len('filesystem:'):]; target=(root/relative).resolve()
        if not relative or not target.is_relative_to(root):raise RuntimeError('Registry URI escapes evidence volume')
        entry=next((entry for entry in observed if entry['path']==relative),None)
        if not entry or entry['sha256']!=row['sha256'] or entry['size_bytes']!=row['size_bytes']:
            raise RuntimeError('Restored DB/evidence linkage mismatch')
        links+=1
print(json.dumps({'role':name,'files_verified':len(observed),'registry_links_verified':links,'status':'PASS'}))
'@
$volumeResults = @()
$registryCount = 0
$failureStage = 'CREATE_ISOLATED_RESTORE_TARGETS'
try {
    foreach ($role in @('db') + @($metadata.volumes | Where-Object status -eq 'BACKED_UP' | ForEach-Object role)) {
        if ($role -notin @('db', 'evidence', 'executor-state')) { throw 'Unexpected volume role in backup metadata' }
        $volumeName = "$prefix-$role"
        Invoke-Docker @('volume', 'create', '--label', "storage-lab-console.rehearsal=$operationId", $volumeName) | Out-Null
        $createdVolumes += $volumeName
    }
    Invoke-Docker @('run', '-d', '--name', $dbContainer, '--label', "storage-lab-console.rehearsal=$operationId", '--network', 'none', '-e', 'POSTGRES_USER=storage_lab_console', '-e', 'POSTGRES_DB=storage_lab_console', '-e', 'POSTGRES_HOST_AUTH_METHOD=trust', '--mount', "type=volume,source=$prefix-db,target=/var/lib/postgresql/data", $metadata.postgres_image_id) | Out-Null
    $failureStage = 'WAIT_FOR_ISOLATED_DATABASE'
    $ready = $false
    for ($attempt=0; $attempt -lt 60; $attempt++) {
        & docker exec -u postgres $dbContainer pg_isready -U storage_lab_console -d storage_lab_console *> $null
        if ($LASTEXITCODE -eq 0) { $ready=$true; break }
        Start-Sleep -Seconds 1
    }
    if (-not $ready) { throw 'Fresh rehearsal PostgreSQL did not become ready' }
    $failureStage = 'RESTORE_DATABASE_DUMP'
    Invoke-Docker @('cp', (Join-Path $backupPath 'database.dump'), "${dbContainer}:/tmp/database.dump") | Out-Null
    Invoke-Docker @('exec', '-u', '0', $dbContainer, 'chown', 'postgres:postgres', '/tmp/database.dump') | Out-Null
    Invoke-Docker @('exec', '-u', 'postgres', $dbContainer, 'pg_restore', '-U', 'storage_lab_console', '-d', 'storage_lab_console', '--exit-on-error', '--no-owner', '--no-acl', '/tmp/database.dump') | Out-Null
    $schema = [int](Invoke-Docker @('exec', '-u', 'postgres', $dbContainer, 'psql', '-U', 'storage_lab_console', '-d', 'storage_lab_console', '-At', '-v', 'ON_ERROR_STOP=1', '-c', 'SELECT max(version) FROM schema_migrations'))
    if ($schema -ne [int]$metadata.schema_version) { throw 'Restored schema version does not match the source checkpoint' }
    $failureStage = 'VERIFY_AS_IS_AND_AUDIT_CHECKPOINTS'
    if ($schema -ge 21) {
        if ($metadata.audit_checkpoint) {
            if ($metadata.audit_checkpoint -ne 'as-is-audit.jsonl' -or -not ($metadata.artifacts | Where-Object name -eq 'as-is-audit.jsonl')) { throw 'Missing bounded audit checkpoint' }
            $auditSql = "SELECT row_to_json(x)::text FROM (SELECT id,collection_id,event_type,actor,occurred_at,sha256 FROM as_is_collection_events ORDER BY id) x"
            $auditTemp = "/tmp/slc-$operationId-audit.jsonl"
            Invoke-Docker @('exec', '-u', 'postgres', $dbContainer, 'psql', '-U', 'storage_lab_console', '-d', 'storage_lab_console', '-At', '-v', 'ON_ERROR_STOP=1', '--output', $auditTemp, '-c', $auditSql) | Out-Null
            Invoke-Docker @('cp', "${dbContainer}:$auditTemp", $auditCheckpointPath) | Out-Null
            if ((Get-FileHash -LiteralPath $auditCheckpointPath -Algorithm SHA256).Hash -ne (Get-FileHash -LiteralPath (Join-Path $backupPath 'as-is-audit.jsonl') -Algorithm SHA256).Hash) { throw 'Restored collection audit actors/history differ from backup' }
        }
        $asIsSql = "SELECT json_build_object('id',id,'cluster_id',cluster_id,'fsid',fsid,'phase',phase,'sha256',sha256,'deleted_at',deleted_at,'deleted_by',deleted_by,'payload',payload)::text FROM as_is_collections ORDER BY id"
        Invoke-Docker @('exec', '-u', 'postgres', $dbContainer, 'psql', '-U', 'storage_lab_console', '-d', 'storage_lab_console', '-At', '-v', 'ON_ERROR_STOP=1', '--output', $asIsExportPath, '-c', $asIsSql) | Out-Null
        Invoke-Docker @('cp', "${dbContainer}:$asIsExportPath", $asIsCheckpointPath) | Out-Null
        $asIsSummary = Invoke-Docker @('run', '--name', $helperName, '--label', "storage-lab-console.rehearsal=$operationId", '--network', 'none', '--read-only', '--tmpfs', '/tmp:rw,noexec,nosuid,size=64m,mode=1777', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true', '--user', '10001:10001', '--mount', "type=bind,source=$backupPath,target=/backup,readonly", '--mount', "type=bind,source=$outputPath,target=/checkpoint,readonly", '--entrypoint', 'python', $metadata.application_image_id, '-c', $asIsCheckCode) | ConvertFrom-Json
        Invoke-Docker @('rm', $helperName) | Out-Null
        Remove-Item -LiteralPath $asIsCheckpointPath
    }
    $failureStage = 'VERIFY_MIGRATION_AND_EVIDENCE_REGISTRIES'
    $migrationsSql = "SELECT json_agg(x ORDER BY x.version)::text FROM (SELECT version, name, checksum FROM schema_migrations) x"
    $migrations = @(Invoke-Docker @('exec', '-u', 'postgres', $dbContainer, 'psql', '-U', 'storage_lab_console', '-d', 'storage_lab_console', '-At', '-v', 'ON_ERROR_STOP=1', '-c', $migrationsSql) | ConvertFrom-Json)
    $expectedMigrations = @(Get-Content -LiteralPath (Join-Path $backupPath 'migrations.json') -Raw | ConvertFrom-Json)
    if ($migrations.Count -ne $schema -or (@($migrations.version) -join ',') -ne ((1..$schema) -join ',') -or ($migrations | ConvertTo-Json -Depth 10 -Compress) -ne ($expectedMigrations | ConvertTo-Json -Depth 10 -Compress)) { throw 'Restored migration names/checksums do not match source checkpoint' }
    $registrySql = "SELECT coalesce(json_agg(x ORDER BY x.id), '[]'::json)::text FROM (SELECT id, uri, sha256, size_bytes FROM evidence_artifacts) x"
    $registry = @(Invoke-Docker @('exec', '-u', 'postgres', $dbContainer, 'psql', '-U', 'storage_lab_console', '-d', 'storage_lab_console', '-At', '-v', 'ON_ERROR_STOP=1', '-c', $registrySql) | ConvertFrom-Json)
    $expectedRegistry = @(Get-Content -LiteralPath (Join-Path $backupPath 'evidence-registry.json') -Raw | ConvertFrom-Json)
    if (($registry | ConvertTo-Json -Depth 10 -Compress) -ne ($expectedRegistry | ConvertTo-Json -Depth 10 -Compress)) { throw 'Restored evidence registry does not match source checkpoint' }
    $registryCount = $registry.Count
    if ($RequireEvidence -and $registryCount -eq 0) { throw 'RequireEvidence requires at least one backed-up evidence registry row' }
    if ($registryCount -and -not ($metadata.volumes | Where-Object { $_.role -eq 'evidence' -and $_.status -eq 'BACKED_UP' })) { throw 'Evidence registry rows require a backed-up evidence volume' }
    [IO.File]::WriteAllText((Join-Path $outputPath 'restored-evidence-registry.json'), (ConvertTo-Json -InputObject $registry -Depth 10) + "`n", $utf8)
    foreach ($volume in $metadata.volumes | Where-Object status -eq 'BACKED_UP') {
        $role = $volume.role
        $failureStage = "RESTORE_AND_VERIFY_VOLUME_$($role.ToUpperInvariant().Replace('-','_'))"
        # Two read-only mounts: the archive set and restored DB's registry. The
        # helper writes only the new rehearsal volume, with no network access.
        $result = Invoke-Docker @('run', '--name', $helperName, '--label', "storage-lab-console.rehearsal=$operationId", '--network', 'none', '--read-only', '--cap-drop', 'ALL', '--cap-add', 'CHOWN', '--cap-add', 'DAC_OVERRIDE', '--security-opt', 'no-new-privileges:true', '--user', '0:0', '--mount', "type=volume,source=$prefix-$role,target=/restored", '--mount', "type=bind,source=$backupPath,target=/backup,readonly", '--mount', "type=bind,source=$outputPath,target=/checkpoint,readonly", '--entrypoint', 'python', $metadata.application_image_id, '-c', $restoreCode, $role)
        $volumeResults += ($result | ConvertFrom-Json)
        Invoke-Docker @('rm', $helperName) | Out-Null
    }
    $failureStage = 'WRITE_SUCCESS_RECEIPT'
    $report = @{
        status='PASS'; operation_id=$operationId; checked_at=[DateTime]::UtcNow.ToString('o'); source_backup=$backupPath
        archive_hashes_verified=@($metadata.artifacts).Count; restored_schema_version=$schema; migration_checksums_verified=$migrations.Count; registry_rows_verified=$registryCount
        volume_results=$volumeResults; source_modified=$false; network='none'; restore_mode='Fresh PostgreSQL database with --no-owner --no-acl'
        as_is_integrity=$asIsSummary
        audit_checkpoint_verified=[bool]$metadata.audit_checkpoint
        restore_duration_seconds=[math]::Round($restoreTimer.Elapsed.TotalSeconds,3)
        checkpoint_age_at_restore_seconds=($restoreStartedAt - $backupStartedAt).TotalSeconds
        recovery_objectives_status='MEASURED_REHEARSAL_ONLY_SLO_NOT_APPROVED'
        limitations=@('Bundled PostgreSQL only', 'Synthetic/local rehearsal does not validate site RPO/RTO', 'Credentials/config and database role recovery must be rehearsed separately')
    }
    [IO.File]::WriteAllText((Join-Path $outputPath 'restore-report.json'), ($report | ConvertTo-Json -Depth 20) + "`n", $utf8)
    Write-Host "Restore rehearsal PASS: $(Join-Path $outputPath 'restore-report.json')"
    Write-Host "Schema: $schema; DB/evidence links verified: $registryCount"
    Write-Host "As-is payloads restored/verified: $($asIsSummary.collections_verified); soft-deleted: $($asIsSummary.deleted_collections_verified)"
} catch {
    # Keep a failed rehearsal report too. Raw driver/Docker errors may reveal
    # local configuration, so only a stable code is exported here.
    $failure = @{status='FAIL'; operation_id=$operationId; checked_at=[DateTime]::UtcNow.ToString('o'); error_code='RESTORE_REHEARSAL_FAILED'; failure_stage=$failureStage; exception_type=$_.Exception.GetType().Name; script_line_number=$_.InvocationInfo.ScriptLineNumber; restore_duration_seconds=[math]::Round($restoreTimer.Elapsed.TotalSeconds,3); source_modified=$false; not_a_production_signoff=$true}
    [IO.File]::WriteAllText((Join-Path $outputPath 'restore-report.json'), ($failure | ConvertTo-Json -Depth 10) + "`n", $utf8)
    throw 'Restore rehearsal failed; inspect its private report and local diagnostics'
} finally {
    if (Test-Path -LiteralPath $asIsCheckpointPath) { Remove-Item -LiteralPath $asIsCheckpointPath }
    if (Test-Path -LiteralPath $auditCheckpointPath) { Remove-Item -LiteralPath $auditCheckpointPath }
    foreach ($name in @($helperName, $dbContainer)) {
        $object = & docker inspect $name 2>$null | ConvertFrom-Json
        if ($LASTEXITCODE -eq 0) {
            if ($object[0].Config.Labels.'storage-lab-console.rehearsal' -ne $operationId) { throw 'Cleanup container identity mismatch' }
            Invoke-Docker @('rm', '-f', $name) | Out-Null
        }
    }
    foreach ($name in $createdVolumes) {
        $object = Invoke-Docker @('volume', 'inspect', $name) | ConvertFrom-Json
        if ($object[0].Labels.'storage-lab-console.rehearsal' -ne $operationId) { throw 'Cleanup volume identity mismatch' }
        Invoke-Docker @('volume', 'rm', $name) | Out-Null
    }
}
