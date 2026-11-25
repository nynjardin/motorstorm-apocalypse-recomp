# Brightness over time of a screen region during the idle phase of the reference race (start line):
# one screenshot a second, mean luma of the region for each. Made for the sun halo (top-left of the
# bridge race) -- a still scene whose region brightness jumps from shot to shot is flickering.
#   scripts\halo_series.ps1 -Label dbt1 [-Env @{DEPTH_BOUNDS='0'}] [-Region 10,40,300,170] [-Shots 35]
param(
    [string]$Label = 'halo',
    [hashtable]$Env = @{},
    [int[]]$Region = @(10, 40, 300, 170),   # x, y, w, h in window pixels
    [int]$Shots = 35
)
$dir = "E:\ms_perf\halo_$Label"
New-Item -ItemType Directory -Force $dir | Out-Null
$marks = Join-Path $PSScriptRoot '..\port\race_perf_marks.txt'
$shot = Join-Path $PSScriptRoot 'screenshot.ps1'
$job = Start-Job -ArgumentList $marks, $shot, $dir, $Shots -ScriptBlock {
    param($marks, $shot, $dir, $shots)
    Start-Sleep 60   # the marks file is reset when race_perf starts
    for ($i = 0; $i -lt 600; $i++) {
        if ((Test-Path $marks) -and (Select-String -Path $marks -Pattern 'idle begin' -Quiet)) { break }
        Start-Sleep 1
    }
    Start-Sleep 3
    for ($k = 0; $k -lt $shots; $k++) {
        & $shot -Out (Join-Path $dir ("s{0:D2}.png" -f $k)) | Out-Null
        Start-Sleep -Milliseconds 700
    }
}
& (Join-Path $PSScriptRoot 'race_perf.ps1') -Label "halo $Label" -Env $Env -IdleSeconds ($Shots + 12) -DriveSeconds 5 2>&1 | Select-Object -Last 5
Receive-Job $job -Wait -ErrorAction SilentlyContinue | Out-Null
Add-Type -AssemblyName System.Drawing
$vals = @()
foreach ($f in Get-ChildItem $dir -Filter 's*.png' | Sort-Object Name) {
    $b = New-Object System.Drawing.Bitmap $f.FullName
    $sum = 0.0; $n = 0
    for ($y = $Region[1]; $y -lt $Region[1] + $Region[3] -and $y -lt $b.Height; $y += 3) {
        for ($x = $Region[0]; $x -lt $Region[0] + $Region[2] -and $x -lt $b.Width; $x += 3) {
            $c = $b.GetPixel($x, $y); $sum += 0.299 * $c.R + 0.587 * $c.G + 0.114 * $c.B; $n++
        }
    }
    $b.Dispose()
    $vals += [math]::Round($sum / [math]::Max($n, 1), 1)
}
$d = @(); for ($i = 1; $i -lt $vals.Count; $i++) { $d += [math]::Abs($vals[$i] - $vals[$i - 1]) }
$mean = if ($vals.Count) { ($vals | Measure-Object -Average).Average } else { 0 }
$md = if ($d.Count) { ($d | Measure-Object -Average).Average } else { 0 }
$mx = if ($d.Count) { ($d | Measure-Object -Maximum).Maximum } else { 0 }
Write-Host ("[halo] {0}: region luma " -f $Label) ($vals -join ' ')
Write-Host ("[halo] {0}: mean {1:N1}, min {2}, max {3}, mean |step| {4:N2}, max |step| {5:N1}" -f $Label, $mean,
    ($vals | Measure-Object -Minimum).Minimum, ($vals | Measure-Object -Maximum).Maximum, $md, $mx)
