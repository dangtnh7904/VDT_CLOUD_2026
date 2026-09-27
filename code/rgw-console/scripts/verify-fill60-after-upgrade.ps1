[CmdletBinding()]
param(
    [string]$ApiBase = "http://127.0.0.1:8000",
    [string]$Bucket = "rgw-lab-data",
    [string]$ClientId = "fill60",
    [string]$FillPrefix = "capacity-fill/20260924/"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ApiBase = $ApiBase.TrimEnd("/")
$corpusRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..\data\size-file-corpus")).Path
$expected = @{
    104857600 = (Get-FileHash -LiteralPath (Join-Path $corpusRoot "100MB.bin") -Algorithm SHA256).Hash.ToLowerInvariant()
    1048576000 = (Get-FileHash -LiteralPath (Join-Path $corpusRoot "1GB.bin") -Algorithm SHA256).Hash.ToLowerInvariant()
}

$objects = [System.Collections.Generic.List[object]]::new()
$nextToken = $null
do {
    $url = "$ApiBase/api/objects?bucket=$([uri]::EscapeDataString($Bucket))&client_id=$([uri]::EscapeDataString($ClientId))&max_keys=1000"
    if ($nextToken) {
        $url += "&continuation_token=$([uri]::EscapeDataString($nextToken))"
    }
    $page = Invoke-RestMethod -Method Get -Uri $url -TimeoutSec 60
    foreach ($item in $page.objects) {
        if ($item.key.StartsWith("clients/$ClientId/") -and $item.key.Contains("/$FillPrefix")) {
            $objects.Add($item)
        }
    }
    $nextToken = $page.next_token
} while ($page.is_truncated)

if ($objects.Count -eq 0) {
    throw "No fill objects found for client $ClientId and prefix $FillPrefix."
}

$client = [System.Net.Http.HttpClient]::new()
$client.Timeout = [TimeSpan]::FromMinutes(30)
$checked = 0
$failed = 0
$checkedBytes = [long]0
try {
    foreach ($item in $objects) {
        $checked++
        $key = [string]$item.key
        $size = [long]$item.size
        Write-Host "[$checked/$($objects.Count)] Hashing $key ($size bytes)"
        $sizeKey = [int]$size
        if (-not $expected.ContainsKey($sizeKey)) {
            Write-Host "  FAIL: no original corpus file for this size"
            $failed++
            continue
        }

        $url = "$ApiBase/api/objects/content?bucket=$([uri]::EscapeDataString($Bucket))&key=$([uri]::EscapeDataString($key))"
        $response = $null
        $stream = $null
        $sha = $null
        try {
            $response = $client.GetAsync($url, [System.Net.Http.HttpCompletionOption]::ResponseHeadersRead).GetAwaiter().GetResult()
            $response.EnsureSuccessStatusCode() | Out-Null
            $stream = $response.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
            $sha = [System.Security.Cryptography.SHA256]::Create()
            $actual = [BitConverter]::ToString($sha.ComputeHash($stream)).Replace("-", "").ToLowerInvariant()
            $reportedSize = $response.Content.Headers.ContentLength
            $matches = ($actual -eq $expected[$sizeKey]) -and ($null -eq $reportedSize -or $reportedSize -eq $size)
            if (-not $matches) { $failed++ }
            $checkedBytes += $size
            Write-Host "  $(if ($matches) { 'MATCH' } else { 'FAIL' }) SHA256=$actual"
        } catch {
            $failed++
            Write-Host "  ERROR: $($_.Exception.Message)"
        } finally {
            if ($sha) { $sha.Dispose() }
            if ($stream) { $stream.Dispose() }
            if ($response) { $response.Dispose() }
        }
    }
} finally {
    $client.Dispose()
}

Write-Host "RESULT checked=$checked failed=$failed listed=$($objects.Count) logical_bytes=$checkedBytes"
if ($failed -gt 0) { throw "$failed object(s) failed verification." }
