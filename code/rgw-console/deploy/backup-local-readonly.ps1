[CmdletBinding()]
param([Parameter(Mandatory)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
$backupTarget = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $backupTarget) { throw 'Backup directory already exists; refusing overwrite.' }
function Docker-Checked([string[]]$Arguments) {
    $value = & docker @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Local checkpoint failed during Docker $($Arguments[0])." }
    return $value
}
$names = @('storage-lab-console-local-api','storage-lab-console-local-executor',
    'storage-lab-console-local-capacity','storage-lab-console-local-performance','storage-lab-console-local-osdmap')
$specs = @{}
foreach ($name in ($names + 'storage-lab-console-local-postgres')) {
    $spec = (Docker-Checked @('inspect',$name) | ConvertFrom-Json)[0]
    if ($spec.Config.Labels.'storage-lab-console.scope' -ne 'local-preview') { throw 'Unverified local scope.' }
    $specs[$name] = $spec
}
$dbSpec = $specs['storage-lab-console-local-postgres']
if ($dbSpec.Config.Env -notcontains 'POSTGRES_USER=storage_lab_console' -or
    $dbSpec.Config.Env -notcontains 'POSTGRES_DB=storage_lab_console') { throw 'Unverified local database.' }
New-Item -ItemType Directory -Path $backupTarget | Out-Null
$operatorSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
& icacls $backupTarget /inheritance:r /grant:r "*${operatorSid}:(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' *> $null
if ($LASTEXITCODE -ne 0) { throw 'Could not restrict checkpoint ACL.' }
$encoding = [Text.UTF8Encoding]::new($false)
$running = @()
try {
    foreach ($name in $names) {
        if ($specs[$name].State.Running) {
            $running += $name
            Docker-Checked @('stop','--timeout','10',$name) | Out-Null
        }
    }
    # Full inspect may contain credentials; it stays in the ACL-restricted checkpoint only.
    [IO.File]::WriteAllText((Join-Path $backupTarget 'private-container-specifications.json'),
        (ConvertTo-Json -InputObject $specs -Depth 40), $encoding)
    $dbName = 'storage-lab-console-local-postgres'
    $dumpFile = '/tmp/slc-local-' + [guid]::NewGuid().ToString('N') + '.dump'
    Docker-Checked @('exec','-u','postgres',$dbName,'pg_dump','-U','storage_lab_console',
        '-d','storage_lab_console','-Fc','-f',$dumpFile) | Out-Null
    Docker-Checked @('cp',"${dbName}:$dumpFile",(Join-Path $backupTarget 'database.dump')) | Out-Null
    $sql = "SELECT json_build_object('collections',(SELECT coalesce(json_agg(x ORDER BY x.id),'[]'::json) FROM (SELECT id,sha256,deleted_at FROM as_is_collections) x),'events',(SELECT count(*) FROM as_is_collection_events),'schema',(SELECT max(version) FROM schema_migrations))::text"
    $registry = Docker-Checked @('exec','-u','postgres',$dbName,'psql','-U','storage_lab_console',
        '-d','storage_lab_console','-At','-v','ON_ERROR_STOP=1','-c',$sql)
    [IO.File]::WriteAllText((Join-Path $backupTarget 'as-is-checkpoint.json'),($registry -join "`n"),$encoding)
    $image = $specs['storage-lab-console-local-api'].Image
    foreach ($volume in @('storage-lab-console-local-evidence','storage-lab-console-local-executor-state')) {
        Docker-Checked @('run','--rm','--network','none','--read-only','--user','10001:10001',
            '--cap-drop','ALL','--security-opt','no-new-privileges',
            '--mount',"type=volume,source=$volume,target=/source,readonly",
            '--mount',"type=bind,source=$backupTarget,target=/checkpoint",
            '--entrypoint','tar',$image,'-cf',"/checkpoint/$volume.tar",'-C','/source','.') | Out-Null
    }
    Docker-Checked @('run','--rm','--network','none','--read-only','--user','10001:10001',
        '--cap-drop','ALL','--security-opt','no-new-privileges',
        '--mount',"type=bind,source=$backupTarget,target=/checkpoint,readonly",'--entrypoint','pg_restore',
        $dbSpec.Image,'--list','/checkpoint/database.dump') | Out-Null
    $summary = @{ created_at=[DateTime]::UtcNow.ToString('o'); scope='local-preview';
        database_container_id=$dbSpec.Id; collections=($registry | ConvertFrom-Json).collections.Count;
        database_sha256=(Get-FileHash -LiteralPath (Join-Path $backupTarget 'database.dump')).Hash.ToLowerInvariant() }
    [IO.File]::WriteAllText((Join-Path $backupTarget 'summary.json'),($summary | ConvertTo-Json),$encoding)
    $summary | ConvertTo-Json
} finally {
    foreach ($name in $running) { Docker-Checked @('start',$name) | Out-Null }
}
