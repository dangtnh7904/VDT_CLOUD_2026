param(
    [string]$Python = ".\\backend\\.venv\\Scripts\\python.exe"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $root $Python

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Backend virtualenv was not found at $pythonPath. Create it and install backend/requirements-dev.txt first."
}

Push-Location $root
try {
    Push-Location backend
    try {
        & $pythonPath -m unittest discover -s tests -v
        if ($LASTEXITCODE -ne 0) { throw "Backend tests failed" }
    }
    finally {
        Pop-Location
    }

    Push-Location frontend
    try {
        npm test
        if ($LASTEXITCODE -ne 0) { throw "Frontend tests failed" }
        npm run build
        if ($LASTEXITCODE -ne 0) { throw "Frontend build failed" }
    }
    finally {
        Pop-Location
    }

    Push-Location rbd-console
    try {
        npm test
        if ($LASTEXITCODE -ne 0) { throw "Executor tests failed" }
    }
    finally {
        Pop-Location
    }
}
finally {
    Pop-Location
}
