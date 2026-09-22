[CmdletBinding(SupportsShouldProcess, ConfirmImpact = "Medium")]
param(
    [string]$Server = "127.0.0.1",
    [ValidateRange(1, 65535)]
    [int]$Port = 5432,
    [string]$User = "postgres",
    [ValidatePattern("^[A-Za-z_][A-Za-z0-9_-]*$")]
    [string]$Database = "rgw_console"
)

$ErrorActionPreference = "Stop"

$psql = Get-Command psql -ErrorAction Stop
$createdb = Get-Command createdb -ErrorAction Stop
$pgIsReady = Get-Command pg_isready -ErrorAction Stop

& $pgIsReady.Source -h $Server -p $Port -U $User -d postgres
if ($LASTEXITCODE -ne 0) {
    throw "PostgreSQL is not accepting connections at ${Server}:$Port."
}

$previousPgOptions = [Environment]::GetEnvironmentVariable("PGOPTIONS", "Process")
try {
    $env:PGOPTIONS = "-c default_transaction_read_only=on"
    $exists = & $psql.Source -X -w -h $Server -p $Port -U $User -d postgres `
        -v ON_ERROR_STOP=1 -Atq `
        -c "SELECT 1 FROM pg_database WHERE datname = '$Database';"
    if ($LASTEXITCODE -ne 0) {
        throw "Could not query PostgreSQL. Set PGPASSWORD for this process or configure pgpass."
    }
}
finally {
    [Environment]::SetEnvironmentVariable("PGOPTIONS", $previousPgOptions, "Process")
}

if (($exists | Out-String).Trim() -eq "1") {
    Write-Host "Database '$Database' already exists; nothing changed."
    return
}

if (-not $PSCmdlet.ShouldProcess("${Server}:$Port/$Database", "Create PostgreSQL database")) {
    return
}

& $createdb.Source -w -h $Server -p $Port -U $User --encoding=UTF8 --template=template0 $Database
if ($LASTEXITCODE -ne 0) {
    throw "createdb failed for '$Database'."
}

Write-Host "Created database '$Database'. Run check-postgres.ps1, then run the migration command."
