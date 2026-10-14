#Requires -Version 7.2
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '../backup-manifest-validation.ps1')
$base = @{
    format_version=1; status='COMPLETE'; schema_version=21
    application_image_id=('sha256:'+('a'*64)); postgres_image_id=('sha256:'+('b'*64))
    audit_checkpoint='as-is-audit.jsonl'; registry_rows=1
    artifacts=@(@('database.dump','evidence-registry.json','migrations.json','as-is-registry.jsonl','as-is-audit.jsonl','evidence.tar.gz','evidence.inventory.json') | ForEach-Object { @{name=$_;sha256=('c'*64);size_bytes=10} })
    volumes=@(@{role='evidence';status='BACKED_UP';archive='evidence.tar.gz';inventory='evidence.inventory.json'},@{role='executor-state';status='NOT_PRESENT'})
}
$passed=0
Assert-BackupManifest ($base | ConvertTo-Json -Depth 10 | ConvertFrom-Json)
$passed++
$cases = @(
    @{name='incomplete';change={param($row) $row.status='FAILED'}},
    @{name='status array';change={param($row) $row.status=@('COMPLETE','COMPLETE')}},
    @{name='artifact scalar';change={param($row) $row.artifacts=$row.artifacts[0]}},
    @{name='volume scalar';change={param($row) $row.volumes=$row.volumes[0]}},
    @{name='artifact record null';change={param($row) $row.artifacts[0]=$null}},
    @{name='volume record null';change={param($row) $row.volumes[0]=$null}},
    @{name='unknown format';change={param($row) $row.format_version=2}},
    @{name='string format';change={param($row) $row.format_version='1'}},
    @{name='lowercase completion';change={param($row) $row.status='complete'}},
    @{name='fractional schema';change={param($row) $row.schema_version=21.1}},
    @{name='string schema';change={param($row) $row.schema_version='21'}},
    @{name='negative registry';change={param($row) $row.registry_rows=-1}},
    @{name='string registry';change={param($row) $row.registry_rows='1'}},
    @{name='mutable image tag';change={param($row) $row.application_image_id='postgres:latest'}},
    @{name='missing postgres image';change={param($row) $row.postgres_image_id=$null}},
    @{name='uppercase digest';change={param($row) $row.application_image_id='sha256:'+('A'*64)}},
    @{name='duplicate artifact';change={param($row) $row.artifacts+= $row.artifacts[0]}},
    @{name='path traversal artifact';change={param($row) $row.artifacts[0].name='../database.dump'}},
    @{name='bad hash';change={param($row) $row.artifacts[0].sha256='bad'}},
    @{name='negative size';change={param($row) $row.artifacts[0].size_bytes=-1}},
    @{name='string size';change={param($row) $row.artifacts[0].size_bytes='10'}},
    @{name='boolean size';change={param($row) $row.artifacts[0].size_bytes=$true}},
    @{name='fractional size';change={param($row) $row.artifacts[0].size_bytes=0.5}},
    @{name='integer-valued double size';change={param($row) $row.artifacts[0].size_bytes=[double]10}},
    @{name='omitted archive hash';change={param($row) $row.artifacts=@($row.artifacts | Where-Object name -ne 'evidence.tar.gz')}},
    @{name='omitted inventory hash';change={param($row) $row.artifacts=@($row.artifacts | Where-Object name -ne 'evidence.inventory.json')}},
    @{name='omitted database hash';change={param($row) $row.artifacts=@($row.artifacts | Where-Object name -ne 'database.dump')}},
    @{name='omitted audit hash';change={param($row) $row.artifacts=@($row.artifacts | Where-Object name -ne 'as-is-audit.jsonl')}},
    @{name='audit checkpoint disabled';change={param($row) $row.audit_checkpoint=$null}},
    @{name='audit checkpoint array';change={param($row) $row.audit_checkpoint=@('as-is-audit.jsonl','as-is-audit.jsonl')}},
    @{name='unknown volume';change={param($row) $row.volumes[0].role='user-data'}},
    @{name='uppercase volume bypass';change={param($row) $row.volumes[0].role='EVIDENCE'}},
    @{name='volume role array';change={param($row) $row.volumes[0].role=@('evidence')}},
    @{name='lowercase backed up';change={param($row) $row.volumes[0].status='backed_up'}},
    @{name='duplicate volume';change={param($row) $row.volumes+= $row.volumes[0]}},
    @{name='unknown volume status';change={param($row) $row.volumes[0].status='MAYBE'}},
    @{name='archive role mismatch';change={param($row) $row.volumes[0].archive='other.tar.gz'}},
    @{name='inventory role mismatch';change={param($row) $row.volumes[0].inventory='other.inventory.json'}},
    @{name='uppercase archive';change={param($row) $row.volumes[0].archive='EVIDENCE.tar.gz'}},
    @{name='archive array';change={param($row) $row.volumes[0].archive=@('evidence.tar.gz')}},
    @{name='registry without evidence volume';change={param($row) $row.volumes=@($row.volumes | Where-Object role -ne 'evidence')}}
)
foreach ($case in $cases) {
    $row = $base | ConvertTo-Json -Depth 10 | ConvertFrom-Json
    & $case.change $row
    $rejected=$false
    try { Assert-BackupManifest $row } catch { $rejected=$true }
    if (-not $rejected) { throw "Invalid manifest accepted: $($case.name)" }
    $passed++
}
Write-Host "Backup manifest checks PASS: $passed; no Docker/filesystem mutations"
