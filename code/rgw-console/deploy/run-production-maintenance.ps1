#Requires -Version 7.2
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$DeploymentDirectory,
    [Parameter(Mandatory)][string]$BackupRoot,
    [ValidateSet('Backup','Check')][string]$Mode = 'Check',
    [string]$Python = 'python',
    [string]$CaFile,
    [string]$AuthUserFile,
    [string]$DaemonKey
)
$ErrorActionPreference = 'Stop'
$deploymentPath = (Resolve-Path -LiteralPath $DeploymentDirectory).Path
$backupPath = [IO.Path]::GetFullPath($BackupRoot)
if (-not (Test-Path -LiteralPath (Join-Path $deploymentPath 'compose.production.yml'))) { throw 'Production deployment directory required' }
$runtime = Get-Content -LiteralPath (Join-Path $deploymentPath '.env') -Raw
$match = [regex]::Match($runtime, '(?m)^COMPOSE_PROJECT_NAME=(storage-lab-console-(?:production|staging)[a-z0-9_-]{0,64})\r?$')
if (-not $match.Success) { throw 'Explicit production/staging project required' }
if (-not (Test-Path -LiteralPath $backupPath)) { New-Item -ItemType Directory -Path $backupPath | Out-Null }
$lock = $null
try {
    # OS releases this lock on process exit/crash; no stale PID lock guessing.
    $lock = [IO.File]::Open((Join-Path $deploymentPath 'maintenance.lock'), [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    $run = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8)
    if ($Mode -eq 'Backup') {
        & (Join-Path $PSScriptRoot 'backup-production.ps1') -DeploymentDirectory $deploymentPath -OutputDirectory (Join-Path $backupPath "backup-$run")
        if (-not $?) { throw 'Scheduled backup failed' }
    } else {
        if (-not $CaFile -or -not $AuthUserFile) { throw 'Check requires CA and client account file paths, not inline credentials' }
        $arguments = @((Join-Path $PSScriptRoot '../scripts/production_ops.py'), '--deployment-directory', $deploymentPath, '--backup-root', $backupPath, '--ca-file', $CaFile, '--auth-user-file', $AuthUserFile, '--report', (Join-Path $backupPath "ops-$run.json"))
        if ($DaemonKey) { $arguments += @('--daemon-key', $DaemonKey) }
        & $Python @arguments
        if ($LASTEXITCODE -ne 0) { throw 'Operations alert: inspect the JSON report; no services were restarted' }
    }
} finally {
    if ($lock) { $lock.Dispose() }
}
