#Requires -Version 7.2
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Image,
    [Parameter(Mandatory)][string]$SshKeyFile,
    [string]$RuntimeEnvFile = (Join-Path $PSScriptRoot '.env.local-readonly'),
    [string]$ConfigDirectory = (Join-Path $PSScriptRoot 'config'),
    [string]$DatabaseUrlFile = (Join-Path $PSScriptRoot 'secrets/local_preview_database_url'),
    [string]$TokenFile = (Join-Path $PSScriptRoot 'secrets/local_executor_token'),
    [string]$PostgresImage = 'postgres:16-alpine@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea',
    [string]$OsdMapImage = 'dang7904/storage-lab-osdmap@sha256:baf1c9e802990b88c8910bbb94a45bb80f8de9ec5f0b5eada0dd6076e6a8d893',
    [switch]$WithoutOsdMap,
    [switch]$ValidateOnly
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Docker-Checked([string[]]$Arguments) {
    & docker @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Docker $($Arguments[0]) failed. No existing data or configuration was deleted." }
}
function Resolve-File([string]$Path, [string]$Description) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "$Description file does not exist." }
    return (Resolve-Path -LiteralPath $Path).Path
}
function Assert-Image([string]$Reference) {
    if ($Reference -notmatch '^[a-zA-Z0-9][a-zA-Z0-9./_:-]*(?:@sha256:[a-f0-9]{64})?$' -or
        ($Reference -notmatch '@sha256:[a-f0-9]{64}$' -and $Reference -notmatch ':[a-zA-Z0-9_][a-zA-Z0-9_.-]*$') -or
        $Reference -match ':latest$') {
        throw 'Use an explicit image version tag or sha256 digest, without shell characters or latest.'
    }
}
foreach ($reference in @($Image, $PostgresImage, $OsdMapImage)) { Assert-Image $reference }
$RuntimeEnvFile = Resolve-File $RuntimeEnvFile 'Runtime configuration'
$DatabaseUrlFile = Resolve-File $DatabaseUrlFile 'Database URL secret'
$TokenFile = Resolve-File $TokenFile 'Executor token secret'
$SshKeyFile = Resolve-File $SshKeyFile 'SSH private key'
if (-not (Test-Path -LiteralPath $ConfigDirectory -PathType Container)) { throw 'Config directory does not exist.' }
$ConfigDirectory = (Resolve-Path -LiteralPath $ConfigDirectory).Path
$originalEnvHash = (Get-FileHash -LiteralPath $RuntimeEnvFile -Algorithm SHA256).Hash
$runtime = @{}
foreach ($line in [IO.File]::ReadAllLines($RuntimeEnvFile)) {
    if ([string]::IsNullOrWhiteSpace($line) -or $line.TrimStart().StartsWith('#')) { continue }
    if ($line -notmatch '^([A-Z][A-Z0-9_]*)=(.*)$') { throw 'Runtime configuration must use plain NAME=value lines.' }
    if ($runtime.ContainsKey($Matches[1])) { throw "Duplicate runtime key: $($Matches[1])." }
    $runtime[$Matches[1]] = $Matches[2]
}
foreach ($name in @('DATABASE_URL', 'CEPH_EXECUTOR_TOKEN', 'RBD_EXECUTOR_TOKEN', 'RBD_SSH_PASSWORD', 'APP_VERSION', 'APP_REVISION', 'APP_BUILD_DATE')) {
    if ($runtime.ContainsKey($name) -and $runtime[$name]) { throw "Remove inline or image-owned setting $name from the runtime file; use secret files where applicable." }
}
foreach ($name in @('CLUSTER_ID', 'CEPH_EXPECTED_FSID', 'RBD_HOST', 'RBD_SSH_USER', 'CLUSTER_CONFIG_PATH', 'RBD_SSH_HOST_KEY_SHA256')) {
    if (-not $runtime.ContainsKey($name) -or [string]::IsNullOrWhiteSpace($runtime[$name])) { throw "Required runtime key $name is missing." }
}
if ($runtime['CEPH_EXPECTED_FSID'] -notmatch '^[a-fA-F0-9]{8}-(?:[a-fA-F0-9]{4}-){3}[a-fA-F0-9]{12}$') { throw 'CEPH_EXPECTED_FSID must be the verified cluster UUID.' }
if ($runtime['RBD_SSH_HOST_KEY_SHA256'] -notmatch '^(?:SHA256:)?[A-Za-z0-9+/]{43}=?$') { throw 'RBD_SSH_HOST_KEY_SHA256 must be a verified OpenSSH SHA256 fingerprint.' }
if ($runtime.ContainsKey('RBD_SSH_KNOWN_HOSTS_PATH') -and $runtime['RBD_SSH_KNOWN_HOSTS_PATH']) { throw 'This localhost installer uses the verified SSH fingerprint; remove an unmounted known-hosts path or use the production installer.' }
if ($runtime['CLUSTER_CONFIG_PATH'] -notmatch '^/etc/storage-lab-console/(profiles/[A-Za-z0-9._-]+\.ya?ml)$') { throw 'CLUSTER_CONFIG_PATH must point to a YAML file in /etc/storage-lab-console/profiles.' }
$profileRelativePath = $Matches[1]
Resolve-File (Join-Path $ConfigDirectory $profileRelativePath) 'Cluster profile' | Out-Null
if ([IO.File]::ReadAllText($TokenFile).Trim().Length -lt 32) { throw 'Executor token secret must contain at least 32 characters.' }
if ([IO.File]::ReadAllText($SshKeyFile) -notmatch '-----BEGIN (?:OPENSSH |RSA |EC |DSA |ENCRYPTED )?PRIVATE KEY-----') { throw 'SSH key file does not contain a recognized private key header.' }

# Never print the database URL, password, token, private key, or full Compose config.
try { $databaseUri = [Uri]::new([IO.File]::ReadAllText($DatabaseUrlFile).Trim()) } catch { throw 'Database URL secret is not a valid URI.' }
if ($databaseUri.Scheme -notin @('postgresql', 'postgres') -or
    $databaseUri.Host -ne 'storage-lab-console-local-postgres' -or
    $databaseUri.Port -notin @(-1, 5432) -or $databaseUri.AbsolutePath -ne '/storage_lab_console' -or
    $databaseUri.Query -or $databaseUri.Fragment) {
    throw 'Local database URL must target storage-lab-console-local-postgres:5432/storage_lab_console, without query parameters.'
}
$databaseCredentials = $databaseUri.UserInfo.Split(':', 2)
if ($databaseCredentials.Count -ne 2 -or [Uri]::UnescapeDataString($databaseCredentials[0]) -ne 'storage_lab_console') { throw 'Local database URL must use the storage_lab_console role and a password.' }
$databasePassword = [Uri]::UnescapeDataString($databaseCredentials[1])
if ($databasePassword.Length -lt 16 -or $databasePassword -match '[\r\n\x00]') { throw 'Local database password must contain at least 16 characters and no line breaks.' }
$postgresPasswordFile = Join-Path (Split-Path -Parent $DatabaseUrlFile) 'local_postgres_password'
if (Test-Path -LiteralPath $postgresPasswordFile) {
    if (-not (Test-Path -LiteralPath $postgresPasswordFile -PathType Leaf) -or
        [IO.File]::ReadAllText($postgresPasswordFile).TrimEnd("`r", "`n") -cne $databasePassword) {
        throw 'Existing PostgreSQL password file does not match the database URL. It was preserved.'
    }
}

$composePath = Join-Path $PSScriptRoot 'compose.local-readonly.yml'
$composeArguments = @('compose', '--project-name', 'storage-lab-console-local', '--file', $composePath)
if (-not $WithoutOsdMap) { $composeArguments += @('--profile', 'osdmap') }
$installationEnvironment = @{
    SLC_LOCAL_IMAGE = $Image
    SLC_LOCAL_POSTGRES_IMAGE = $PostgresImage
    SLC_LOCAL_OSDMAP_IMAGE = $OsdMapImage
    SLC_LOCAL_ENV_FILE = $RuntimeEnvFile
    SLC_LOCAL_CONFIG_DIR = $ConfigDirectory
    SLC_LOCAL_DATABASE_URL_FILE = $DatabaseUrlFile
    SLC_LOCAL_TOKEN_FILE = $TokenFile
    SLC_LOCAL_SSH_KEY_FILE = $SshKeyFile
    SLC_LOCAL_POSTGRES_PASSWORD_FILE = $postgresPasswordFile
}
$savedEnvironment = @{}
try {
    foreach ($entry in $installationEnvironment.GetEnumerator()) {
        $savedEnvironment[$entry.Key] = [Environment]::GetEnvironmentVariable($entry.Key, 'Process')
        [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value, 'Process')
    }
    Docker-Checked ($composeArguments + @('--profile', 'setup', 'config', '--quiet'))
    if ($ValidateOnly) {
        Write-Output 'Configuration and Compose syntax are valid. No containers, volumes, secret files, or runtime configuration were changed.'
        return
    }
    $reservedNames = @('storage-lab-console-local-postgres', 'storage-lab-console-local-api',
        'storage-lab-console-local-executor', 'storage-lab-console-local-capacity',
        'storage-lab-console-local-performance', 'storage-lab-console-local-osdmap')
    $existingNames = @(Docker-Checked @('ps', '-a', '--format', '{{.Names}}'))
    if (@($reservedNames | Where-Object { $_ -in $existingNames }).Count) {
        throw 'Local console containers already exist. This fresh installer never replaces or removes them; use the documented update or reviewed cleanup procedure.'
    }
    foreach ($reference in @($Image, $PostgresImage)) { Docker-Checked @('pull', $reference) }
    if (-not $WithoutOsdMap) { Docker-Checked @('pull', $OsdMapImage) }
    if (-not (Test-Path -LiteralPath $postgresPasswordFile)) {
        New-Item -ItemType File -Path $postgresPasswordFile | Out-Null
        if ($IsWindows) {
            $operatorSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
            & icacls $postgresPasswordFile /inheritance:r /grant:r "*${operatorSid}:F" '*S-1-5-18:F' '*S-1-5-32-544:F' *> $null
            if ($LASTEXITCODE -ne 0) { throw 'Could not restrict the generated PostgreSQL password file ACL.' }
        } else {
            & chmod 600 $postgresPasswordFile
            if ($LASTEXITCODE -ne 0) { throw 'Could not restrict the generated PostgreSQL password file permissions.' }
        }
        [IO.File]::WriteAllText($postgresPasswordFile, $databasePassword, [Text.UTF8Encoding]::new($false))
    }
    Docker-Checked ($composeArguments + @('--profile', 'setup', 'run', '--rm', '--no-deps', 'init-permissions'))
    Docker-Checked ($composeArguments + @('up', '-d', '--wait', '--wait-timeout', '100', 'postgres'))
    Docker-Checked ($composeArguments + @('--profile', 'setup', 'run', '--rm', '--no-deps', 'migrate'))
    $services = @('executor', 'api', 'capacity', 'performance')
    if (-not $WithoutOsdMap) { $services += 'osdmap' }
    Docker-Checked ($composeArguments + @('up', '-d', '--wait', '--wait-timeout', '150') + $services)
    $ready = $false
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        try {
            $status = Invoke-RestMethod -Uri 'http://127.0.0.1:8080/api/ready' -TimeoutSec 5
            if ($status.ready -eq $true) { $ready = $true; break }
        } catch { }
        Start-Sleep -Seconds 2
    }
    if (-not $ready) { throw 'Containers started, but /api/ready did not become ready. Installation is incomplete; inspect service logs. Configuration and database were preserved.' }
    Write-Output 'Read-only console is ready at http://127.0.0.1:8080/. Runtime .env, SSH key, profile, and original secret files were preserved.'
    if ($WithoutOsdMap) { Write-Output 'Offline OSDMap worker was omitted; OSDMap preview is unavailable until it is installed.' }
} finally {
    foreach ($entry in $savedEnvironment.GetEnumerator()) { [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value, 'Process') }
    $databasePassword = $null
    $databaseCredentials = $null
    $databaseUri = $null
    if ((Get-FileHash -LiteralPath $RuntimeEnvFile -Algorithm SHA256).Hash -ne $originalEnvHash) { throw 'Runtime .env changed during installation; review the file before continuing.' }
}
