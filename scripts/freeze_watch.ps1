# Watch the running game for a freeze and capture its state when one happens.
# Rule (user, 2026-11-21): the window title shows the FPS; unchanged for 5 s = probably frozen,
# unchanged for 10 s = frozen. On a freeze this writes into <OutDir>\<HHmmss>\ :
#   stacks.txt  every thread's call chain (scripts/host_stacks.py)
#   locks.txt   lv2 mutexes / condition variables in use (scripts/host_locks.py)
#   run.log     copy of the port log at that moment
# and prints one "FROZEN ..." line. The game is never stopped. Runs until the game has been
# absent for -GoneSeconds, or -MaxSeconds. Start it next to any scripted run:
#   scripts\freeze_watch.ps1 [-OutDir E:\ms_perf\freeze] [-Once]
# Known false positive: the ~40 s of black after X on "DEPART" (PSO compilation, no flip).
param(
    [string]$OutDir = 'E:\ms_perf\freeze',
    [int]$StuckSeconds = 10,
    [int]$GoneSeconds = 60,
    [int]$MaxSeconds = 3600,
    [switch]$Once
)
$py = 'I:\Projets\Recomp\.venv\Scripts\python.exe'
$port = Join-Path $PSScriptRoot '..\port'
function Get-Title {
    $p = Get-Process MotorStormApocalypse -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
    if ($p) { $p.Refresh(); return $p.MainWindowTitle }
    return $null
}
$t0 = Get-Date; $last = $null; $same = 0; $gone = 0; $reported = $null
while (((Get-Date) - $t0).TotalSeconds -lt $MaxSeconds) {
    Start-Sleep 1
    $t = Get-Title
    if (-not $t) { $gone++; $same = 0; $last = $null; $reported = $null; if ($gone -ge $GoneSeconds) { break }; continue }
    $gone = 0
    if ($t -notmatch 'FPS: ') { continue }          # window not up yet
    if ($t -eq $last) { $same++ } else { $same = 0; $last = $t; $reported = $null }
    if ($same -ge $StuckSeconds -and $reported -ne $t) {
        $reported = $t
        $dir = Join-Path $OutDir (Get-Date -Format 'HHmmss')
        New-Item -ItemType Directory -Force $dir | Out-Null
        & $py (Join-Path $PSScriptRoot 'host_stacks.py') --samples 15 --depth 14 2>&1 | Out-File (Join-Path $dir 'stacks.txt') -Encoding utf8
        & $py (Join-Path $PSScriptRoot 'host_locks.py') 2>&1 | Out-File (Join-Path $dir 'locks.txt') -Encoding utf8
        Copy-Item (Join-Path $port 'run.log') (Join-Path $dir 'run.log') -ErrorAction SilentlyContinue
        Write-Output ("FROZEN {0} title='{1}' -> {2}" -f (Get-Date -Format 'HH:mm:ss'), $t, $dir)
        if ($Once) { break }
    }
}
Write-Output 'freeze_watch: done'
