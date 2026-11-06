<#
.SYNOPSIS
    Task runner for the Bank Statement Analyzer (Windows replacement for a Makefile).

.EXAMPLE
    .\scripts\dev.ps1 setup      # create backend\.venv and install deps
    .\scripts\dev.ps1 test       # run pytest
    .\scripts\dev.ps1 lint       # ruff + mypy
    .\scripts\dev.ps1 migrate    # alembic upgrade head
    .\scripts\dev.ps1 run        # start the API on http://127.0.0.1:8000
    .\scripts\dev.ps1 samples    # regenerate synthetic statements
#>
param(
    [Parameter(Position = 0)]
    [ValidateSet('setup', 'test', 'lint', 'format', 'migrate', 'run', 'samples', 'help')]
    [string]$Task = 'help',

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root 'backend'
$Venv = Join-Path $Backend '.venv'
$Py = Join-Path $Venv 'Scripts\python.exe'

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
    }
    'test' {
        Assert-Venv
        Push-Location $Backend
        try { & $Py -m pytest @Rest; exit $LASTEXITCODE } finally { Pop-Location }
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
    default {
        Get-Help $MyInvocation.MyCommand.Path -Detailed
    }
}
