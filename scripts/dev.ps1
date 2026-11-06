<#
.SYNOPSIS
    Task runner for the Bank Statement Analyzer (Windows replacement for a Makefile).

.EXAMPLE
    .\scripts\dev.ps1 setup      # backend\.venv + frontend\node_modules (both local)
    .\scripts\dev.ps1 test       # pytest, then Vitest (extra args go to pytest only)
    .\scripts\dev.ps1 lint       # ruff + mypy
    .\scripts\dev.ps1 migrate    # alembic upgrade head
    .\scripts\dev.ps1 run        # API (and built frontend, if any) on http://127.0.0.1:8000
    .\scripts\dev.ps1 web        # Vite dev server on http://127.0.0.1:5173 (proxies /api)
    .\scripts\dev.ps1 build      # build the frontend into frontend\dist
    .\scripts\dev.ps1 samples    # regenerate synthetic statements
    .\scripts\dev.ps1 demo       # build demo.db from synthetic data and serve it
#>
param(
    [Parameter(Position = 0)]
    [ValidateSet('setup', 'test', 'lint', 'format', 'migrate', 'run', 'samples', 'demo', 'web', 'build', 'help')]
    [string]$Task = 'help',

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root 'backend'
$Venv = Join-Path $Backend '.venv'
$Py = Join-Path $Venv 'Scripts\python.exe'
$Frontend = Join-Path $Root 'frontend'

# Keep caches off the C: drive. Process-scoped only; nothing global is changed.
if (-not $env:PIP_CACHE_DIR) { $env:PIP_CACHE_DIR = 'D:\dev-cache\pip' }

function Get-BasePython {
    if ($env:PYTHON) { return $env:PYTHON }
    if (Get-Command py -ErrorAction SilentlyContinue) { return 'py -3' }
    return 'python'
}

function Assert-Venv {
    if (-not (Test-Path $Py)) { throw "No virtualenv found. Run: .\scripts\dev.ps1 setup" }
}

switch ($Task) {
    'setup' {
        $base = Get-BasePython
        Write-Host "Creating venv with: $base"
        Invoke-Expression "$base -m venv `"$Venv`""
        & $Py -m pip install --upgrade pip
        & $Py -m pip install -e "$Backend[dev]"
        if (Get-Command npm -ErrorAction SilentlyContinue) {
            # npm cache location comes from frontend\.npmrc (D:\dev-cache\npm)
            Push-Location $Frontend
            try { npm install } finally { Pop-Location }
        } else { Write-Warning "npm not found: skipping frontend install" }
    }
    'test' {
        Assert-Venv
        Push-Location $Backend
        try {
            & $Py -m pytest @Rest
            if ($LASTEXITCODE -ne 0 -or $Rest) { exit $LASTEXITCODE }
        } finally { Pop-Location }
        Push-Location $Frontend
        try { npm test; exit $LASTEXITCODE } finally { Pop-Location }
    }
    'lint' {
        Assert-Venv
        Push-Location $Backend
        try {
            & $Py -m ruff check app tests ..\samples
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
            & $Py -m mypy app
            exit $LASTEXITCODE
        } finally { Pop-Location }
    }
    'format' {
        Assert-Venv
        Push-Location $Backend
        try { & $Py -m ruff format app tests ..\samples; & $Py -m ruff check --fix app tests ..\samples } finally { Pop-Location }
    }
    'migrate' {
        Assert-Venv
        Push-Location $Backend
        try { & $Py -m alembic upgrade head; exit $LASTEXITCODE } finally { Pop-Location }
    }
    'run' {
        Assert-Venv
        Push-Location $Backend
        try { & $Py -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 } finally { Pop-Location }
    }
    'samples' {
        Assert-Venv
        & $Py (Join-Path $Root 'samples\generate.py') @Rest
        exit $LASTEXITCODE
    }
    'demo' {
        # Synthetic data only, separate demo.db, offline fake LLM. Never touches ledger.db.
        Assert-Venv
        Push-Location $Backend
        try {
            & $Py -m app.demo --reset
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
            $env:DATABASE_URL = 'sqlite:///' + ((Join-Path $Backend 'demo.db') -replace '\\', '/')
            $env:DEMO_MODE = 'true'
            & $Py -m uvicorn app.main:app --host 127.0.0.1 --port 8000
        } finally { Pop-Location }
    }
    'web' {
        Push-Location $Frontend
        try { npm run dev } finally { Pop-Location }
    }
    'build' {
        Push-Location $Frontend
        try { npm run build; exit $LASTEXITCODE } finally { Pop-Location }
    }
    default {
        Get-Help $MyInvocation.MyCommand.Path -Detailed
    }
}
