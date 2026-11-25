# Bloom flicker on a PAUSED race (the scene is frozen, so anything that changes is ours): launches
# the reference race (race_perf.ps1), and on the start line presses START (pause menu), grabs a fast
# burst of the window (grab_burst.py, ~8 grabs a second), then optionally asks for RSX frame
# captures (RSX_CAP_GATE) a few seconds apart: with the game paused two captures ARE comparable.
#   scripts\pause_burst.ps1 -Label base
#   scripts\pause_burst.ps1 -Label async0 -Env @{RSX_ASYNC='0'}
#   scripts\pause_burst.ps1 -Label cap -Caps 4          # + 4 RSX captures in <dir>\cap
# Results: E:\ms_perf\pause_<label>\ (b000.png ..., report.txt, paused.png, cap\). Window must stay visible.
param(
    [string]$Label = 'base',
    [hashtable]$Env = @{},
    [int]$Grabs = 120,
    [int]$Caps = 0,
    [int]$PauseDelay = 12,     # seconds after the race scene appears (the countdown must be over)
    [int]$DriveFirst = 6       # seconds of R2 before the pause: paused on the start line, before the
                               # bike has moved, the pause camera orbits it (the scene is not frozen)
)
$dir = "E:\ms_perf\pause_$Label"
New-Item -ItemType Directory -Force $dir | Out-Null
Remove-Item (Join-Path $dir 'b*.png') -ErrorAction SilentlyContinue
$gate = Join-Path $env:TEMP 'ms_capgate.txt'
Remove-Item $gate -ErrorAction SilentlyContinue
$e = @{} + $Env
if ($Caps -gt 0) {
    $capdir = Join-Path $dir 'cap'
    New-Item -ItemType Directory -Force $capdir | Out-Null
    $e['RSX_CAP_GATE'] = $gate; $e['RSX_CAP_DIR'] = $capdir
}
$marks = Join-Path $PSScriptRoot '..\port\race_perf_marks.txt'
$grab = Join-Path $PSScriptRoot 'grab_burst.py'
$shot = Join-Path $PSScriptRoot 'screenshot.ps1'
$pad = Join-Path $env:TEMP 'motorstorm_pad.txt'
$job = Start-Job -ArgumentList $marks, $grab, $dir, $Grabs, $PauseDelay, $pad, $Caps, $gate, $shot, $DriveFirst -ScriptBlock {
    param($marks, $grab, $dir, $grabs, $delay, $pad, $caps, $gate, $shot, $drive)
    Start-Sleep 60   # the marks file is reset when race_perf starts
    for ($i = 0; $i -lt 600; $i++) {
        if ((Test-Path $marks) -and (Select-String -Path $marks -Pattern 'idle begin' -Quiet)) { break }
        Start-Sleep 1
    }
    Start-Sleep $delay
    if ($drive -gt 0) {
        for ($try = 0; $try -lt 50; $try++) {
            try { Set-Content -Path $pad -Value ('0x0200 {0}' -f ($drive * 30)) -NoNewline -ErrorAction Stop; break } catch { Start-Sleep -Milliseconds 20 }
        }
        Start-Sleep ($drive + 1)
    }
    for ($try = 0; $try -lt 50; $try++) {
        try { Set-Content -Path $pad -Value '0x0008 5' -NoNewline -ErrorAction Stop; break } catch { Start-Sleep -Milliseconds 20 }
    }
    Start-Sleep 4
    & $shot -Out (Join-Path $dir 'paused.png') | Out-Null
    python $grab $dir --n $grabs 2>&1 | Set-Content (Join-Path $dir 'report.txt')
    for ($c = 0; $c -lt $caps; $c++) {
        Set-Content -Path $gate -Value '1' -NoNewline
        Start-Sleep 5
        & $shot -Out (Join-Path $dir ("aftercap{0}.png" -f $c)) | Out-Null
    }
}
$idle = $PauseDelay + $DriveFirst + 5 + [int]($Grabs / 6) + $Caps * 6 + 20
& (Join-Path $PSScriptRoot 'race_perf.ps1') -Label "pause $Label [controle, FPS faux]" -Env $e -IdleSeconds $idle -DriveSeconds 3 2>&1 | Select-Object -Last 3
Receive-Job $job -Wait -ErrorAction SilentlyContinue | Out-Null
Write-Host "[pause_burst] $Label -> $dir"
Get-Content (Join-Path $dir 'report.txt') -ErrorAction SilentlyContinue | Write-Host
