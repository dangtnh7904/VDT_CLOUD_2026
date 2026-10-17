[CmdletBinding()]
param(
    [switch]$Execute,
    [string]$OutputRoot = (Join-Path $PSScriptRoot '..\evidence\as-is'),
    [string]$RunId = ('h3-as-is-{0}' -f [DateTimeOffset]::UtcNow.ToString('yyyyMMddTHHmmssZ')),
    [string]$CephCommand = 'ceph',
    [string]$RepresentativeDaemon = '',
    [switch]$IncludeConfiguration,
    [switch]$IncludeServiceSpecs
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ($RunId -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$') {
    throw 'RunId must contain only letters, digits, dot, underscore, or hyphen (maximum 96 characters).'
}

$commands = [System.Collections.Generic.List[object]]::new()

function Add-CaptureCommand {
    param(
        [Parameter(Mandatory)][string]$Id,
        [Parameter(Mandatory)][string[]]$AsIds,
        [Parameter(Mandatory)][string]$Description,
        [Parameter(Mandatory)][string[]]$Arguments,
        [switch]$Sensitive
    )

    $commands.Add([pscustomobject]@{
        id = $Id
        as_ids = $AsIds
        description = $Description
        executable = $CephCommand
        arguments = $Arguments
        sensitive = [bool]$Sensitive
    })
}

Add-CaptureCommand -Id 'cluster-status' -AsIds @('AS-002') -Description 'Cluster status baseline' -Arguments @('status', '-f', 'json-pretty')
Add-CaptureCommand -Id 'health-detail' -AsIds @('AS-002', 'AS-023') -Description 'Detailed health baseline' -Arguments @('health', 'detail', '-f', 'json-pretty')
Add-CaptureCommand -Id 'df-detail' -AsIds @('AS-002') -Description 'Capacity and pool baseline' -Arguments @('df', 'detail', '-f', 'json-pretty')
Add-CaptureCommand -Id 'versions' -AsIds @('AS-003') -Description 'Daemon version coverage' -Arguments @('versions', '-f', 'json-pretty')
Add-CaptureCommand -Id 'orch-ps' -AsIds @('AS-003', 'AS-009') -Description 'Orchestrated daemon and image inventory' -Arguments @('orch', 'ps', '-f', 'json-pretty')
Add-CaptureCommand -Id 'quorum-status' -AsIds @('AS-004') -Description 'MON quorum state' -Arguments @('quorum_status', '-f', 'json-pretty')
Add-CaptureCommand -Id 'mon-dump' -AsIds @('AS-004') -Description 'MonMap and MON feature baseline' -Arguments @('mon', 'dump', '-f', 'json-pretty')
Add-CaptureCommand -Id 'osd-dump' -AsIds @('AS-005') -Description 'OSDMap and release flags' -Arguments @('osd', 'dump', '-f', 'json-pretty')
Add-CaptureCommand -Id 'osd-tree' -AsIds @('AS-005') -Description 'OSD topology and state' -Arguments @('osd', 'tree', '-f', 'json-pretty')
Add-CaptureCommand -Id 'crush-dump' -AsIds @('AS-005') -Description 'CRUSH topology and rules' -Arguments @('osd', 'crush', 'dump', '-f', 'json-pretty')
Add-CaptureCommand -Id 'osd-metadata' -AsIds @('AS-006') -Description 'OSD backend and host metadata' -Arguments @('osd', 'metadata', '-f', 'json-pretty')
Add-CaptureCommand -Id 'device-ls' -AsIds @('AS-006') -Description 'Ceph device inventory' -Arguments @('device', 'ls', '-f', 'json-pretty')
Add-CaptureCommand -Id 'orch-host-ls' -AsIds @('AS-008', 'AS-020') -Description 'Orchestrator host, label, and status inventory' -Arguments @('orch', 'host', 'ls', '--detail', '-f', 'json-pretty')
Add-CaptureCommand -Id 'mgr-dump' -AsIds @('AS-010') -Description 'MGR active and standby state' -Arguments @('mgr', 'dump', '-f', 'json-pretty')
Add-CaptureCommand -Id 'mgr-module-ls' -AsIds @('AS-010') -Description 'MGR module inventory' -Arguments @('mgr', 'module', 'ls', '-f', 'json-pretty')
Add-CaptureCommand -Id 'mgr-services' -AsIds @('AS-010', 'AS-011') -Description 'MGR service endpoints' -Arguments @('mgr', 'services', '-f', 'json-pretty') -Sensitive
Add-CaptureCommand -Id 'pg-stat' -AsIds @('AS-012') -Description 'PG state baseline' -Arguments @('pg', 'stat', '-f', 'json-pretty')
Add-CaptureCommand -Id 'osd-perf' -AsIds @('AS-012', 'AS-022') -Description 'OSD latency baseline' -Arguments @('osd', 'perf', '-f', 'json-pretty')
Add-CaptureCommand -Id 'osd-df-tree' -AsIds @('AS-012') -Description 'OSD utilization baseline' -Arguments @('osd', 'df', 'tree', '-f', 'json-pretty')
Add-CaptureCommand -Id 'pool-ls-detail' -AsIds @('AS-014') -Description 'RADOS pool detail' -Arguments @('osd', 'pool', 'ls', 'detail', '-f', 'json-pretty')
Add-CaptureCommand -Id 'fs-dump' -AsIds @('AS-016') -Description 'CephFS map and feature baseline' -Arguments @('fs', 'dump', '-f', 'json-pretty')
Add-CaptureCommand -Id 'fs-status' -AsIds @('AS-016') -Description 'CephFS status baseline' -Arguments @('fs', 'status', '-f', 'json-pretty')
Add-CaptureCommand -Id 'mds-stat' -AsIds @('AS-016') -Description 'MDS rank and standby summary' -Arguments @('mds', 'stat', '-f', 'json-pretty')

if ($IncludeConfiguration) {
    Add-CaptureCommand -Id 'config-dump' -AsIds @('AS-007') -Description 'Stored cluster configuration (redacted)' -Arguments @('config', 'dump', '-f', 'json-pretty') -Sensitive
    if ($RepresentativeDaemon) {
        Add-CaptureCommand -Id 'config-show-with-defaults' -AsIds @('AS-007') -Description 'Representative effective configuration (redacted)' -Arguments @('config', 'show-with-defaults', $RepresentativeDaemon, '-f', 'json-pretty') -Sensitive
    }
}

if ($IncludeServiceSpecs) {
    Add-CaptureCommand -Id 'orch-ls-export' -AsIds @('AS-008', 'AS-017') -Description 'Orchestrator service specs (redacted)' -Arguments @('orch', 'ls', '--export') -Sensitive
}

function Format-CommandLine {
    param([Parameter(Mandatory)][object]$Command)

    $parts = @($Command.executable) + @($Command.arguments | ForEach-Object {
        if ($_ -match '[\s"]') {
            '"{0}"' -f ($_ -replace '"', '\"')
        } else {
            $_
        }
    })
    return ($parts -join ' ')
}

Write-Output ('Capture plan: {0} commands' -f $commands.Count)
foreach ($command in $commands) {
    Write-Output ('[{0}] {1} :: {2}' -f $command.id, ($command.as_ids -join ','), (Format-CommandLine -Command $command))
}

if (-not $Execute) {
    Write-Output ''
    Write-Output 'PLAN ONLY: no cluster command was executed and no evidence directory was created.'
    Write-Output 'Review the plan, read-only credentials, redaction policy, and output path; add -Execute only after authorization.'
    exit 0
}

$resolvedTool = Get-Command -Name $CephCommand -ErrorAction Stop
$bundlePath = [System.IO.Path]::GetFullPath((Join-Path $OutputRoot $RunId))
if (Test-Path -LiteralPath $bundlePath) {
    throw "Evidence bundle already exists and will not be overwritten: $bundlePath"
}

$null = New-Item -ItemType Directory -Path $bundlePath
$null = New-Item -ItemType Directory -Path (Join-Path $bundlePath 'commands')

function Redact-Text {
    param([AllowEmptyString()][string]$Text)

    if ([string]::IsNullOrEmpty($Text)) {
        return $Text
    }

    $result = $Text
    $keyPattern = '(?im)("?(?:secret|password|token|access[_-]?key|secret[_-]?key|private[_-]?key|keyring|credential|admin[_-]?key)[^"\r\n]*"?\s*[:=]\s*)("(?:\\.|[^"\\])*"|[^,}\r\n]*)'
    $result = [regex]::Replace($result, $keyPattern, '${1}"***REDACTED***"')
    $result = [regex]::Replace($result, '(?i)(https?://)[^/@:\s]+:[^/@\s]+@', '$1***REDACTED***@')
    $result = [regex]::Replace($result, '(?im)(\b(?:key|secret)\s*=\s*)[A-Za-z0-9+/]{24,}={0,2}', '$1***REDACTED***')
    return $result
}

function Invoke-CaptureCommand {
    param(
        [Parameter(Mandatory)][object]$Command,
        [Parameter(Mandatory)][string]$CommandDirectory
    )

    $started = [DateTimeOffset]::UtcNow
    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    $psi = [System.Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = $resolvedTool.Source
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true
    foreach ($argument in $Command.arguments) {
        $null = $psi.ArgumentList.Add([string]$argument)
    }

    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $psi
    $null = $process.Start()
    $stdoutTask = $process.StandardOutput.ReadToEndAsync()
    $stderrTask = $process.StandardError.ReadToEndAsync()
    $process.WaitForExit()
    $stdout = $stdoutTask.GetAwaiter().GetResult()
    $stderr = $stderrTask.GetAwaiter().GetResult()
    $stopwatch.Stop()

    if ($Command.sensitive) {
        $stdout = Redact-Text -Text $stdout
        $stderr = Redact-Text -Text $stderr
    }

    $prefix = Join-Path $CommandDirectory $Command.id
    [System.IO.File]::WriteAllText("$prefix.stdout.txt", $stdout, [System.Text.UTF8Encoding]::new($false))
    [System.IO.File]::WriteAllText("$prefix.stderr.txt", $stderr, [System.Text.UTF8Encoding]::new($false))
    $metadata = [ordered]@{
        id = $Command.id
        as_ids = @($Command.as_ids)
        description = $Command.description
        command = Format-CommandLine -Command $Command
        sensitive_output_redacted = [bool]$Command.sensitive
        started_utc = $started.ToString('o')
        duration_ms = $stopwatch.ElapsedMilliseconds
        exit_code = $process.ExitCode
        stdout_file = "commands/$($Command.id).stdout.txt"
        stderr_file = "commands/$($Command.id).stderr.txt"
    }
    $metadataJson = $metadata | ConvertTo-Json -Depth 6
    [System.IO.File]::WriteAllText("$prefix.meta.json", $metadataJson + "`n", [System.Text.UTF8Encoding]::new($false))
    return $metadata
}

$runMetadata = [ordered]@{
    schema_version = 1
    run_id = $RunId
    created_utc = [DateTimeOffset]::UtcNow.ToString('o')
    collector_host = [Environment]::MachineName
    collector_user = [Environment]::UserName
    ceph_command = $resolvedTool.Source
    representative_daemon = $RepresentativeDaemon
    include_configuration = [bool]$IncludeConfiguration
    include_service_specs = [bool]$IncludeServiceSpecs
    comparison = 'quincy-17.2.7-to-reef-18.2.7'
    base_sha = 'b12291d110049b2f35e32e0de30d70e9a4c060d2'
    target_sha = '6b0e988052ec84cf2d4a54ff9bbbc5e720b621ad'
}
[System.IO.File]::WriteAllText((Join-Path $bundlePath 'run.json'), (($runMetadata | ConvertTo-Json -Depth 6) + "`n"), [System.Text.UTF8Encoding]::new($false))
[System.IO.File]::WriteAllText((Join-Path $bundlePath 'commands.json'), (($commands | ConvertTo-Json -Depth 8) + "`n"), [System.Text.UTF8Encoding]::new($false))

$results = [System.Collections.Generic.List[object]]::new()
foreach ($command in $commands) {
    Write-Output ('EXEC [{0}] {1}' -f $command.id, $command.description)
    $result = Invoke-CaptureCommand -Command $command -CommandDirectory (Join-Path $bundlePath 'commands')
    $results.Add($result)
}
[System.IO.File]::WriteAllText((Join-Path $bundlePath 'results.json'), (($results | ConvertTo-Json -Depth 8) + "`n"), [System.Text.UTF8Encoding]::new($false))

$manifestLines = [System.Collections.Generic.List[string]]::new()
$bundleFiles = Get-ChildItem -LiteralPath $bundlePath -File -Recurse | Where-Object { $_.Name -ne 'MANIFEST.sha256' } | Sort-Object FullName
foreach ($file in $bundleFiles) {
    $relative = [System.IO.Path]::GetRelativePath($bundlePath, $file.FullName).Replace('\', '/')
    $hash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    $manifestLines.Add("$hash  $relative")
}
[System.IO.File]::WriteAllLines((Join-Path $bundlePath 'MANIFEST.sha256'), $manifestLines, [System.Text.UTF8Encoding]::new($false))

$failed = @($results | Where-Object { $_.exit_code -ne 0 })
Write-Output ('Bundle: {0}' -f $bundlePath)
Write-Output ('Commands: {0}; failed: {1}' -f $results.Count, $failed.Count)
if ($failed.Count -gt 0) {
    Write-Warning ('Read-only capture completed with failed commands: {0}' -f (($failed | ForEach-Object { $_.id }) -join ', '))
    exit 2
}

exit 0
