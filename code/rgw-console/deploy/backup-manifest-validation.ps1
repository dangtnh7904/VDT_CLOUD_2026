# Pure validation only. No Docker, writes, credential reads or extraction.
function Assert-BackupManifest($Metadata) {
    if ($Metadata -isnot [System.Collections.IDictionary] -and $Metadata -isnot [pscustomobject]) { throw 'Backup metadata must be an object' }
    if (($Metadata.format_version -isnot [int] -and $Metadata.format_version -isnot [long]) -or $Metadata.format_version -ne 1 -or $Metadata.status -isnot [string] -or $Metadata.status -cne 'COMPLETE' -or ($Metadata.schema_version -isnot [int] -and $Metadata.schema_version -isnot [long]) -or $Metadata.schema_version -lt 1 -or $Metadata.schema_version -gt 9999) { throw 'Unsupported or incomplete backup metadata' }
    if (($Metadata.registry_rows -isnot [int] -and $Metadata.registry_rows -isnot [long]) -or $Metadata.registry_rows -lt 0) { throw 'Invalid evidence registry count' }
    foreach ($image in @($Metadata.application_image_id, $Metadata.postgres_image_id)) {
        if ($image -isnot [string] -or $image -cnotmatch '^sha256:[0-9a-f]{64}$') { throw 'Exact local application/PostgreSQL image ID required' }
    }
    if ($Metadata.artifacts -isnot [array] -or $Metadata.volumes -isnot [array]) { throw 'Artifact and volume records must be arrays' }
    $artifacts = @($Metadata.artifacts)
    if ($artifacts.Count -lt 3 -or $artifacts.Count -gt 32) { throw 'Invalid backup artifact count' }
    $names = @{}
    foreach ($artifact in $artifacts) {
        if ($artifact -isnot [System.Collections.IDictionary] -and $artifact -isnot [pscustomobject]) { throw 'Artifact record must be an object' }
        if ($artifact.name -isnot [string] -or $artifact.name -cnotmatch '^[a-z0-9][a-z0-9.-]+$' -or $names.ContainsKey($artifact.name)) { throw 'Unsafe or duplicate backup artifact name' }
        if ($artifact.sha256 -isnot [string] -or $artifact.sha256 -cnotmatch '^[0-9a-f]{64}$' -or ($artifact.size_bytes -isnot [int] -and $artifact.size_bytes -isnot [long]) -or $artifact.size_bytes -lt 0) { throw 'Invalid backup artifact hash or byte size' }
        $names[$artifact.name] = $true
    }
    $required = @('database.dump','evidence-registry.json','migrations.json')
    if ($Metadata.schema_version -ge 21) {
        $required += @('as-is-registry.jsonl','as-is-audit.jsonl')
        if ($Metadata.audit_checkpoint -isnot [string] -or $Metadata.audit_checkpoint -cne 'as-is-audit.jsonl') { throw 'Schema 21+ audit checkpoint required' }
    }
    $roles = @{}
    if (@($Metadata.volumes).Count -gt 2) { throw 'Invalid backup volume count' }
    foreach ($volume in @($Metadata.volumes)) {
        if ($volume -isnot [System.Collections.IDictionary] -and $volume -isnot [pscustomobject]) { throw 'Volume record must be an object' }
        if ($volume.role -isnot [string] -or $volume.role -cnotin @('evidence','executor-state') -or $roles.ContainsKey([string]$volume.role) -or $volume.status -isnot [string] -or $volume.status -cnotin @('BACKED_UP','NOT_PRESENT')) { throw 'Invalid or duplicate backup volume role/status' }
        $roles[[string]$volume.role] = $true
        if ($volume.status -eq 'BACKED_UP') {
            if ($volume.archive -isnot [string] -or $volume.inventory -isnot [string] -or $volume.archive -cne "$($volume.role).tar.gz" -or $volume.inventory -cne "$($volume.role).inventory.json") { throw 'Backup volume artifact names do not match role' }
            $required += @($volume.archive,$volume.inventory)
        }
    }
    foreach ($name in $required) {
        if (-not $names.ContainsKey($name)) { throw "Required hashed backup artifact missing: $name" }
    }
    if ($Metadata.registry_rows -gt 0 -and -not (@($Metadata.volumes) | Where-Object { $_.role -eq 'evidence' -and $_.status -eq 'BACKED_UP' })) { throw 'Evidence registry requires hashed evidence volume artifacts' }
}
