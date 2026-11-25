# Instrumented session PLAYED BY THE USER (a defect or slowness that scripted driving does not
# reproduce). Launches port\run.bat with diagnostics on and, until the game exits, records in
# E:\ms_perf\play_<label>_<time>\ :
#   title.csv    one line a second: seconds since launch, FPS, draws (window title)
#   shots\*.png  a screenshot every -ShotEvery seconds, named by the same seconds (popping, LOD)
#   threads.txt  CPU per host thread every -CpuEvery seconds (2 s window, scripts\thread_cpu.ps1)
#   run.log      copy of port\run.log at the end ([HITCH] = each frame over 45 ms split into
#                render / fifo / shaders / fs, [FRAME_LOG] = draws, vertices, scene size per race
#                frame (first 4000), [geo] = geometry cache)
# Marks: the user writes nothing; phases are found afterwards from draws in title.csv.
# ONE command at a time: it returns when the game is closed (a pasted series runs the next one then).
#   scripts\play_watch.ps1 -Label quai
#   scripts\play_watch.ps1 -Label quai_nogeo -Env @{GEO_CACHE='0'}
#   scripts\play_watch.ps1 -Label x -Attach       # game already running (goto_race.ps1): only record
param(
    [string]$Label = 'play',
    [hashtable]$Env = @{},
    [int]$ShotEvery = 3,
    [int]$CpuEvery = 30,
    [int]$MaxSeconds = 3600,
    [switch]$Attach
)
$ErrorActionPreference = 'Stop'
$port = Join-Path $PSScriptRoot '..\port'
$log = Join-Path $port 'run.log'

if (-not $Attach) {
    # A game that is closing (the previous play_watch of a pasted series) gets 30 s to go away.
    for ($w = 0; $w -lt 30 -and (Get-Process MotorStormApocalypse -ErrorAction SilentlyContinue); $w++) { Start-Sleep 1 }
    if (Get-Process MotorStormApocalypse -ErrorAction SilentlyContinue) { throw 'the game is already running: close it first (or -Attach to record it as it is)' }
}
$dir = 'E:\ms_perf\play_{0}_{1}' -f ($Label -replace '[\\/:*?"<>|]', '_'), (Get-Date -Format 'MMdd_HHmm')
New-Item -ItemType Directory -Force (Join-Path $dir 'shots') | Out-Null
$csv = Join-Path $dir 'title.csv'
Set-Content -Path $csv -Value 't,fps,draws'
if (-not $Attach) {
    # the last session's log is often the only trace of what the user saw: keep one generation
    if (Test-Path $log) { Copy-Item $log (Join-Path $port 'run.prev.log') -Force }
    $diag = @{ RSX_HITCH = '45'; FRAME_LOG = '1'; GEO_STATS = '120' }
    foreach ($k in $Env.Keys) { $diag[$k] = $Env[$k] }
    Set-Content -Path (Join-Path $dir 'env.txt') -Value (($diag.Keys | Sort-Object | ForEach-Object { "$_=$($diag[$_])" }) -join "`r`n")
    foreach ($k in $diag.Keys) { Set-Item -Path "env:$k" -Value $diag[$k] }
    Start-Process -FilePath cmd.exe -ArgumentList '/c', (Join-Path $port 'run.bat') -WindowStyle Minimized
    foreach ($k in $diag.Keys) { Remove-Item -Path "env:$k" -ErrorAction SilentlyContinue }
}
Write-Host "recording to $dir (ends when the game exits)"

$t0 = Get-Date; $seen = $false; $nextShot = 0; $nextCpu = $CpuEvery; $same = 0; $last = ''
while (((Get-Date) - $t0).TotalSeconds -lt $MaxSeconds) {
    Start-Sleep -Milliseconds 1000
    $p = Get-Process MotorStormApocalypse -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
    if (-not $p) { if ($seen) { break }; if (((Get-Date) - $t0).TotalSeconds -gt 60) { throw 'no game window after 60 s' }; continue }
    $seen = $true
    $t = [int]((Get-Date) - $t0).TotalSeconds
    $p.Refresh(); $title = $p.MainWindowTitle
    if ($title -match 'FPS: ([0-9.]+) \| draws: ([0-9]+)') {
        Add-Content -Path $csv -Value ("{0},{1},{2}" -f $t, $Matches[1], $Matches[2])
        # Freeze rule: title unchanged 10 s with a non-zero FPS = frozen. Say so, keep recording.
        if ($title -eq $last) { $same++ } else { $same = 0; $last = $title }
        if ($same -eq 10) { Write-Warning "t=$t s: title unchanged for 10 s (frozen?)"; Add-Content -Path $csv -Value "# t=$t title unchanged for 10 s" }
        $inRace = [int]$Matches[2] -ge 1500
        if ($inRace -and $t -ge $nextShot) {
            $nextShot = $t + $ShotEvery
            try { & (Join-Path $PSScriptRoot 'screenshot.ps1') -Out (Join-Path $dir ("shots\{0:D4}.png" -f $t)) | Out-Null } catch {}
        }
        if ($inRace -and $t -ge $nextCpu) {
            $nextCpu = $t + $CpuEvery
            try {
                Add-Content -Path (Join-Path $dir 'threads.txt') -Value "=== t=$t  $title"
                (& (Join-Path $PSScriptRoot 'thread_cpu.ps1') -Seconds 2 6>&1 | Out-String) | Add-Content -Path (Join-Path $dir 'threads.txt')
            } catch {}
        }
    }
}
for ($w = 0; $w -lt 20 -and (Get-Process MotorStormApocalypse -ErrorAction SilentlyContinue); $w++) { Start-Sleep 1 }
if (Test-Path $log) { Copy-Item $log (Join-Path $dir 'run.log') -Force }
Write-Host "done: $dir"
