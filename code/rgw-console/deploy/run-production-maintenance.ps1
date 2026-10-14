#Requires -Version 7.2
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$DeploymentDirectory,
    [Parameter(Mandatory)][string]$BackupRoot,
    [ValidateSet('Backup','Check')][string]$Mode = 'Check',
    [string]$Python = 'python',
    [string]$CaFile,
    [string]$AuthUserFile,
    [string]$DaemonKey,
    [string]$BaseUrl,
    [string]$AlertConfigFile,
    [string]$AlertStateFile,
    [string[]]$AdditionalHostStoragePath = @()
)
$ErrorActionPreference = 'Stop'
$deploymentPath = (Resolve-Path -LiteralPath $DeploymentDirectory).Path
$backupPath = [IO.Path]::GetFullPath($BackupRoot)
if (-not (Test-Path -LiteralPath (Join-Path $deploymentPath 'compose.production.yml'))) { throw 'Production deployment directory required' }
if ([bool]$AlertConfigFile -ne [bool]$AlertStateFile) { throw 'Alert config and private state-file paths must be supplied together' }
$runtime = Get-Content -LiteralPath (Join-Path $deploymentPath '.env') -Raw
$match = [regex]::Match($runtime, '(?m)^COMPOSE_PROJECT_NAME=(storage-lab-console-(?:production|staging)[a-z0-9_-]{0,64})\r?$')
if (-not $match.Success) { throw 'Explicit production/staging project required' }
if (-not (Test-Path -LiteralPath $backupPath)) { New-Item -ItemType Directory -Path $backupPath | Out-Null }
$lock = $null
$operationFailed = $false
$deliveryFailed = $false
function Write-MaintenanceJson([string]$Path, [hashtable]$Payload) {
    $stream=[IO.File]::Open($Path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
    $writer=[IO.StreamWriter]::new($stream,[Text.UTF8Encoding]::new($false))
    try { $writer.WriteLine(($Payload | ConvertTo-Json -Depth 5)) }
    finally { $writer.Dispose() }
}
try {
    # OS releases this lock on process exit/crash; no stale PID lock guessing.
    $lock = [IO.File]::Open((Join-Path $deploymentPath 'maintenance.lock'), [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    $run = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ') + '-' + [guid]::NewGuid().ToString('N')
    $opsReport = Join-Path $backupPath "ops-$run.json"
    $deliveryReport = $opsReport
    if ($Mode -eq 'Backup') {
        try {
            & (Join-Path $PSScriptRoot 'backup-production.ps1') -DeploymentDirectory $deploymentPath -OutputDirectory (Join-Path $backupPath "backup-$run")
            if (-not $?) { throw 'Scheduled backup failed' }
        } catch { $operationFailed = $true }
        [string[]]$backupAlerts = @()
        if ($operationFailed) { $backupAlerts = @('SCHEDULED_BACKUP_FAILED') }
        $backupStatus = if ($operationFailed) { 'ALERT' } else { 'PASS' }
        $backupProbe = @{kind='PRODUCTION_MAINTENANCE_BACKUP';checked_at=[DateTime]::UtcNow.ToString('o');status=$backupStatus;alerts=$backupAlerts;thresholds_status='PROPOSED_NOT_APPROVED';not_a_production_signoff=$true}
        Write-MaintenanceJson $opsReport $backupProbe
    } else {
        if (-not $CaFile -or -not $AuthUserFile) { throw 'Check requires CA and client account file paths, not inline credentials' }
        $arguments = @((Join-Path $PSScriptRoot '../scripts/production_ops.py'), '--deployment-directory', $deploymentPath, '--backup-root', $backupPath, '--ca-file', $CaFile, '--auth-user-file', $AuthUserFile, '--report', $opsReport)
        if ($DaemonKey) { $arguments += @('--daemon-key', $DaemonKey) }
        if ($BaseUrl) { $arguments += @('--base-url', $BaseUrl) }
        foreach ($storagePath in $AdditionalHostStoragePath) { $arguments += @('--host-storage-path', $storagePath) }
        try {
            & $Python @arguments
            $operationFailed = $LASTEXITCODE -ne 0
        } catch {
            # Invocation failure (including native nonzero made terminating by
            # host policy) must reach the safe report/delivery path as well.
            $operationFailed = $true
        }
        $probeValid=$false
        $probe=$null
        if (Test-Path -LiteralPath $opsReport -PathType Leaf) {
            try {
                if ((Get-Item -LiteralPath $opsReport).Length -le 1048576) {
                    $probe=Get-Content -LiteralPath $opsReport -Raw | ConvertFrom-Json
                    $probeValid=$probe.kind -ceq 'PRODUCTION_OPERATIONS_PROBE' -and $probe.status -cin @('PASS','ALERT') -and $probe.alerts -is [array]
                    if ($probeValid) {
                        $probeValid=@($probe.alerts | Where-Object { $_ -isnot [string] -or $_ -cnotmatch '^[A-Z][A-Z0-9_]{0,79}$' }).Count -eq 0
                        $probeValid=$probeValid -and (($probe.status -ceq 'PASS' -and $probe.alerts.Count -eq 0) -or ($probe.status -ceq 'ALERT' -and $probe.alerts.Count -gt 0))
                    }
                }
            } catch { $probeValid=$false }
        }
        if ($probeValid -and $probe.status -ceq 'ALERT') { $operationFailed=$true }
        if (-not $probeValid -or ($operationFailed -and $probe.status -cne 'ALERT')) {
            # Preserve the process report. Never send PASS/RECOVERY after a
            # crashed or malformed probe, even if it wrote PASS before exit.
            $operationFailed=$true
            $deliveryReport=Join-Path $backupPath "ops-process-failure-$run.json"
            $failureProbe=@{kind='PRODUCTION_OPERATIONS_PROBE';checked_at=[DateTime]::UtcNow.ToString('o');status='ALERT';alerts=@('OPERATIONS_CHECK_PROCESS_FAILED');thresholds_status='PROPOSED_NOT_APPROVED';not_a_production_signoff=$true}
            Write-MaintenanceJson $deliveryReport $failureProbe
        }
    }
    # Nonzero probe/backup status does NOT skip delivery. The sender requires
    # an explicitly approved private endpoint config; no implicit destination.
    if ($AlertConfigFile) {
        if (-not $AlertStateFile) { throw 'Alert delivery requires an explicit private state-file path' }
        $alertReceipt=Join-Path $backupPath "alert-$($Mode.ToLowerInvariant())-$run.json"
        # Backup PASS must not recover an unresolved Check/disk alert. Each
        # mode gets its own durable state alongside the supplied private path.
        $statePath=[IO.Path]::GetFullPath($AlertStateFile)
        $modeState=Join-Path ([IO.Path]::GetDirectoryName($statePath)) ([IO.Path]::GetFileNameWithoutExtension($statePath)+".$($Mode.ToLowerInvariant()).json")
        try {
            & $Python (Join-Path $PSScriptRoot '../scripts/production_alert.py') --config $AlertConfigFile --report $deliveryReport --state $modeState --receipt $alertReceipt
            $deliveryFailed=$LASTEXITCODE -ne 0
        } catch { $deliveryFailed=$true }
        if ($deliveryFailed) {
            $processReceipt=Join-Path $backupPath "alert-process-failure-$run.json"
            Write-MaintenanceJson $processReceipt @{kind='PRODUCTION_ALERT_DELIVERY';status='FAILED';reason='SENDER_PROCESS_OR_STATUS_FAILED';checked_at=[DateTime]::UtcNow.ToString('o');delivery_completed=$null;delivery_completion_not_assumed=$true;not_a_production_signoff=$true}
        }
    }
} finally {
    if ($lock) { $lock.Dispose() }
}
if ($deliveryFailed) { throw 'Operations alert delivery failed; inspect private JSON receipts; no services were restarted' }
if ($operationFailed) { throw 'Operations check/backup has an alert; inspect private JSON report; no automatic restart or data deletion' }
