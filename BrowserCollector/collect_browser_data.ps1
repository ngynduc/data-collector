# ============================================================
#  Browser Data Collector - PowerShell (Windows)
#  Collects: History, Bookmarks, Cookies, Passwords,
#            Extensions, Cache, Preferences
#  Browsers: Chrome, Edge, Firefox, Brave, Opera, Vivaldi
# ============================================================

param (
    [string]$OutputDir = "D:\CollectedData\BrowserData_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
)

# Global log for CSV export
$global:CollectionLog = [System.Collections.Generic.List[PSCustomObject]]::new()

function Get-SHA256 ($filePath) {
    try {
        $hash = Get-FileHash -Path $filePath -Algorithm SHA256 -ErrorAction Stop
        return $hash.Hash
    } catch {
        return "ERROR"
    }
}

function Add-Log ($srcPath, $destPath, $status) {
    $entry = [PSCustomObject]@{
        SourcePath   = $srcPath
        DestPath     = $destPath
        LastModified = ""
        SizeKB       = ""
        SHA256       = ""
        Status       = $status
    }
    if ($status -eq "OK" -and (Test-Path $destPath)) {
        $fi = Get-Item $destPath -ErrorAction SilentlyContinue
        if ($fi -and -not $fi.PSIsContainer) {
            $entry.LastModified = $fi.LastWriteTime.ToString("yyyy-MM-dd HH:mm:ss")
            $entry.SizeKB       = [math]::Round($fi.Length / 1KB, 2)
            $entry.SHA256       = Get-SHA256 $destPath
        }
    }
    $global:CollectionLog.Add($entry)
}

function Write-Banner {
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Cyan
    Write-Host "   Browser Data Collector (PowerShell)     " -ForegroundColor Cyan
    Write-Host "============================================" -ForegroundColor Cyan
    Write-Host " Output : $OutputDir" -ForegroundColor Yellow
    Write-Host " Time   : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Yellow
    Write-Host "============================================" -ForegroundColor Cyan
    Write-Host ""
}

function Write-Step ($msg) { Write-Host "[*] $msg" -ForegroundColor Green }
function Write-Warn ($msg) { Write-Host "[!] $msg" -ForegroundColor Yellow }
function Write-Fail ($msg) { Write-Host "[-] $msg" -ForegroundColor Red }

function Safe-Copy ($src, $destDir, $label) {
    if (Test-Path $src) {
        New-Item -ItemType Directory -Path $destDir -Force | Out-Null
        $destFile = Join-Path $destDir (Split-Path $src -Leaf)
        try {
            Copy-Item -Path $src -Destination $destDir -Force -ErrorAction Stop
            Write-Step "Copied $label"
            Add-Log $src $destFile "OK"
        } catch {
            Write-Warn "Skipped (locked): $label"
            Add-Log $src $destFile "LOCKED"
        }
    } else {
        Write-Warn "Not found: $label"
        Add-Log $src "" "NOT_FOUND"
    }
}

# For DIRECTORIES: robocopy with /R:0 /W:0 so it never blocks on locked files
function Safe-CopyDir ($src, $destDir, $label) {
    if (Test-Path $src) {
        $leaf = Split-Path $src -Leaf
        $dest = Join-Path $destDir $leaf
        New-Item -ItemType Directory -Path $dest -Force | Out-Null
        robocopy "$src" "$dest" /E /R:0 /W:0 /NJH /NJS /NFL /NDL 2>$null | Out-Null
        if ($LASTEXITCODE -le 7) {
            Write-Step "Copied $label"
            # Log each file individually inside the copied directory
            Get-ChildItem -Path $dest -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object {
                $rel     = $_.FullName.Substring($dest.Length)
                $srcFile = $src + $rel
                Add-Log $srcFile $_.FullName "OK"
            }
        } else {
            Write-Fail "Failed to copy $label (exit $LASTEXITCODE)"
            Add-Log $src "" "FAILED"
        }
    } else {
        Write-Warn "Not found: $label"
        Add-Log $src "" "NOT_FOUND"
    }
}

function Collect-ChromiumBrowser ($name, $profileRoot) {
    Write-Host ""
    Write-Host "--- $name ---" -ForegroundColor Magenta

    if (-not (Test-Path $profileRoot)) {
        Write-Warn "$name not found. Skipping."
        return
    }

    $profiles = Get-ChildItem -Path $profileRoot -Directory |
                Where-Object { $_.Name -match "^(Default|Profile \d+)$" }

    foreach ($profile in $profiles) {
        $pName    = $profile.Name
        $pPath    = $profile.FullName
        $destBase = Join-Path $OutputDir "$name\$pName"

        Write-Step "Profile: $pName"

        # Note: Cookies moved to Network\Cookies in Chromium v96+
        # The full Network\ dir is copied below, which includes Cookies
        $files = @("History","Bookmarks","Login Data","Preferences",
                   "Secure Preferences","Web Data")
        $dirs  = @("Extensions","Cache","Local Storage","Session Storage","Network")

        foreach ($f in $files) { Safe-Copy    "$pPath\$f" $destBase $f }
        foreach ($d in $dirs)  { Safe-CopyDir "$pPath\$d" $destBase $d }
    }

    Safe-Copy "$profileRoot\Local State" (Join-Path $OutputDir $name) "Local State"
}

function Collect-Firefox {
    Write-Host ""
    Write-Host "--- Firefox ---" -ForegroundColor Magenta

    $ffRoot = Join-Path $env:APPDATA "Mozilla\Firefox\Profiles"
    if (-not (Test-Path $ffRoot)) {
        Write-Warn "Firefox not found. Skipping."
        return
    }

    $profiles = Get-ChildItem -Path $ffRoot -Directory
    foreach ($profile in $profiles) {
        $pPath    = $profile.FullName
        $destBase = Join-Path $OutputDir "Firefox\$($profile.Name)"

        Write-Step "Profile: $($profile.Name)"

        $files = @("places.sqlite","cookies.sqlite","logins.json","key4.db",
                   "cert9.db","prefs.js","extensions.json","formhistory.sqlite")
        $dirs  = @("extensions","storage","sessionstore-backups")

        foreach ($f in $files) { Safe-Copy    "$pPath\$f" $destBase $f }
        foreach ($d in $dirs)  { Safe-CopyDir "$pPath\$d" $destBase $d }
    }
}

function Write-SystemInfo {
    $destFile  = Join-Path $OutputDir "system_info.txt"
    $osCaption = (Get-WmiObject Win32_OperatingSystem).Caption

    $lines = @(
        "=== System Information ===",
        "Collection Time : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')",
        "Hostname        : $env:COMPUTERNAME",
        "Username        : $env:USERNAME",
        "OS              : $osCaption",
        "Architecture    : $env:PROCESSOR_ARCHITECTURE",
        "Domain          : $env:USERDOMAIN",
        "",
        "=== Installed Browsers (Registry) ==="
    )
    $lines | Out-File $destFile -Encoding UTF8

    $regBase  = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"
    $browsers = @("chrome.exe","msedge.exe","firefox.exe","brave.exe")
    foreach ($b in $browsers) {
        $key = "$regBase\$b"
        if (Test-Path $key) {
            $val = (Get-ItemProperty $key).'(default)'
            "$b => $val" | Add-Content $destFile
        }
    }

    Write-Step "System info saved."
}

function Export-CollectionCSV {
    $csvPath = Join-Path $OutputDir "collection_report.csv"
    Write-Host ""
    Write-Step "Generating SHA256 and CSV report..."

    # For OK file entries that don't have SHA256 yet (files logged without hash)
    # Re-compute if missing (Safe-CopyDir already fills in via Add-Log)
    $global:CollectionLog | Export-Csv -Path $csvPath -NoTypeInformation -Encoding UTF8
    Write-Step "Report saved: collection_report.csv ($($global:CollectionLog.Count) entries)"
}

# ── Main ──────────────────────────────────────────────────────
Write-Banner
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

Collect-ChromiumBrowser "Chrome"  "$env:LOCALAPPDATA\Google\Chrome\User Data"
Collect-ChromiumBrowser "Edge"    "$env:LOCALAPPDATA\Microsoft\Edge\User Data"
Collect-ChromiumBrowser "Brave"   "$env:LOCALAPPDATA\BraveSoftware\Brave-Browser\User Data"
Collect-ChromiumBrowser "Opera"   "$env:APPDATA\Opera Software\Opera Stable"
Collect-ChromiumBrowser "Vivaldi" "$env:LOCALAPPDATA\Vivaldi\User Data"
Collect-Firefox
Write-SystemInfo
Export-CollectionCSV

# ── Summary ───────────────────────────────────────────────────
Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host " Collection Complete!" -ForegroundColor Green
Write-Host " Saved to: $OutputDir" -ForegroundColor Yellow
$totalBytes = (Get-ChildItem $OutputDir -Recurse -File |
               Measure-Object -Property Length -Sum).Sum
$size = "{0:N2} MB" -f ($totalBytes / 1MB)
Write-Host " Total size: $size" -ForegroundColor Yellow
Write-Host "============================================" -ForegroundColor Cyan
