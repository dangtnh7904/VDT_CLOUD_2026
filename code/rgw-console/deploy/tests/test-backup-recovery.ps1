#Requires -Version 7.2
# Execute ONLY the parsed finally block with in-memory Docker doubles.
# Never invoke the real CLI or top-level backup/deployment code.
$ErrorActionPreference='Stop'
$tokens=$null; $errors=$null
$source=Join-Path $PSScriptRoot '../backup-production.ps1'
$ast=[System.Management.Automation.Language.Parser]::ParseFile($source,[ref]$tokens,[ref]$errors)
if ($errors.Count) { throw 'Backup source parse failed' }
$try=@($ast.EndBlock.Statements | Where-Object { $_ -is [System.Management.Automation.Language.TryStatementAst] })[-1]
if (-not $try.Finally) { throw 'Backup recovery block missing' }
$body=$try.Finally.Extent.Text
$block=[scriptblock]::Create($body.Substring(1,$body.Length-2))
$project='storage-lab-console-staging-recovery-unit'
$databaseName='1'*64; $helperName='fake-helper'
$dumpPath='/tmp/fake-dump'; $asIsExportPath='/tmp/fake-asis'; $auditExportPath='/tmp/fake-audit'
$asIsCheckpointPath=Join-Path ([IO.Path]::GetTempPath()) ([guid]::NewGuid().ToString('N')+'.not-created')
$operationId='fake-operation'; $stopped=@(('a'*64),('b'*64),('c'*64))
function docker {
    # All native cleanup commands are absorbed here. No filesystem write.
    $global:LASTEXITCODE=1
    if ($args[0] -eq 'exec') {
        $script:cleanupAttempts++
        if ($script:cleanupThrows) { throw 'Synthetic native invocation failure' }
        $global:LASTEXITCODE=if ($script:cleanupFails) { 1 } else { 0 }
        return
    }
    if ($args[0] -eq 'inspect') {
        if ($script:failHelperShape) { return 'not-json' }
        return '[]'
    }
}
function Inspect-Container([string]$Id) {
    $script:inspected+= $Id
    if ($Id -eq $script:missingId) { throw 'Synthetic missing ID' }
    $label=if ($Id -eq $script:wrongProjectId) { 'other-project' } else { $project }
    @{Id=$Id;Config=@{Labels=@{'com.docker.compose.project'=$label}}}
}
function Invoke-Docker([string[]]$Arguments) {
    if ($Arguments[0] -ne 'start' -or $Arguments.Count -ne 2 -or $Arguments[1] -notin $stopped) { throw 'Unexpected operation in recovery test double' }
    $script:started+= $Arguments[1]
    if ($Arguments[1] -eq $script:failedStartId) { throw 'Synthetic start failure' }
}
$cases=@(
    @{name='all restored';missing=$null;wrong=$null;start=$null;helper=$false;expected=@($stopped);throws=$false},
    @{name='first ID missing';missing=$stopped[0];wrong=$null;start=$null;helper=$false;expected=@($stopped[1],$stopped[2]);throws=$true},
    @{name='first project wrong';missing=$null;wrong=$stopped[0];start=$null;helper=$false;expected=@($stopped[1],$stopped[2]);throws=$true},
    @{name='first start failed';missing=$null;wrong=$null;start=$stopped[0];helper=$false;expected=@($stopped);throws=$true},
    @{name='helper cleanup failed';missing=$null;wrong=$null;start=$null;helper=$true;expected=@($stopped);throws=$true},
    @{name='transient cleanup nonzero still recovers';cleanupFails=$true;missing=$null;wrong=$null;start=$null;helper=$false;expected=@($stopped);throws=$true},
    @{name='terminating cleanup still recovers';cleanupThrows=$true;missing=$null;wrong=$null;start=$null;helper=$false;expected=@($stopped);throws=$true}
)
foreach ($case in $cases) {
    $script:started=@();$script:inspected=@();$script:missingId=$case.missing
    $script:wrongProjectId=$case.wrong;$script:failedStartId=$case.start;$script:failHelperShape=$case.helper
    $script:cleanupAttempts=0;$script:cleanupFails=$case.cleanupFails;$script:cleanupThrows=$case.cleanupThrows
    $threw=$false
    try { & $block } catch { $threw=$true }
    if ($threw -ne $case.throws -or ($script:started -join ',') -ne ($case.expected -join ',') -or ($script:inspected -join ',') -ne ($stopped -join ',') -or $script:cleanupAttempts -ne 3) { throw "Recovery test failed: $($case.name)" }
}
Write-Host "Backup recovery checks PASS: $($cases.Count); Docker doubles only, no deployment actions"
