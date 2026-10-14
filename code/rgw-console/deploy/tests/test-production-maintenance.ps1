#Requires -Version 7.2
# The real wrapper runs against temporary synthetic config; Python and backup
# are function doubles. Never call Docker, webhook or live deployment.
$ErrorActionPreference='Stop'
$global:slcUnitCase=$null;$global:slcSenderCalls=@();$global:slcProbeCalls=@()
function maintenance-test-python {
    $Arguments=@($args)
    $command=[string]$Arguments[0]
    if ($command -like '*production_ops.py') {
        $global:slcProbeCalls+= ,$Arguments
        if ($global:slcUnitCase.probeThrows) { throw 'Synthetic process invocation failed' }
        $reportIndex=[array]::IndexOf($Arguments,'--report')
        if (-not $global:slcUnitCase.noReport) {
            $status=if ($global:slcUnitCase.reportStatus) { $global:slcUnitCase.reportStatus } elseif ($global:slcUnitCase.probeExit) {'ALERT'} else {'PASS'}
            $alerts=if ($status -eq 'ALERT') {@('HOST_DISK_HIGH')} else {@()}
            $row=@{kind='PRODUCTION_OPERATIONS_PROBE';checked_at=[DateTime]::UtcNow.ToString('o');status=$status;alerts=@($alerts | Where-Object { $_ });thresholds_status='PROPOSED_NOT_APPROVED'}
            [IO.File]::WriteAllText([string]$Arguments[$reportIndex+1],($row|ConvertTo-Json -Depth 5))
        }
        $global:LASTEXITCODE=$global:slcUnitCase.probeExit
    } elseif ($command -like '*production_alert.py') {
        $reportIndex=[array]::IndexOf($Arguments,'--report')
        $stateIndex=[array]::IndexOf($Arguments,'--state')
        $row=Get-Content -LiteralPath ([string]$Arguments[$reportIndex+1]) -Raw | ConvertFrom-Json
        if ($row.alerts -isnot [array] -or $row.kind -notin @('PRODUCTION_OPERATIONS_PROBE','PRODUCTION_MAINTENANCE_BACKUP')) { throw 'Wrapper did not serialize an alert report array/kind' }
        $global:slcSenderCalls+= @{status=$row.status;kind=$row.kind;alerts=$row.alerts;state=[string]$Arguments[$stateIndex+1]}
        $global:LASTEXITCODE=$global:slcUnitCase.senderExit
    } else { throw 'Unexpected external process in maintenance double' }
}
function maintenance-test-backup {
    param([string]$DeploymentDirectory,[string]$OutputDirectory)
    if ($global:slcUnitCase.backupFails) { throw 'Synthetic backup failure' }
}
function Join-Path {
    param([string]$Path,[string]$ChildPath)
    if ($ChildPath -eq 'backup-production.ps1') { return 'maintenance-test-backup' }
    Microsoft.PowerShell.Management\Join-Path -Path $Path -ChildPath $ChildPath
}
$temporaryRoot=Join-Path ([IO.Path]::GetTempPath()) ('slc-maintenance-unit-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temporaryRoot | Out-Null
[IO.File]::WriteAllText((Join-Path $temporaryRoot '.env'),"COMPOSE_PROJECT_NAME=storage-lab-console-production-unit`nAPP_INSTANCE_ID=storage-lab-console-production-unit`n")
[IO.File]::WriteAllText((Join-Path $temporaryRoot 'compose.production.yml'),'services: {}')
$cases=@(
    @{name='check PASS';mode='Check';probeExit=0;senderExit=0;noReport=$false;backupFails=$false;throws=$false;status='PASS'},
    @{name='check ALERT still delivered';mode='Check';probeExit=2;senderExit=0;noReport=$false;backupFails=$false;throws=$true;status='ALERT'},
    @{name='process failure creates alert';mode='Check';probeExit=2;senderExit=0;noReport=$true;backupFails=$false;throws=$true;status='ALERT'},
    @{name='terminating invocation still reports and delivers';mode='Check';probeExit=2;probeThrows=$true;senderExit=0;noReport=$true;backupFails=$false;throws=$true;status='ALERT'},
    @{name='nonzero after PASS never sends recovery';mode='Check';probeExit=2;reportStatus='PASS';senderExit=0;noReport=$false;backupFails=$false;throws=$true;status='ALERT'},
    @{name='ALERT after zero still fails job';mode='Check';probeExit=0;reportStatus='ALERT';senderExit=0;noReport=$false;backupFails=$false;throws=$true;status='ALERT'},
    @{name='receiver failure not hidden';mode='Check';probeExit=0;senderExit=2;noReport=$false;backupFails=$false;throws=$true;status='PASS'},
    @{name='backup PASS';mode='Backup';probeExit=0;senderExit=0;noReport=$false;backupFails=$false;throws=$false;status='PASS'},
    @{name='backup failed still delivered';mode='Backup';probeExit=0;senderExit=0;noReport=$false;backupFails=$true;throws=$true;status='ALERT'}
)
try {
    foreach ($case in $cases) {
        $global:slcUnitCase=$case;$global:slcSenderCalls=@();$global:slcProbeCalls=@()
        $threw=$false;$cause=''
        try {
            & (Join-Path $PSScriptRoot '../run-production-maintenance.ps1') -DeploymentDirectory $temporaryRoot -BackupRoot (Join-Path $temporaryRoot 'backups') -Mode $case.mode -Python maintenance-test-python -CaFile 'fake-ca' -AuthUserFile 'fake-accounts' -BaseUrl 'https://console.example' -AlertConfigFile 'fake-alert-config' -AlertStateFile (Join-Path $temporaryRoot 'alerts.json')
        } catch { $threw=$true;$cause=$_.Exception.Message }
        if ($threw -ne $case.throws -or $global:slcSenderCalls.Count -ne 1 -or $global:slcSenderCalls[0].status -ne $case.status -or $global:slcSenderCalls[0].state -notlike "*.$($case.mode.ToLowerInvariant()).json") { throw "Maintenance test failed: $($case.name); sender=$($global:slcSenderCalls.Count); cause=$cause" }
        if ($case.mode -eq 'Check' -and [array]::IndexOf($global:slcProbeCalls[0],'--base-url') -lt 0) { throw 'Domain argument missing' }
        $lock=[IO.File]::Open((Join-Path $temporaryRoot 'maintenance.lock'),[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
        $lock.Dispose()
    }
} finally {
    $resolved=[IO.Path]::GetFullPath($temporaryRoot)
    $parent=[IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd([IO.Path]::DirectorySeparatorChar)+[IO.Path]::DirectorySeparatorChar
    if (-not $resolved.StartsWith($parent,[StringComparison]::OrdinalIgnoreCase) -or [IO.Path]::GetFileName($resolved) -notlike 'slc-maintenance-unit-*') { throw 'Unsafe unit-fixture cleanup path' }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
Write-Host "Production maintenance wrapper checks PASS: $($cases.Count); no Docker/webhook/scheduler actions"
