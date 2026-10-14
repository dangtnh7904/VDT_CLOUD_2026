param(
    [string]$Image = 'dang7904/storage-lab-console@sha256:49f5284d27fd4defe2e2804e3b4eb06eaa3ac19352026622de3eae6c417fbe1f',
    [string]$OsdMapImage = 'dang7904/storage-lab-osdmap@sha256:baf1c9e802990b88c8910bbb94a45bb80f8de9ec5f0b5eada0dd6076e6a8d893'
)
$ErrorActionPreference = 'Stop'
function Docker-Checked([string[]]$Arguments) {
    & docker @Arguments
    if ($LASTEXITCODE -ne 0) { throw 'Docker operation failed. Previous containers and database volumes were retained.' }
}
$serviceNames = @('storage-lab-console-local-executor','storage-lab-console-local-api','storage-lab-console-local-capacity','storage-lab-console-local-performance')
$specifications = @{}
foreach ($serviceName in $serviceNames) {
    $specification = (& docker inspect $serviceName | ConvertFrom-Json)[0]
    if ($LASTEXITCODE -ne 0 -or $specification.Config.Labels.'storage-lab-console.scope' -ne 'local-preview') {
        throw "Container $serviceName is not the verified local preview."
    }
    $specifications[$serviceName] = $specification
}
$workerName = 'storage-lab-console-local-osdmap'
if ($workerName -in @(& docker ps -a --format '{{.Names}}')) {
    $workerSpecification = (& docker inspect $workerName | ConvertFrom-Json)[0]
    if ($LASTEXITCODE -ne 0 -or $workerSpecification.Config.Labels.'storage-lab-console.scope' -ne 'local-preview') {
        throw 'OSDMap worker is not the verified local preview.'
    }
}
Docker-Checked @('image','inspect',$Image,'--format','{{.Id}}')
Docker-Checked @('image','inspect',$OsdMapImage,'--format','{{.Id}}')
$runtimeEnv = Join-Path $PSScriptRoot '.env.local-readonly'
$overrideKeys = @(Get-Content -LiteralPath $runtimeEnv | Where-Object { $_ -match '^[A-Z][A-Z0-9_]*=' } | ForEach-Object { $_.Split('=',2)[0] })
$excludeKeys = $overrideKeys + @('APP_VERSION','APP_REVISION','APP_BUILD_DATE','OSDMAP_PREVIEW_SPOOL',
    'FEATURE_BENCHMARK','FEATURE_QOS','BENCHMARK_WRITES_ENABLED','BENCHMARK_RUNNER_ENABLED','BENCHMARK_ALLOWED_POOLS',
    'BENCHMARK_ASSETS_PATH','BENCHMARK_RUNNER_PATH','BENCHMARK_RUNNER_REGISTRY','RBD_FIO_ENABLED','RBD_WARP_ENABLED')
$spoolVolume = 'storage-lab-console-local-osdmap-spool'
Docker-Checked @('volume','create',$spoolVolume)
Docker-Checked @('run','--rm','--network','none','--user','0:0','--cap-drop','ALL','--cap-add','CHOWN',
    '--mount',"type=volume,source=$spoolVolume,target=/spool",'--entrypoint','/bin/chown',$OsdMapImage,'10001:10001','/spool')
function Clone-Arguments($specification, [bool]$apiRole) {
    $arguments = @('--network','storage-lab-console-local','--env-file',$runtimeEnv,'--read-only','--init',
        '--tmpfs','/tmp:rw,noexec,nosuid,size=128m,mode=1777','--cap-drop','ALL','--security-opt','no-new-privileges',
        '--label','storage-lab-console.scope=local-preview')
    foreach ($entry in $specification.Config.Env) {
        if ($entry.Split('=',2)[0] -notin $excludeKeys) { $arguments += @('--env',$entry) }
    }
    foreach ($binding in $specification.Mounts) {
        if ($binding.Destination -eq '/var/lib/storage-lab-console/osdmap-spool') { continue }
        if ($binding.Type -notin @('volume','bind')) { continue }
        $source = if ($binding.Type -eq 'volume') { $binding.Name } else { $binding.Source }
        $mount = "type=$($binding.Type),source=$source,target=$($binding.Destination)"
        if (-not $binding.RW) { $mount += ',readonly' }
        $arguments += @('--mount',$mount)
    }
    if ($apiRole) {
        $arguments += @('--env','OSDMAP_PREVIEW_SPOOL=/var/lib/storage-lab-console/osdmap-spool',
            '--mount',"type=volume,source=$spoolVolume,target=/var/lib/storage-lab-console/osdmap-spool")
    }
    return $arguments
}
# Additive migration only. Existing history and applied migration checksums remain.
$migrateArguments = Clone-Arguments $specifications['storage-lab-console-local-api'] $true
Docker-Checked (@('run','--rm') + $migrateArguments + @($Image,'migrate'))
$existingWorkers = @(& docker ps -a --format '{{.Names}}')
$suffix = Get-Date -Format 'yyyyMMdd-HHmmss'
if ($workerName -in $existingWorkers) {
    Docker-Checked @('stop','--timeout','10',$workerName)
    Docker-Checked @('rename',$workerName,"$workerName-before-v5-$suffix")
}
Docker-Checked @('run','-d','--name',$workerName,'--restart','unless-stopped','--network','none','--read-only','--init',
    '--user','10001:10001','--cpus','1','--memory','1536m','--pids-limit','32','--cap-drop','ALL',
    '--security-opt','no-new-privileges','--tmpfs','/tmp:rw,noexec,nosuid,size=128m,mode=1777',
    '--label','storage-lab-console.scope=local-preview','--mount',"type=volume,source=$spoolVolume,target=/spool",$OsdMapImage)
foreach ($serviceName in $serviceNames) {
    $specification = $specifications[$serviceName]
    Docker-Checked @('stop','--timeout','10',$serviceName)
    $savedName = "$serviceName-before-v5-$suffix"
    Docker-Checked @('rename',$serviceName,$savedName)
    Docker-Checked @('network','disconnect','storage-lab-console-local',$savedName)
    $apiRole = $serviceName -eq 'storage-lab-console-local-api'
    $arguments = Clone-Arguments $specification $apiRole
    if ($apiRole) { $arguments += @('--publish','127.0.0.1:8080:8000') }
    Docker-Checked (@('run','-d','--name',$serviceName,'--restart','unless-stopped') + $arguments + @($Image) + $specification.Config.Cmd)
}
Write-Output 'Local v5 services updated. Previous containers retained; volumes and historical evidence preserved. Check /api/ready and live workflows.'
