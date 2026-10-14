#Requires -Version 7.2
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$OutputDirectory,
    [Parameter(Mandatory)][string]$ApplicationImage,
    [Parameter(Mandatory)][string]$SourceLabEnvFile,
    [Parameter(Mandatory)][string]$SshPrivateKey,
    [string]$SshKnownHostsFile,
    [string]$PrometheusUrl,
    [string]$ProjectName = 'storage-lab-console-staging',
    [ValidateRange(1024,65535)][int]$Port = 8446,
    [string]$OpenSsl = 'openssl'
)

# Preparation only: no Docker mutations, global trust changes, source .env
# changes or target-cluster changes. A staging CA is not a production PKI.
$ErrorActionPreference = 'Stop'
$outputPath = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $outputPath) { throw 'Destination exists; refusing to overwrite secrets or data' }
if ($ProjectName -notmatch '^storage-lab-console-staging[a-z0-9_-]*$' -or $ProjectName.Length -gt 64) { throw 'A unique storage-lab-console-staging project name is required' }
if ($ApplicationImage -notmatch '^[A-Za-z0-9][A-Za-z0-9./:_@-]+$') { throw 'Invalid application image reference' }
$opensslCommand = Get-Command $OpenSsl -ErrorAction Stop
$sourcePath = (Resolve-Path -LiteralPath $SourceLabEnvFile).Path
$keyPath = (Resolve-Path -LiteralPath $SshPrivateKey).Path
$sourceValues = @{}
foreach ($line in [IO.File]::ReadAllLines($sourcePath)) {
    if ($line -match '^([A-Z0-9_]+)=([^\r\n]*)$') {
        if ($sourceValues.ContainsKey($matches[1])) { throw 'Duplicate source .env variable' }
        $sourceValues[$matches[1]] = $matches[2]
    }
}
foreach ($required in @('CEPH_EXPECTED_FSID','RBD_HOST','RBD_SSH_USER','UPGRADE_ALLOWED_OSDS','RBD_SSH_HOST_KEY_SHA256')) {
    if (-not $sourceValues[$required]) { throw "Missing required source identity/scope field: $required" }
}
if ($sourceValues['CEPH_EXPECTED_FSID'] -notmatch '^[a-fA-F0-9-]{36}$') { throw 'Invalid source FSID' }
if ($sourceValues['RBD_SSH_HOST_KEY_SHA256'] -notmatch '^SHA256:[A-Za-z0-9+/]{43}=?$') { throw 'Invalid pinned SSH fingerprint' }
if ($PrometheusUrl) {
    $uri = [Uri]$PrometheusUrl
    if ($uri.Scheme -notin @('http','https') -or -not $uri.Host -or $uri.UserInfo -or $uri.Query -or $uri.Fragment -or $uri.AbsolutePath -notin @('/','/metrics')) { throw 'PrometheusUrl must be a verified exporter root or /metrics URL without credentials' }
}
$utf8 = [Text.UTF8Encoding]::new($false)
function Write-NewRuntimeFile([string]$RelativePath, [string]$Content) {
    $path = Join-Path $outputPath $RelativePath
    if (Test-Path -LiteralPath $path) { throw 'Refusing to overwrite generated runtime file' }
    [IO.File]::WriteAllText($path, $Content + "`n", $utf8)
}
function New-SecretHex { [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32)).ToLowerInvariant() }
function Password-Hash([string]$Password) {
    $salt = [Security.Cryptography.RandomNumberGenerator]::GetBytes(32)
    $derived = [Security.Cryptography.Rfc2898DeriveBytes]::Pbkdf2([Text.Encoding]::UTF8.GetBytes($Password), $salt, 600000, [Security.Cryptography.HashAlgorithmName]::SHA256, 32)
    'pbkdf2_sha256$600000$' + [Convert]::ToBase64String($salt) + '$' + [Convert]::ToBase64String($derived)
}
New-Item -ItemType Directory -Path $outputPath | Out-Null
foreach ($directory in @('secrets','config/profiles','nginx','backups','client')) { New-Item -ItemType Directory -Path (Join-Path $outputPath $directory) | Out-Null }
if ($IsWindows) {
    $operatorSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    & icacls $outputPath /inheritance:r /grant:r "*${operatorSid}:(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' *> $null
    if ($LASTEXITCODE -ne 0) { throw 'Failed to restrict staging directory ACL' }
} else {
    & chmod 700 $outputPath
    if ($LASTEXITCODE -ne 0) { throw 'Failed to restrict staging directory permissions' }
}
foreach ($name in @('compose.production.yml','compose.access-control.yml')) { Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination $outputPath }
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'nginx/production.conf') -Destination (Join-Path $outputPath 'nginx/production.conf')
$accounts = @(); $clients = @()
foreach ($role in @('viewer','operator','admin')) {
    $password = New-SecretHex
    $username = "staging-$role"
    $accounts += @{ username=$username; role=$role; password_hash=(Password-Hash $password) }
    $passwordFile = "client/$role.password"
    Write-NewRuntimeFile $passwordFile $password
    $clients += @{role=$role; username=$username; password_file=(Join-Path $outputPath $passwordFile)}
}
Write-NewRuntimeFile 'secrets/console_users.json' (@{version=1;users=$accounts} | ConvertTo-Json -Depth 5)
Write-NewRuntimeFile 'client/accounts.json' (@{accounts=$clients} | ConvertTo-Json -Depth 5)
# Compatibility secret is mounted by the base compose but disabled by overlay.
Write-NewRuntimeFile 'secrets/console_password_hash' (Password-Hash (New-SecretHex))
$databasePassword = New-SecretHex; $runtimePassword = New-SecretHex
Write-NewRuntimeFile 'secrets/postgres_password' $databasePassword
Write-NewRuntimeFile 'secrets/migration_database_url' "postgresql://storage_lab_console:${databasePassword}@postgres:5432/storage_lab_console"
Write-NewRuntimeFile 'secrets/database_runtime_password' $runtimePassword
Write-NewRuntimeFile 'secrets/database_url' "postgresql://storage_lab_runtime:${runtimePassword}@postgres:5432/storage_lab_console"
Write-NewRuntimeFile 'secrets/executor_token' (New-SecretHex)
Copy-Item -LiteralPath $keyPath -Destination (Join-Path $outputPath 'secrets/ssh_private_key')
if ($SshKnownHostsFile) {
    Copy-Item -LiteralPath (Resolve-Path -LiteralPath $SshKnownHostsFile).Path -Destination (Join-Path $outputPath 'secrets/ssh_known_hosts')
    $knownHostsSetting = '/run/secrets/ssh_known_hosts'
} else {
    Write-NewRuntimeFile 'secrets/ssh_known_hosts' ''
    $knownHostsSetting = '' # Fingerprint remains mandatory; not a trust bypass.
}
Write-NewRuntimeFile 'config/profiles/production.yaml' '{}'
$runtime = Get-Content -LiteralPath (Join-Path $PSScriptRoot '.env.production.example') -Raw
$changes = @{
    COMPOSE_PROJECT_NAME=$ProjectName; APP_INSTANCE_ID=$ProjectName; APP_DEPLOYMENT_SCOPE='staging'
    STORAGE_LAB_CONSOLE_IMAGE=$ApplicationImage; CONSOLE_HTTPS_PORT=[string]$Port
    CORS_ORIGINS="https://localhost:${Port},https://127.0.0.1:${Port}"; FEATURE_UPGRADE='true'
    CONSOLE_AUTH_USERNAME=''; RBD_SSH_KNOWN_HOSTS_PATH=$knownHostsSetting
    RBD_SSH_HOST_KEY_REQUIRED='true'; OSD_INFO_COLLECTOR_RUN_AS_SSH_USER='true'
}
# Deliberately do not copy source credentials, DB URL, auth, paths, CORS or flags.
$allowed = @('CLUSTER_ID','CEPH_EXPECTED_FSID','UPGRADE_ALLOWED_OSDS','UPGRADE_ALLOWED_HOSTS','UPGRADE_ALLOWED_POOLS','UPGRADE_ALLOWED_DEVICE_CLASSES','RBD_HOST','RBD_SSH_PORT','RBD_SSH_USER','RBD_SSH_HOST_KEY_SHA256','RBD_SSH_CONNECT_TIMEOUT_MS','OSD_INFO_COLLECTOR_PATH','CAPACITY_COLLECTOR_INTERVAL_SECONDS','CAPACITY_METRICS_MAX_AGE_SECONDS','CAPACITY_INVENTORY_MAX_AGE_SECONDS','PERFORMANCE_ENABLED','PERFORMANCE_SOURCE','PERFORMANCE_PROMETHEUS_URL','PERFORMANCE_COLLECTOR_INTERVAL_SECONDS')
foreach ($name in $allowed) { if ($sourceValues.ContainsKey($name)) { $changes[$name] = $sourceValues[$name] } }
if ($PrometheusUrl) { $changes['PERFORMANCE_PROMETHEUS_URL']=$PrometheusUrl; $changes['PERFORMANCE_SOURCE']='prometheus' }
foreach ($name in $changes.Keys) {
    $value = [string]$changes[$name]
    if ($value -match '[\r\n]') { throw 'Multiline .env values are not supported' }
    if ($runtime -match "(?m)^$name=") { $runtime = [regex]::Replace($runtime, "(?m)^$name=.*$", { param($match) "$name=$value" }.GetNewClosure()) }
    else { $runtime += "`n$name=$value" }
}
Write-NewRuntimeFile '.env' $runtime.TrimEnd()
# Base executor sets this path explicitly, so a fingerprint-only deployment
# needs a reviewed overlay to remove the unused known-hosts-file setting.
Write-NewRuntimeFile 'compose.staging.yml' @"
services:
  executor:
    environment:
      RBD_SSH_KNOWN_HOSTS_PATH: '$knownHostsSetting'
"@
$caKey = Join-Path $outputPath 'client/staging-ca.key'
$caCert = Join-Path $outputPath 'client/staging-ca.crt'
$tlsKey = Join-Path $outputPath 'secrets/tls_private_key.pem'
$tlsCert = Join-Path $outputPath 'secrets/tls_certificate.pem'
$csr = Join-Path $outputPath 'client/localhost.csr'
Write-NewRuntimeFile 'client/leaf.ext' "subjectAltName=DNS:localhost,IP:127.0.0.1`nbasicConstraints=critical,CA:FALSE`nkeyUsage=critical,digitalSignature,keyEncipherment`nextendedKeyUsage=serverAuth"
& $opensslCommand.Source req -x509 -newkey rsa:3072 -sha256 -nodes -days 14 -keyout $caKey -out $caCert -subj '/CN=Storage Lab isolated staging CA' -addext 'basicConstraints=critical,CA:TRUE' -addext 'keyUsage=critical,keyCertSign,cRLSign' *> $null
if ($LASTEXITCODE -ne 0) { throw 'Staging CA generation failed' }
& $opensslCommand.Source req -newkey rsa:3072 -sha256 -nodes -keyout $tlsKey -out $csr -subj '/CN=localhost' *> $null
if ($LASTEXITCODE -ne 0) { throw 'Staging CSR generation failed' }
& $opensslCommand.Source x509 -req -in $csr -CA $caCert -CAkey $caKey -CAcreateserial -days 7 -sha256 -extfile (Join-Path $outputPath 'client/leaf.ext') -out $tlsCert *> $null
if ($LASTEXITCODE -ne 0) { throw 'Staging certificate signing failed' }
& $opensslCommand.Source verify -CAfile $caCert -verify_hostname localhost $tlsCert *> $null
if ($LASTEXITCODE -ne 0) { throw 'Staging certificate verification failed' }
Write-Host "Prepared isolated staging (not started): $outputPath"
Write-Host "URL: https://localhost:$Port"
Write-Host 'No source .env changes, no global certificate trust installation. Reused lab SSH authority is NOT least-privilege acceptance.'
