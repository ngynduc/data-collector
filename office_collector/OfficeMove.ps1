# === Cau hinh ===
$SearchPaths = @("C:\")                          # Cac duong dan can quet
$DestFolder  = "D:\New folder"         # Noi gom file
$Extensions  = @("*.doc","*.docx","*.xls","*.xlsx","*.ppt","*.pptx","*.docm","*.xlsm","*.pptm")
$Mode        = "Copy"                            # "Copy" hoac "Move"
$LogFile     = Join-Path $DestFolder "collection_log.csv"

# === Tao thu muc dich ===
New-Item -ItemType Directory -Path $DestFolder -Force | Out-Null

# === Tim file ===
$found = foreach ($path in $SearchPaths) {
    Get-ChildItem -Path $path -Include $Extensions -Recurse -File -ErrorAction SilentlyContinue
}

Write-Host "Tim thay $($found.Count) file." -ForegroundColor Cyan

# === Gom file + xu ly trung ten + ghi log ===
$log = foreach ($file in $found) {
    $target = Join-Path $DestFolder $file.Name

    # Xu ly trung ten: them so thu tu
    if (Test-Path $target) {
        $base = [IO.Path]::GetFileNameWithoutExtension($file.Name)
        $ext  = $file.Extension
        $i = 1
        do {
            $target = Join-Path $DestFolder "$base`_$i$ext"
            $i++
        } while (Test-Path $target)
    }

    try {
        if ($Mode -eq "Move") {
            Move-Item -LiteralPath $file.FullName -Destination $target -Force
        } else {
            Copy-Item -LiteralPath $file.FullName -Destination $target -Force
        }
        $hash = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
        [PSCustomObject]@{
            OriginalPath = $file.FullName
            NewPath      = $target
            SizeKB       = [math]::Round($file.Length/1KB,2)
            LastWrite    = $file.LastWriteTime
            SHA256       = $hash
            Status       = "OK"
        }
    } catch {
        [PSCustomObject]@{
            OriginalPath = $file.FullName
            NewPath      = $target
            SizeKB       = [math]::Round($file.Length/1KB,2)
            LastWrite    = $file.LastWriteTime
            SHA256       = ""
            Status       = "ERROR: $($_.Exception.Message)"
        }
    }
}

$log | Export-Csv -Path $LogFile -NoTypeInformation -Encoding UTF8
Write-Host "Xong. Log luu tai: $LogFile" -ForegroundColor Green