param([string]$SecretPath = (Join-Path $PSScriptRoot 'secrets/local_executor_token'))
$ErrorActionPreference = 'Stop'
# Generate a runtime secret without putting its value in command-line arguments,
# source files, terminal output, or image layers. Existing tokens are preserved.
if (-not (Test-Path -LiteralPath $SecretPath)) {
    $bytes = New-Object byte[] 48
    $random = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $random.GetBytes($bytes) } finally { $random.Dispose() }
    $token = [Convert]::ToBase64String($bytes)
    [System.IO.File]::WriteAllText($SecretPath, $token, [System.Text.UTF8Encoding]::new($false))
}
$value = [System.IO.File]::ReadAllText($SecretPath).Trim()
if ($value.Length -lt 32) { throw 'Existing executor token is invalid; it was preserved.' }
Write-Output 'Executor runtime secret is ready; value not displayed.'
