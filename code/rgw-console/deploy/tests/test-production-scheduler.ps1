#Requires -Version 7.2
# All ScheduledTasks operations are function doubles; never register a task.
$ErrorActionPreference='Stop'
if (-not $IsWindows) { throw 'Windows scheduler binding test requires Windows' }
$global:slcScheduleActions=@();$global:slcScheduleRegistered=@()
function Get-ScheduledTask { param($TaskName,$ErrorAction) return $null }
function New-ScheduledTaskPrincipal { param($UserId,$LogonType,$RunLevel) return @{UserId=$UserId} }
function New-ScheduledTaskSettingsSet { param([switch]$StartWhenAvailable,$MultipleInstances,$ExecutionTimeLimit) return @{} }
function New-ScheduledTaskTrigger { param([switch]$Once,$At,$RepetitionInterval,[switch]$Daily) return @{} }
function New-ScheduledTaskAction {
    param($Execute,$Argument)
    $global:slcScheduleActions+= $Argument
    return @{Arguments=$Argument}
}
function Register-ScheduledTask {
    param($TaskName,$Action,$Trigger,$Principal,$Settings)
    $global:slcScheduleRegistered+= $TaskName
    return [pscustomobject]@{TaskName=$TaskName;State='UNIT_TEST_ONLY'}
}
$root=Join-Path ([IO.Path]::GetTempPath()) ('slc-scheduler-unit-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $root | Out-Null
[IO.File]::WriteAllText((Join-Path $root '.env'),"COMPOSE_PROJECT_NAME=storage-lab-console-production-scheduler-unit`n")
try {
    & (Join-Path $PSScriptRoot '../register-production-maintenance.ps1') -DeploymentDirectory $root -BackupRoot (Join-Path $root 'backups') -Python 'C:/fake/python.exe' -CaFile 'C:/fake/ca.crt' -AuthUserFile 'C:/fake/accounts.json' -BaseUrl 'https://console.example' -AlertConfigFile 'C:/fake/alert.json' -AlertStateFile 'C:/fake/state.json' -AdditionalHostStoragePath 'C:/fake/docker-disk' -Install -Confirm:$false
    if ($global:slcScheduleActions.Count -ne 2 -or $global:slcScheduleRegistered.Count -ne 2) { throw 'Two action bindings expected' }
    foreach ($arguments in $global:slcScheduleActions) {
        if ([regex]::Matches($arguments,'(?:^|\s)-Python\s').Count -ne 1 -or $arguments -notmatch '-AlertConfigFile' -or $arguments -notmatch '-AlertStateFile') { throw 'Duplicate/missing scheduler parameters' }
        if ($arguments -match '-Mode Check' -and ($arguments -notmatch '-BaseUrl' -or $arguments -notmatch '-AdditionalHostStoragePath')) { throw 'Check target/storage not forwarded' }
        # Parse command-line argument syntax without executing its action.
        $tokens=$null;$errors=$null;[System.Management.Automation.Language.Parser]::ParseInput(('pwsh '+$arguments),[ref]$tokens,[ref]$errors) | Out-Null
        if ($errors.Count) { throw 'Scheduler action quoting invalid' }
    }
} finally {
    $resolved=[IO.Path]::GetFullPath($root);$parent=[IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd([IO.Path]::DirectorySeparatorChar)+[IO.Path]::DirectorySeparatorChar
    if (-not $resolved.StartsWith($parent,[StringComparison]::OrdinalIgnoreCase) -or [IO.Path]::GetFileName($resolved) -notlike 'slc-scheduler-unit-*') { throw 'Unsafe unit-fixture cleanup path' }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
Write-Host 'Scheduler action binding checks PASS: Check+Backup with alerts; no tasks registered'
