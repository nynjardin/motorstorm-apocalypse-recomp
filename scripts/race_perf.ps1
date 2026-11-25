# FPS measurement on the reference race "Un pont vers nulle part" (Good Herb).
# Launches the port through goto_race.ps1 -Track pont, waits for the race presentation (window title
# draws > 500), presses X (skips it), waits for the race, then samples the window-title FPS:
#   -IdleSeconds  on the start line (countdown + standing; 0 = none: R2 from the start, the bike
#                 leaves with the pack = the load of a real race, heavier than the empty track),
#   -DriveSeconds with R2 held (driving).
# After X the script waits for the race scene itself (title draws > 4500 three seconds in a row,
# at most -StartWait seconds) instead of a fixed time: at 20+ FPS the old fixed 75 s + 40 s let the
# opponents finish a lap before the bike moved. Drive begin is now ~60 s earlier than before
# 2026-11-23: read it in race_perf_marks.txt before choosing a PS3_FTRACE / PS3_SAMPLE_DELAY start.
# Every phase is marked in port\run.log ("[race_perf] <phase>"), so PERF=1 / FRAME_BUDGET lines can
# be split per phase afterwards. Prints a summary (median/mean title FPS per phase) and stops the game.
#   scripts\race_perf.ps1 -Label base -Env @{PERF='1'}
param(
    [hashtable]$Env = @{},
    [string]$Label = "run",
    [int]$IdleSeconds = 20,
    [int]$DriveSeconds = 60,
    [int]$StartWait = 90,      # after X: longest wait for the race scene (PSO compilation = black)
    [string]$ShotDir = "",
    [string]$Track = 'pont',   # 'quai' = "Quai sous pression" (goto_race.ps1 -Track)
    [switch]$KeepRunning
)
$ErrorActionPreference = 'Stop'
$port = Join-Path $PSScriptRoot '..\port'
$log = Join-Path $port 'run.log'
$pad = Join-Path $env:TEMP 'motorstorm_pad.txt'

function Write-Pad([string]$v) {
    for ($try = 0; ; $try++) {
        try { Set-Content -Path $pad -Value $v -NoNewline -ErrorAction Stop; break }
        catch { if ($try -ge 50) { throw }; Start-Sleep -Milliseconds 20 }
    }
}
function Get-Title {
    $p = Get-Process MotorStormApocalypse -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
    if ($p) { $p.Refresh(); return $p.MainWindowTitle }
    return $null
}
function Parse-Title([string]$t) {
    if ($t -match 'FPS: ([0-9.]+) \| draws: ([0-9]+)') { return @([double]$Matches[1], [int]$Matches[2]) }
    return $null
}
$marks = Join-Path $port 'race_perf_marks.txt'
Set-Content -Path $marks -Value '' -NoNewline
function Mark([string]$what) {
    # run.log is held exclusively by the cmd redirect: marks go to their own file, with the log's
    # byte size at that moment (split the log per phase with it) and the time since the launch.
    $sz = (Get-Item $log -ErrorAction SilentlyContinue).Length
    $line = "{0} {1:N0}s {2}" -f $sz, ((Get-Date) - $script:launch).TotalSeconds, $what
    Add-Content -Path $marks -Value $line
    Write-Host "[race_perf] $line"
}
function Sample([string]$phase, [int]$seconds) {
    Mark "$phase begin"
    $vals = @(); $scene = @()
    for ($i = 0; $i -lt $seconds; $i++) {
        Start-Sleep 1
        $r = Parse-Title (Get-Title)
        if ($r) { $vals += $r[0]; $script:lastDraws = $r[1]; if ($r[1] -ge 3500) { $scene += $r[0] } }
        if ($ShotDir -and $i % 15 -eq 14 -and $i -lt $seconds - 1) {   # what the phase looked like
            & (Join-Path $PSScriptRoot 'screenshot.ps1') -Out (Join-Path $ShotDir "$SafeLabel-$phase-$($i + 1)s.png") | Out-Null
        }
    }
    Mark "$phase end"
    if ($ShotDir) { & (Join-Path $PSScriptRoot 'screenshot.ps1') -Out (Join-Path $ShotDir "$SafeLabel-$phase.png") | Out-Null }
    $s = $vals | Sort-Object
    $med = if ($s.Count) { $s[[int][math]::Floor($s.Count / 2)] } else { 0 }
    $mean = if ($s.Count) { ($s | Measure-Object -Average).Average } else { 0 }
    # Samples of the full race scene only (>= 3500 draws): the scripted bike crashes within ~15 s
    # (crash camera, 700-900 draws, 30+ FPS, respawn prompt), which flatters the plain figures.
    $sc = $scene | Sort-Object
    $scMed = if ($sc.Count) { $sc[[int][math]::Floor($sc.Count / 2)] } else { 0 }
    return [pscustomobject]@{ Phase = $phase; Median = $med; Mean = [math]::Round($mean, 2); Min = $s[0]; Max = $s[-1]; N = $s.Count; Draws = $script:lastDraws; SceneMed = $scMed; SceneN = $sc.Count }
}

if ($ShotDir) { New-Item -ItemType Directory -Force $ShotDir | Out-Null }
$script:launch = Get-Date
$SafeLabel = $Label -replace '[\\/:*?"<>|]', '_'
& (Join-Path $PSScriptRoot 'goto_race.ps1') -Track $Track -Env $Env -AfterSeconds 5
$t0 = Get-Date
# Race presentation: many draws for a few seconds in a row (loading screen ~7 draws).
$hits = 0
while ($hits -lt 3) {
    if (-not (Get-Process MotorStormApocalypse -ErrorAction SilentlyContinue)) { throw 'game exited during loading' }
    if (((Get-Date) - $t0).TotalSeconds -gt 400) { throw 'race presentation not reached' }
    Start-Sleep 2
    $tt = Get-Title
    # Freeze rule: title (FPS) unchanged for 10 s = frozen. Stop at once, game left running for
    # scripts\host_stacks.py / host_locks.py (freeze_watch.ps1 captures them by itself).
    if ($tt -and $tt -eq $script:lastTitle) { $script:sameTitle++ } else { $script:sameTitle = 0; $script:lastTitle = $tt }
    if ($script:sameTitle -ge 5) { throw 'FROZEN during loading (title unchanged for 10 s); game left running' }
    $r = Parse-Title $tt
    if ($r -and $r[1] -gt 500) { $hits++ } else { $hits = 0 }
}
Mark ("presentation after {0:N0}s" -f ((Get-Date) - $t0).TotalSeconds)
$pres = Sample 'presentation' 10
Write-Pad '0x4000 10'   # X: start
Mark 'X pressed'
$tx = Get-Date; $hits = 0
while ($hits -lt 3 -and ((Get-Date) - $tx).TotalSeconds -lt $StartWait) {
    Start-Sleep 1
    $r = Parse-Title (Get-Title)
    if ($r -and $r[1] -gt 4500) { $hits++ } else { $hits = 0 }
}
Mark ("race scene after {0:N0}s" -f ((Get-Date) - $tx).TotalSeconds)
$idle = if ($IdleSeconds -gt 0) { Sample 'idle' $IdleSeconds } else { $null }
# Always keep one picture of the start line: the scripted menu navigation sometimes lands on another
# race (one DOWN too many = "Buena vista" instead of the bridge), and nothing else tells.
$proof = 'E:\ms_perf\race_perf_shots'; New-Item -ItemType Directory -Force $proof | Out-Null
& (Join-Path $PSScriptRoot 'screenshot.ps1') -Out (Join-Path $proof ("{0}_{1}.png" -f (Get-Date -Format 'yyyyMMdd_HHmm'), $SafeLabel)) | Out-Null
Write-Pad ('0x0200 {0}' -f (($DriveSeconds + 10) * 30))   # R2 held
$drive = Sample 'drive' $DriveSeconds
Write-Pad ''
Mark 'done'
$res = @($pres, $idle, $drive) | Where-Object { $_ }
$res | Format-Table -AutoSize | Out-String | Write-Host
$sum = Join-Path $port 'race_perf.txt'
# The start line of the reference race draws 5280-5850 times a frame (more as the game gets faster): anything else is another race
# (scripted menu navigation went astray, about one run in ten) and the figures are worthless.
$wrong = ''
if ($Track -eq 'pont' -and $idle -and ($idle.Draws -lt 5000 -or $idle.Draws -gt 6000)) {
    $wrong = ' [MAUVAISE COURSE: {0} draws a l''arret, attendu ~5300; run a jeter]' -f $idle.Draws
    Write-Warning "wrong race: $($idle.Draws) draws on the start line (expected ~5300). Discard this run."
}
Add-Content -Path $sum -Value ("{0} {1}{2}  " -f (Get-Date -Format 'yyyy-MM-dd HH:mm'), $Label, $wrong) -NoNewline
Add-Content -Path $sum -Value (($res | ForEach-Object { "{0}: med {1} mean {2} ({3}-{4}, draws {5}; scene {6} n={7})" -f $_.Phase, $_.Median, $_.Mean, $_.Min, $_.Max, $_.Draws, $_.SceneMed, $_.SceneN }) -join ' | ')
if (-not $KeepRunning) {
    Get-Process MotorStormApocalypse -ErrorAction SilentlyContinue | Stop-Process -Confirm:$false
}
