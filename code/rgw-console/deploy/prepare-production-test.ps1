#Requires -Version 7.2
[CmdletBinding()]
param(
    [string]$OutputDirectory = (Join-Path $PSScriptRoot 'dist/production-test'),
    [string]$ApplicationImage = 'storage-lab-console:production-readonly-check',
    [string]$ProjectName = 'storage-lab-console-production-test',
    [int]$Port = 8443,
    [string]$Username = 'console-admin',
    [string]$OpenSsl = 'openssl'
)

$ErrorActionPreference = 'Stop'
$outputPath = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $outputPath) {
    throw "Output directory exists; refusing to replace config, secrets or data: $outputPath"
}
if ($Port -lt 1024 -or $Port -gt 65535) { throw 'Port must be between 1024 and 65535' }
if ($Username -notmatch '^[A-Za-z0-9._-]{1,128}$') { throw 'Username contains unsupported characters' }
if ($ProjectName -notmatch '^[a-z0-9][a-z0-9_-]{0,63}$') { throw 'ProjectName contains unsupported characters' }
$opensslCommand = Get-Command $OpenSsl -ErrorAction Stop
docker image inspect $ApplicationImage *> $null
if ($LASTEXITCODE -ne 0) { throw "Application image must be available locally: $ApplicationImage" }

$utf8 = [Text.UTF8Encoding]::new($false)
function Write-NewRuntimeFile([string]$RelativePath, [string]$Content) {
    $filePath = Join-Path $outputPath $RelativePath
    if (Test-Path -LiteralPath $filePath) { throw "Refusing to overwrite: $filePath" }
    [IO.File]::WriteAllText($filePath, $Content + "`n", $utf8)
}
function New-SecretHex {
    [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32)).ToLowerInvariant()
}

New-Item -ItemType Directory -Path $outputPath | Out-Null
foreach ($directory in @('secrets', 'config/profiles', 'nginx', 'backups')) {
    New-Item -ItemType Directory -Path (Join-Path $outputPath $directory) | Out-Null
}
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'compose.production.yml') -Destination $outputPath
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'nginx/production.conf') -Destination (Join-Path $outputPath 'nginx/production.conf')

$password = New-SecretHex
$salt = [Security.Cryptography.RandomNumberGenerator]::GetBytes(32)
$passwordBytes = [Text.Encoding]::UTF8.GetBytes($password)
$derived = [Security.Cryptography.Rfc2898DeriveBytes]::Pbkdf2(
    $passwordBytes, $salt, 600000, [Security.Cryptography.HashAlgorithmName]::SHA256, 32
)
$hash = 'pbkdf2_sha256$600000$' + [Convert]::ToBase64String($salt) + '$' + [Convert]::ToBase64String($derived)
Write-NewRuntimeFile 'secrets/console_password_hash' $hash
# The client password is for the operator/test client only. It is never mounted
# into an application container, included in .env, or printed to the console.
Write-NewRuntimeFile 'secrets/console_password' $password
$databasePassword = New-SecretHex
Write-NewRuntimeFile 'secrets/postgres_password' $databasePassword
Write-NewRuntimeFile 'secrets/migration_database_url' "postgresql://storage_lab_console:${databasePassword}@postgres:5432/storage_lab_console"
$runtimePassword = New-SecretHex
Write-NewRuntimeFile 'secrets/database_runtime_password' $runtimePassword
Write-NewRuntimeFile 'secrets/database_url' "postgresql://storage_lab_runtime:${runtimePassword}@postgres:5432/storage_lab_console"
Write-NewRuntimeFile 'secrets/executor_token' (New-SecretHex)
Write-NewRuntimeFile 'config/profiles/production.yaml' '{}'

$runtime = Get-Content -LiteralPath (Join-Path $PSScriptRoot '.env.production.example') -Raw
$changes = @{
    STORAGE_LAB_CONSOLE_IMAGE = $ApplicationImage
    COMPOSE_PROJECT_NAME = $ProjectName
    APP_INSTANCE_ID = $ProjectName
    CONSOLE_HTTPS_PORT = [string]$Port
    CONSOLE_AUTH_USERNAME = $Username
    CORS_ORIGINS = "https://localhost:${Port},https://127.0.0.1:${Port}"
}
foreach ($name in $changes.Keys) {
    $value = $changes[$name]
    $runtime = [regex]::Replace($runtime, "(?m)^$name=.*$", { param($match) "$name=$value" }.GetNewClosure())
}
Write-NewRuntimeFile '.env' $runtime.TrimEnd()

$keyPath = Join-Path $outputPath 'secrets/tls_private_key.pem'
$certificatePath = Join-Path $outputPath 'secrets/tls_certificate.pem'
& $opensslCommand.Source req -x509 -newkey rsa:3072 -sha256 -nodes -days 14 `
    -keyout $keyPath -out $certificatePath -subj '/CN=localhost' `
    -addext 'subjectAltName=DNS:localhost,IP:127.0.0.1' *> $null
if ($LASTEXITCODE -ne 0) { throw 'Local test certificate generation failed; inspect the incomplete output directory' }

if ($IsWindows) {
    # Limit inherited access to generated secrets to the current operator and
    # Windows system/administrators. Docker Desktop reads bind-mounted files.
    $operatorSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    & icacls (Join-Path $outputPath 'secrets') /inheritance:r /grant:r "*${operatorSid}:(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' *> $null
    if ($LASTEXITCODE -ne 0) { throw 'Could not restrict the local secret directory ACL' }
}

Write-Host "Created isolated test config: $(Join-Path $outputPath '.env')"
Write-Host "URL: https://localhost:$Port"
Write-Host "Username: $Username"
Write-Host "Client password file (not mounted): $(Join-Path $outputPath 'secrets/console_password')"
Write-Host 'TLS certificate is for local testing only. Production requires a certificate trusted by the receiving environment.'
