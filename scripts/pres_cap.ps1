# RSX frame captures DURING THE RACE PRESENTATION (the camera tour before "DEPART"): launches
# race_perf.ps1 with RSX_CAP_GATE and asks for <Caps> captures, the first <After> seconds into the
# presentation, 2 s apart (race_perf presses X 10 s into it). Same idea as drive_cap.ps1; for the
# defects only seen in the presentation views (the fuchsia dots on the tunnel portal of the bridge).
#   scripts\pres_cap.ps1 -Label base [-Track quai] [-Env @{..}] [-After 3] [-Caps 3]
# Results: E:\ms_perf\prescap_<label>\frame_50, frame_51, ... (manifest.txt, fps.hlsl, rt_*.bmp, ds_*.bmp)
# and one screenshot per capture (shot_<n>.png, taken right after the capture was asked for).
param(
    [string]$Label = 'base',
    [hashtable]$Env = @{},
    [int]$Caps = 3,
    [int]$After = 3,
    [string]$Track = 'pont'
)
$dir = "E:\ms_perf\prescap_$Label"
New-Item -ItemType Directory -Force $dir | Out-Null
$gate = Join-Path $env:TEMP 'ms_capgate.txt'
Remove-Item $gate -ErrorAction SilentlyContinue
$e = @{} + $Env
$e['RSX_CAP_GATE'] = $gate; $e['RSX_CAP_DIR'] = $dir
$marks = Join-Path $PSScriptRoot '..\port\race_perf_marks.txt'
$shot = Join-Path $PSScriptRoot 'screenshot.ps1'
$job = Start-Job -ArgumentList $marks, $gate, $Caps, $After, $shot, $dir -ScriptBlock {
    param($marks, $gate, $caps, $after, $shot, $dir)
    Start-Sleep 60   # the marks file is reset when race_perf starts
    for ($i = 0; $i -lt 600; $i++) {
        if ((Test-Path $marks) -and (Select-String -Path $marks -Pattern 'presentation begin' -Quiet)) { break }
        Start-Sleep 1
    }
    Start-Sleep $after
    for ($c = 0; $c -lt $caps; $c++) {
        Set-Content -Path $gate -Value '1' -NoNewline
        & $shot -Out (Join-Path $dir "shot_$c.png") | Out-Null
        Start-Sleep 2
    }
}
& (Join-Path $PSScriptRoot 'race_perf.ps1') -Label "prescap $Label [controle, FPS faux]" -Env $e -Track $Track -IdleSeconds 2 -DriveSeconds 2 2>&1 | Select-Object -Last 3
Receive-Job $job -Wait -ErrorAction SilentlyContinue | Out-Null
Write-Host "[pres_cap] $Label -> $dir"
Get-ChildItem $dir -Directory | ForEach-Object { "{0}: {1} files" -f $_.Name, (Get-ChildItem $_.FullName).Count } | Write-Host
