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

if (-not (& $Python -c "import PyInstaller" 2>$null)) {
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

Write-Host ""
Write-Host "Done. Binary: dist\$Name.exe"
Write-Host "Verify:      .\dist\$Name.exe --version"
Write-Host ""
Write-Host "Portable USB bundle = copy these together:"
Write-Host "  dist\$Name.exe      # the binary"
Write-Host "  .env                # your API_ID / API_HASH"
Write-Host "  *.session           # saved login (AUTH KEY - keep private / encrypt the USB)"
