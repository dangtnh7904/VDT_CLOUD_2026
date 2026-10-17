param(
    [string]$Image = 'storage-lab-console:3.0.0-ssh-readonly-preview.1',
    [string]$SshKeyPath = 'C:\Users\Dang\.ssh\openstack_lab'
)
$ErrorActionPreference = 'Stop'
function Invoke-DockerChecked([string[]]$Arguments) {
    & docker @Arguments
    if ($LASTEXITCODE -ne 0) { throw 'Docker operation failed; existing data was preserved.' }
}
$runtimeEnv = Join-Path $PSScriptRoot '.env.local-readonly'
$configDir = Join-Path $PSScriptRoot 'config'
$tokenPath = Join-Path $PSScriptRoot 'secrets/local_executor_token'
if (-not (Test-Path -LiteralPath $SshKeyPath -PathType Leaf)) { throw 'Configured SSH key does not exist.' }
& (Join-Path $PSScriptRoot 'prepare-local-executor-secret.ps1') -SecretPath $tokenPath
$existing = (& docker inspect storage-lab-console-local-api | ConvertFrom-Json)[0]
$dbMount = @($existing.Mounts | Where-Object { $_.Destination -eq '/run/secrets/database_url' })
$evidenceMount = @($existing.Mounts | Where-Object { $_.Destination -eq '/var/lib/storage-lab-console/evidence' })
if ($dbMount.Count -ne 1 -or $evidenceMount.Count -ne 1 -or $evidenceMount[0].Type -ne 'volume') { throw 'Existing preview storage bindings could not be verified.' }
$envKeys = @(Get-Content -LiteralPath $runtimeEnv | Where-Object { $_ -match '^[A-Z][A-Z0-9_]*=' } | ForEach-Object { $_.Split('=',2)[0] })
$exclude = $envKeys + @('APP_VERSION','APP_REVISION','APP_BUILD_DATE','RBD_SSH_PASSWORD','RBD_EXECUTOR_TOKEN','CEPH_EXECUTOR_TOKEN')
$apiEnvArgs = @()
foreach ($entry in $existing.Config.Env) {
    if ($entry.Split('=',2)[0] -notin $exclude) { $apiEnvArgs += @('--env', $entry) }
}
$common = @('--network','storage-lab-console-local','--env-file',$runtimeEnv,'--read-only','--init','--tmpfs','/tmp:rw,noexec,nosuid,size=64m,mode=1777','--cap-drop','ALL','--security-opt','no-new-privileges','--label','storage-lab-console.scope=local-preview',
    '--mount',"type=bind,source=$configDir,target=/etc/storage-lab-console,readonly",
    '--mount',"type=bind,source=$tokenPath,target=/run/secrets/executor_token,readonly")
$apiStorage = @('--mount',"type=bind,source=$($dbMount[0].Source),target=/run/secrets/database_url,readonly",
    '--mount',"type=volume,source=$($evidenceMount[0].Name),target=/var/lib/storage-lab-console/evidence")
$names = @(& docker ps -a --format '{{.Names}}')
foreach ($name in @('storage-lab-console-local-executor','storage-lab-console-local-capacity','storage-lab-console-local-performance')) {
    if ($name -in $names) { throw "Container $name already exists. Inspect it before replacing an existing configured service." }
}
Invoke-DockerChecked (@('run','-d','--name','storage-lab-console-local-executor','--restart','unless-stopped') + $common + @('--env','PORT=3001','--env','RBD_EXECUTOR_STATE_ROOT=/var/lib/rbd-executor',
    '--mount',"type=bind,source=$SshKeyPath,target=/run/secrets/ssh_private_key,readonly",
    '--mount','type=volume,source=storage-lab-console-local-executor-state,target=/var/lib/rbd-executor',$Image,'executor'))
$savedName = 'storage-lab-console-local-api-before-ssh-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
Invoke-DockerChecked @('stop','--timeout','10','storage-lab-console-local-api')
Invoke-DockerChecked @('rename','storage-lab-console-local-api',$savedName)
Invoke-DockerChecked (@('run','-d','--name','storage-lab-console-local-api','--restart','unless-stopped','--publish','127.0.0.1:8080:8000') + $common + $apiStorage + $apiEnvArgs + @($Image,'api'))
foreach ($collector in @(@('storage-lab-console-local-capacity','capacity-collector'),@('storage-lab-console-local-performance','performance-collector'))) {
    Invoke-DockerChecked (@('run','-d','--name',$collector[0],'--restart','unless-stopped') + $common + $apiStorage + @($Image,$collector[1]))
}
Write-Output "Local read-only services started. Prior API retained as $savedName. Verify /api/ready before collecting evidence."
