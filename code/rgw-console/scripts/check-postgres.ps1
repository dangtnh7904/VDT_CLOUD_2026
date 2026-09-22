[CmdletBinding()]
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
$pgIsReady = Get-Command pg_isready -ErrorAction Stop

& $pgIsReady.Source -h $Server -p $Port -U $User -d postgres
if ($LASTEXITCODE -ne 0) {
    throw "PostgreSQL is not accepting connections at ${Server}:$Port."
}

$previousPgOptions = [Environment]::GetEnvironmentVariable("PGOPTIONS", "Process")
try {
    # Keep this diagnostic session read-only even if a future query is edited.
    $env:PGOPTIONS = "-c default_transaction_read_only=on"
    $exists = & $psql.Source -X -w -h $Server -p $Port -U $User -d postgres `
        -v ON_ERROR_STOP=1 -Atq `
        -c "SELECT 1 FROM pg_database WHERE datname = '$Database';"
    if ($LASTEXITCODE -ne 0) {
        throw "Could not query PostgreSQL. Set PGPASSWORD for this process or configure pgpass."
    }
    if (($exists | Out-String).Trim() -ne "1") {
        throw "Database '$Database' does not exist. Run setup-postgres.ps1 explicitly to create it."
    }

    & $psql.Source -X -w -h $Server -p $Port -U $User -d $Database `
        -v ON_ERROR_STOP=1 -P pager=off `
        -c "SELECT current_database() AS database, current_user AS db_user, current_setting('server_version') AS server_version, current_setting('transaction_read_only') AS read_only;"
    if ($LASTEXITCODE -ne 0) {
        throw "Database '$Database' exists but could not be opened."
    }
}
finally {
    [Environment]::SetEnvironmentVariable("PGOPTIONS", $previousPgOptions, "Process")
}
