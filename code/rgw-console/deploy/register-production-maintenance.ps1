#Requires -Version 7.2
[CmdletBinding(SupportsShouldProcess, ConfirmImpact='Medium')]
param(
    [Parameter(Mandatory)][string]$DeploymentDirectory,
    [Parameter(Mandatory)][string]$BackupRoot,
    [Parameter(Mandatory)][string]$Python,
    [Parameter(Mandatory)][string]$CaFile,
    [Parameter(Mandatory)][string]$AuthUserFile,
    [string]$DaemonKey,
    [string]$BaseUrl,
    [string]$AlertConfigFile,
    [string]$AlertStateFile,
    [string[]]$AdditionalHostStoragePath = @(),
    [switch]$Install
)
# Explicit opt-in only. This script is not run automatically by image install.
$ErrorActionPreference = 'Stop'
if (-not $IsWindows) { throw 'Use the documented Linux scheduler procedure on Linux' }
$deploymentPath = (Resolve-Path -LiteralPath $DeploymentDirectory).Path
$runtime = Get-Content -LiteralPath (Join-Path $deploymentPath '.env') -Raw
$match = [regex]::Match($runtime, '(?m)^COMPOSE_PROJECT_NAME=(storage-lab-console-(?:production|staging)[a-z0-9_-]{0,64})\r?$')
if (-not $match.Success) { throw 'Explicit deployment project required' }
$project = $match.Groups[1].Value
if ([bool]$AlertConfigFile -ne [bool]$AlertStateFile) { throw 'Alert config and private state paths must be supplied together' }
if ($AdditionalHostStoragePath.Count -gt 1) { throw 'Windows schedule accepts at most one explicit additional storage path; use the manual probe for multiple disks' }
foreach ($value in @($deploymentPath, $BackupRoot, $Python, $CaFile, $AuthUserFile, $DaemonKey, $BaseUrl, $AlertConfigFile, $AlertStateFile, $PSScriptRoot) + $AdditionalHostStoragePath) {
    if ($value -match '["\r\n]') { throw 'Unsafe scheduler argument' }
}
$shell = (Get-Command pwsh).Source
$script = Join-Path $PSScriptRoot 'run-production-maintenance.ps1'
$operator = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $operator -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
foreach ($mode in @('Backup','Check')) {
    if (Get-ScheduledTask -TaskName "$project-$($mode.ToLowerInvariant())" -ErrorAction SilentlyContinue) { throw 'A maintenance task already exists; no tasks were changed' }
}
foreach ($mode in @('Backup','Check')) {
    $name = "$project-$($mode.ToLowerInvariant())"
    if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) { throw "Task exists; refusing to overwrite: $name" }
    $arguments = "-NoProfile -NonInteractive -File `"$script`" -Mode $mode -DeploymentDirectory `"$deploymentPath`" -BackupRoot `"$BackupRoot`" -Python `"$Python`""
    if ($AlertConfigFile) { $arguments += " -AlertConfigFile `"$AlertConfigFile`" -AlertStateFile `"$AlertStateFile`"" }
    if ($mode -eq 'Check') {
        $arguments += " -CaFile `"$CaFile`" -AuthUserFile `"$AuthUserFile`""
        if ($DaemonKey) { $arguments += " -DaemonKey `"$DaemonKey`"" }
        if ($BaseUrl) { $arguments += " -BaseUrl `"$BaseUrl`"" }
        if ($AdditionalHostStoragePath.Count) { $arguments += " -AdditionalHostStoragePath `"$($AdditionalHostStoragePath[0])`"" }
        $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(5) -RepetitionInterval (New-TimeSpan -Minutes 5)
    } else { $trigger = New-ScheduledTaskTrigger -Daily -At '02:00' }
    if ($Install -and $PSCmdlet.ShouldProcess($name, 'Register current-user maintenance task')) {
        $action = New-ScheduledTaskAction -Execute $shell -Argument $arguments
        Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Principal $principal -Settings $settings | Select-Object TaskName,State
    } else { Write-Host "Prepared only; not registered: $name ($mode)" }
}
Write-Host 'Docker Desktop/current-user login must remain available. JSON alerts and nonzero task results still require an approved delivery channel.'
