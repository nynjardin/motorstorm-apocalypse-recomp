# The same STILL view in every run: the bike left on the starting grid, no throttle, until the
# pack is gone. Records what the title draws there (DRAW_SIG, toolkit patch #47) and a screenshot,
# to compare two settings object by object (drawsig_static.py --cmp): an object one setting draws
# and the other does not is a visibility / LOD / occlusion difference, with no camera or traffic
# noise.
#   scripts\idle_sig.ps1 -Label base [-Track quai|pont] [-Env @{PORT_JOBMODS_EXCLUDE='220'}] [-Frames 800]
# Results: E:\ms_perf\idlesig\<label>.bin / .png / .tick (GetTickCount of the still window) / .log.
# Compare: python scripts\drawsig_static.py a.bin --from-tick (cat a.tick) --cmp b.bin --cmp-tick (cat b.tick)
param(
    [string]$Label = 'base',
    [string]$Track = 'quai',
    [hashtable]$Env = @{},
    [int]$Frames = 800           # game frames after the X before the still window (the pack must be gone)
)
$ErrorActionPreference = 'Stop'
$port = Join-Path $PSScriptRoot '..\port'
$pad = Join-Path $env:TEMP 'motorstorm_pad.txt'
$dir = 'E:\ms_perf\idlesig'
New-Item -ItemType Directory -Force $dir | Out-Null
$bin = Join-Path $dir "$Label.bin"
function Write-Pad([string]$v) {
    for ($try = 0; ; $try++) {
        try { Set-Content -Path $pad -Value $v -NoNewline -ErrorAction Stop; break }
        catch { if ($try -ge 50) { throw }; Start-Sleep -Milliseconds 20 }
    }
}
function Get-Title {
    $p = Get-Process MotorStormApocalypse -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
    if ($p) { $p.Refresh(); return $p.MainWindowTitle }
    return ''
}
$e = @{} + $Env
$e['DRAW_SIG'] = $bin
$e['DRAW_SIG_FRAMES'] = '6000'
& (Join-Path $PSScriptRoot 'goto_race.ps1') -Track $Track -Env $e -AfterSeconds 5 | Out-Null
$t0 = Get-Date; $hits = 0
while ($hits -lt 3) {      # race presentation: many draws a few seconds in a row
    if (-not (Get-Process MotorStormApocalypse -ErrorAction SilentlyContinue)) { throw 'game exited during loading' }
    if (((Get-Date) - $t0).TotalSeconds -gt 600) { throw 'race presentation not reached' }
    Start-Sleep 2
    if ((Get-Title) -match 'draws: ([0-9]+)' -and [int]$Matches[1] -gt 500) { $hits++ } else { $hits = 0 }
}
Start-Sleep 3
Write-Pad '0x4000 10'       # X: start, then nothing: the bike stays on the grid
# Wait in GAME frames (title "| f N"), not seconds: a slow setting runs the race in slow motion and
# the pack would still be on screen after the same wall time.
function Get-Frame { if ((Get-Title) -match '\| f ([0-9]+)') { return [long]$Matches[1] } return -1 }
$f0 = Get-Frame; $last = ''; $same = 0; $fps = @(); $w0 = Get-Date
while ($true) {
    Start-Sleep 1
    $t = Get-Title
    if ($t -eq $last) { $same++ } else { $same = 0; $last = $t }
    if ($same -ge 10) { throw "FROZEN (title unchanged for 10 s): $t ; game left running" }
    $f = Get-Frame
    if ($f0 -lt 0) { $f0 = $f }
    if ($f -ge 0 -and ($f - $f0) -ge $Frames) { break }
    if (((Get-Date) - $w0).TotalSeconds -gt 900) { throw 'still window not reached in 900 s' }
}
$tick = [Environment]::TickCount64
Set-Content (Join-Path $dir "$Label.tick") $tick
Start-Sleep 2
& (Join-Path $PSScriptRoot 'screenshot.ps1') -Out (Join-Path $dir "$Label.png") | Out-Null
for ($s = 0; $s -lt 4; $s++) { Start-Sleep 1; if ((Get-Title) -match 'FPS: ([0-9.]+)') { $fps += [double]$Matches[1] } }
Get-Process MotorStormApocalypse -ErrorAction SilentlyContinue | Stop-Process -Confirm:$false
Start-Sleep 3
Copy-Item (Join-Path $port 'run.log') (Join-Path $dir "$Label.log") -Force
Write-Host ("[idle_sig] {0} ({1}) FPS {2}" -f $Label, $Track, ($fps -join ' '))
python (Join-Path $PSScriptRoot 'drawsig_static.py') $bin --from-tick $tick 2>&1 | Write-Host
