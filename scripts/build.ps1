# Build a single-file portable .exe of telegram-collector with PyInstaller (Windows).
#
# cryptg is a compiled C extension, so the .exe is platform-locked:
# build it ON Windows to RUN on Windows.
#
# Usage (PowerShell):
#   pwsh scripts/build.ps1
#   # or from cmd:  powershell -ExecutionPolicy Bypass -File scripts\build.ps1
#
# Prereq: pyinstaller installed (pip install pyinstaller) and Python 3.11+ on PATH.

param(
    [string]$Name = "telegram-collector",
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path (Join-Path $PSScriptRoot ".."))

# Probe via exit code, not boolean of the call: with $ErrorActionPreference="Stop",
# native stderr (a traceback when PyInstaller is absent) raises a terminating
# NativeCommandError before 2>$null can suppress it.
$ErrorActionPreference = "Continue"
& $Python -c "import PyInstaller" 2>&1 | Out-Null
$hasPyInstaller = $LASTEXITCODE -eq 0
$ErrorActionPreference = "Stop"
if (-not $hasPyInstaller) {
    Write-Host "PyInstaller not found. Installing into current env..."
    & $Python -m pip install --upgrade pyinstaller
}

Write-Host "Cleaning previous build artifacts..."
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue

Write-Host "Building $Name (this takes a minute)..."
& $Python -m PyInstaller `
    --onefile `
    --console `
    --name $Name `
    --collect-all telethon `
    --collect-all cryptg `
    --copy-metadata telegram_collector `
    --hidden-import "telethon.tl.types" `
    main.py

if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller build failed (exit code $LASTEXITCODE). See log above."
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "Done. Binary: dist\$Name.exe"
Write-Host "Verify:      .\dist\$Name.exe --version"
Write-Host ""
Write-Host "Portable USB bundle = copy these together:"
Write-Host "  dist\$Name.exe      # the binary"
Write-Host "  .env                # your API_ID / API_HASH"
Write-Host "  *.session           # saved login (AUTH KEY - keep private / encrypt the USB)"
