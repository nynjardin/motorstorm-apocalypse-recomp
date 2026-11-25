# Flicker of the start line of the reference race, from TRUE consecutive frames: launches the race
# (race_perf.ps1), and once on the start line grabs a fast burst of the window (grab_burst.py, ~9
# grabs a second) -- the report gives, per screen cell, the mean change and the mean second
# difference ("blink, not drift") between consecutive frames. Compare labels/env to bisect.
#   scripts\burst_series.ps1 -Label base
#   scripts\burst_series.ps1 -Label async0 -Env @{RSX_ASYNC='0'}
# Results: E:\ms_perf\burst_<label>\ (b000.png ... + report.txt). The window must stay visible.
param(
    [string]$Label = 'base',
    [hashtable]$Env = @{},
    [int]$Grabs = 120,
    [ValidateSet('idle','drive')][string]$Phase = 'idle'   # drive: burst while driving (beam mask lag...)
)
$dir = "E:\ms_perf\burst_$Label"
New-Item -ItemType Directory -Force $dir | Out-Null
Remove-Item (Join-Path $dir 'b*.png') -ErrorAction SilentlyContinue
$marks = Join-Path $PSScriptRoot '..\port\race_perf_marks.txt'
$grab = Join-Path $PSScriptRoot 'grab_burst.py'
$job = Start-Job -ArgumentList $marks, $grab, $dir, $Grabs, $Phase -ScriptBlock {
    param($marks, $grab, $dir, $grabs, $phase)
    Start-Sleep 60   # the marks file is reset when race_perf starts
    for ($i = 0; $i -lt 600; $i++) {
        if ((Test-Path $marks) -and (Select-String -Path $marks -Pattern "$phase begin" -Quiet)) { break }
        Start-Sleep 1
    }
    Start-Sleep 5
    python $grab $dir --n $grabs 2>&1 | Set-Content (Join-Path $dir 'report.txt')
}
& (Join-Path $PSScriptRoot 'race_perf.ps1') -Label "burst $Label [controle, FPS faux]" -Env $Env -IdleSeconds $(if ($Phase -eq 'drive') { 10 } else { 40 }) -DriveSeconds $(if ($Phase -eq 'drive') { 40 } else { 5 }) 2>&1 | Select-Object -Last 3
Receive-Job $job -Wait -ErrorAction SilentlyContinue | Out-Null
Write-Host "[burst] $Label"
Get-Content (Join-Path $dir 'report.txt') | Write-Host
