[CmdletBinding()]
param(
    [string]$ApiBase = "http://127.0.0.1:8000",
    [string]$Pool = "default.rgw.lab.data",
    [string]$Bucket = "rgw-lab-data",
    [string]$Prefix = "capacity-fill/20260924",
    [double]$CoarseStopRatio = 0.55,
    [double]$TargetStopRatio = 0.595,
    [int]$PollSeconds = 5,
    [switch]$Execute
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($ApiBase -match "\[|\]|\(|\)" -or $Pool.Contains("\")) {
    throw "ApiBase/Pool contains Markdown or escape characters. Use plain values such as http://127.0.0.1:8000 and default.rgw.lab.data."
}

$ApiBase = $ApiBase.TrimEnd("/")
$encodedPool = [uri]::EscapeDataString($Pool)
$capacityUri = "$ApiBase/api/capacity?scope_type=pool&scope=$encodedPool"

function Get-Capacity {
    Invoke-RestMethod -Method Get -Uri $capacityUri -TimeoutSec 30
}

function Assert-CapacitySafe {
    param([object]$Capacity)

    if (-not $Capacity.fresh) {
        throw "Capacity telemetry is stale; stopping."
    }
    if ($Capacity.state -ne "NORMAL") {
        throw "Capacity state is $($Capacity.state), not NORMAL; stopping."
    }
    if ([double]$Capacity.most_full_ratio -ge 0.60) {
        throw "Most-full OSD is already at or above 60%; stopping."
    }
}

function Upload-Exact {
    param([long]$Bytes)

    $idempotencyKey = "fill60-" + [guid]::NewGuid().ToString("N")
    $body = @{
        corpus_ids = @("size")
        client_id = "fill60"
        bucket = $Bucket
        prefix = $Prefix
        category = "binary"
        extension = "bin"
        min_bytes = $Bytes
        max_bytes = $Bytes
    } | ConvertTo-Json

    Write-Host ("Uploading {0:N0} bytes; request may remain quiet until the upload completes..." -f $Bytes)
    $result = Invoke-RestMethod `
        -Method Post `
        -Uri "$ApiBase/api/uploads/random" `
        -Headers @{ "Idempotency-Key" = $idempotencyKey } `
        -ContentType "application/json" `
        -Body $body `
        -TimeoutSec 1800

    Write-Host ("Upload completed: {0}" -f $result.key)
}

$initial = Get-Capacity
Write-Host ("Current most-full ratio: {0:P2}; state: {1}; contract: {2}" -f `
    [double]$initial.most_full_ratio, $initial.state, $initial.contract)

if (-not $Execute) {
    Write-Host "Preflight only. No data was uploaded."
    Write-Host "After Ceph health checks pass, rerun this script with -Execute."
    exit 0
}

Assert-CapacitySafe $initial

while ($true) {
    $capacity = Get-Capacity
    Assert-CapacitySafe $capacity
    Write-Host ("Most-full ratio: {0:P2}; state: {1}" -f `
        [double]$capacity.most_full_ratio, $capacity.state)

    if ([double]$capacity.most_full_ratio -ge $CoarseStopRatio) {
        break
    }

    Upload-Exact -Bytes 1048576000
    Start-Sleep -Seconds $PollSeconds
}

while ($true) {
    $capacity = Get-Capacity
    Assert-CapacitySafe $capacity
    Write-Host ("Most-full ratio: {0:P2}; state: {1}" -f `
        [double]$capacity.most_full_ratio, $capacity.state)

    if ([double]$capacity.most_full_ratio -ge $TargetStopRatio) {
        break
    }

    Upload-Exact -Bytes 104857600
    Start-Sleep -Seconds $PollSeconds
}

$final = Get-Capacity
Write-Host ("Finished. Most-full ratio: {0:P2}; state: {1}; prefix: {2}" -f `
    [double]$final.most_full_ratio, $final.state, $Prefix)
