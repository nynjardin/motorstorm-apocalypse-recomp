# pause_start.ps1 -Out <dir> [-Res 1920x1080] [-Track pont] [-PauseAfter 5.5] [-Caps 5]
#                 [-KillUnit 1] [-Env @{..}]
# The race PAUSED by script just after the start (the pack is still next to the bike), captured
# around the orbit of the pause camera, twice: as it is (cap\off_NN), then with the small draws
# that sample their own target on unit -KillUnit left out (cap\kill_NN; FB_KILL_UNIT_FILE,
# toolkit patch #64 tools). The world is frozen in pause, only the camera turns: what is in the
# "off" frames and in none of the "kill" frames is drawn by those draws.
# -KillSpecs '0 8','9 64': one series per vertex-count range (cap\kill0_NN, kill1_NN, series.txt).
# -PauseAfter: seconds between the X that leaves the presentation and START (the countdown takes
# ~4 s: 5.5 = about 1.5 s of race). -KillUnit -1 = no second series.
# Then: scripts\orbit_sheet.py <Out> makes the contact sheet of both series.
param(
    [Parameter(Mandatory)][string]$Out,
    [string]$Res = '1920x1080',
    [string]$Track = 'pont',
    [double]$PauseAfter = 5.5,
    [int]$Caps = 5,
    [int]$KillUnit = 1,
    [string[]]$KillSpecs = @('0 64'),
    [hashtable]$Env = @{},
    # -Photo: from the pause into the game's photo mode (DOWN, DOWN, X): the camera stays put,
    # so captures of different frames line up (the pause camera orbits on its own).
    [switch]$Photo,
    # -Gates: one more capture per entry, the entry written to the gate file ('fpb=301' = stop
    # before the first draw of program 0x301, 'fp=301' = after its last one), named gate_NN.
    [string[]]$Gates = @()
)
$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force $Out | Out-Null
$gate = Join-Path $Out 'gate.txt'; $cap = Join-Path $Out 'cap'; $kill = Join-Path $Out 'kill_unit.txt'
Remove-Item $gate -ErrorAction SilentlyContinue
Set-Content -Path $kill -Value '-1' -NoNewline
$e = @{ PORT_RES = $Res; RSX_CAP_GATE = $gate; RSX_CAP_DIR = $cap; FB_KILL_UNIT_FILE = $kill }
foreach ($k in $Env.Keys) { $e[$k] = $Env[$k] }
$pad = Join-Path $env:TEMP 'motorstorm_pad.txt'

function Get-Title {
    $p = Get-Process MotorStormApocalypse -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
    if (-not $p) { return $null }
    $p.Refresh(); return $p.MainWindowTitle
}
function Take-Capture([string]$name, [string]$content = '0') {
    $before = @(Get-ChildItem $cap -Directory -ErrorAction SilentlyContinue | ForEach-Object Name)
    Set-Content -Path $gate -Value $content -NoNewline
    $new = $null; $t0 = Get-Date
    while (-not $new -and ((Get-Date) - $t0).TotalSeconds -lt 30) {
        Start-Sleep -Milliseconds 500
        $new = Get-ChildItem $cap -Directory -ErrorAction SilentlyContinue | Where-Object { $before -notcontains $_.Name } | Select-Object -First 1
    }
    if (-not $new) { Write-Host "$name : no capture"; return }
    Start-Sleep 6
    Rename-Item $new.FullName $name
    Write-Host "$name ($(Get-Title))"
}

& (Join-Path $PSScriptRoot 'goto_race.ps1') -Track $Track -AfterSeconds 5 -Env $e
# the race scene (presentation): more than 2000 draws at a steady rate; freeze rule on the title
$t0 = Get-Date; $last = ''; $same = 0; $ok = 0
while ($true) {
    if (((Get-Date) - $t0).TotalSeconds -gt 300) { throw 'race scene not reached' }
    $t = Get-Title
    if (-not $t) { throw 'game exited' }
    if ($t -eq $last) { $same++ } else { $same = 0; $last = $t }
    if ($same -ge 4) { throw "FROZEN (title unchanged 12 s): $t; game left running" }
    if ($t -match 'FPS: ([0-9.]+) \| draws: ([0-9]+)' -and [double]$Matches[1] -gt 20 -and [int]$Matches[2] -gt 2000) { $ok++ } else { $ok = 0 }
    if ($ok -ge 4) { break }
    Start-Sleep 3
}
Set-Content -Path $pad -Value '0x4000 10' -NoNewline          # X: leave the presentation
Start-Sleep -Milliseconds ([int]($PauseAfter * 1000))
Set-Content -Path $pad -Value '0x0008 8' -NoNewline           # START: pause
Start-Sleep 3
Write-Host "paused: $(Get-Title)"
if ($Photo) {
    foreach ($b in '0x0040', '0x0040', '0x4000') { Set-Content -Path $pad -Value "$b 6" -NoNewline; Start-Sleep -Milliseconds 900 }
    Start-Sleep 3
    Write-Host "photo mode: $(Get-Title)"
}
for ($i = 0; $i -lt $Caps; $i++) { Take-Capture ('off_{0:d2}' -f $i) }
for ($i = 0; $i -lt $Gates.Count; $i++) { Take-Capture ('gate_{0:d2}' -f $i) $Gates[$i] }
if ($KillUnit -ge 0) {
    # -KillSpecs: several series, each "<min vertices> <max vertices>" (default: every such draw)
    $k = 0
    foreach ($spec in $KillSpecs) {
        Set-Content -Path $kill -Value "$KillUnit $spec" -NoNewline
        Start-Sleep 2
        $tag = if ($KillSpecs.Count -gt 1) { 'kill{0}_' -f $k } else { 'kill_' }
        for ($i = 0; $i -lt $Caps; $i++) { Take-Capture ($tag + ('{0:d2}' -f $i)) }
        Add-Content (Join-Path $Out 'series.txt') "$tag = unit $KillUnit, vertices $spec"
        $k++
    }
}
Copy-Item (Join-Path $PSScriptRoot '..\port\run.log') (Join-Path $Out 'run.log') -ErrorAction SilentlyContinue
Get-Process MotorStormApocalypse -ErrorAction SilentlyContinue | Stop-Process -Confirm:$false
Write-Host 'game stopped'
