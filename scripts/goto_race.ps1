# Launch the port and drive it to a "Pour le fun" (single) race with PAD_FILE.
# Needs an existing save (otherwise the title asks 3 confirmations for screen/pad settings).
#   scripts\goto_race.ps1 [-Env @{PORT_JOBMODS='1'}] [-AfterSeconds 60] [-Shot <png>]
#   scripts\goto_race.ps1 -Track pont     # "Un pont vers nulle part" (Good Herb), the reference race
# Title detection: the port logs the (skipped) "maintitles" video right before the title screen.
# User-given sequence from "Appuyer sur une touche" (2026-11-21), X = CROSS:
#   X, DOWN, X, X, DOWN, DOWN, X, 11x DOWN, X, UP, UP, X  -> race loading.

param(
    [hashtable]$Env = @{},
    [int]$AfterSeconds = 60,
    [string]$Shot = "",
    [string]$ShotDir = "",
    [string[]]$Steps = @(),
    [string]$Track = "",
    [int]$TitleTimeout = 300,
    [double]$MenuScale = 0.5,
    [switch]$NoStart,     # stop on the Course rapide setup screen (no final X), game left running
    [switch]$Multiplayer  # "Pour le fun" -> DOWN -> X = "Multijoueur" (online Wreckreation), then stop; game left running
)
$ErrorActionPreference = 'Stop'
# Presets for -Steps (presses on the Course rapide setup screen, before the final X).
if ($Track -eq 'pont') {
    # DOWN = "Changer de vehicule", X opens it (cursor on the Dirt bike), X = Dirt bike, X = first model
    # (Wasabi Wildcat MX): the title does not always save the vehicle, so it is chosen every time.
    # Then DOWN = "Circuit", X, 11x DOWN, X = "Un pont vers nulle part", UP UP = "Depart".
    $Steps = @('0x0040 4 3', '0x4000 8 5', '0x4000 8 5', '0x4000 8 5', '0x0040 4 3', '0x4000 8 5') +
             (@('0x0040 4 2') * 11) + @('0x4000 8 5', '0x0010 4 2', '0x0010 4 3')
} elseif ($Track -eq 'quai') {
    # "Quai sous pression" (track_pier_v1): the circuit the setup screen opens on, vehicle = the saved one.
} elseif ($Track -match '^c([0-9]+)$') {
    # c<N> = the circuit N entries below the first one of the list (c11 = pont), with the Dirt bike:
    # for a circuit that was never loaded (first-visit effects: shaders, pipelines, cold disk).
    $Steps = @('0x0040 4 3', '0x4000 8 5', '0x4000 8 5', '0x4000 8 5', '0x0040 4 3', '0x4000 8 5') +
             (@('0x0040 4 2') * [int]$Matches[1]) + @('0x4000 8 5', '0x0010 4 2', '0x0010 4 3')
} elseif ($Track) { throw "unknown -Track '$Track' (known: pont, quai, c<N>)" }
$port = Join-Path $PSScriptRoot '..\port'
$log = Join-Path $port 'run.log'
$pad = Join-Path $env:TEMP 'motorstorm_pad.txt'

Get-Process MotorStormApocalypse -ErrorAction SilentlyContinue | Stop-Process -Confirm:$false
Start-Sleep 2
# after the old game is gone: it holds the pad file open at every poll
for ($try = 0; ; $try++) { try { Set-Content -Path $pad -Value '' -NoNewline -ErrorAction Stop; break } catch { if ($try -ge 50) { throw }; Start-Sleep -Milliseconds 100 } }
# A stale log would match the title at once. It is moved, not deleted: the log of the session the
# user just played is often the only trace of what they saw (lost that way on 2026-11-23).
if (Test-Path $log) { Move-Item $log (Join-Path $port 'run.prev.log') -Force }
# Keep a copy of the save whenever it changed since the last copy: a navigation gone astray once
# walked through "Mon MotorStorm" and the title autosaved another vehicle (2026-11-22).
$save = Join-Path $port 'gamedata\dev_hdd0\home\00000001\savedata\BLES00000'
$bakRoot = 'E:\ms_perf\save_backups'
if (Test-Path (Join-Path $save 'AUTOSAVE.DAT')) {
    $h = (Get-FileHash (Join-Path $save 'AUTOSAVE.DAT') -Algorithm SHA1).Hash
    $known = Get-ChildItem $bakRoot -Recurse -Filter AUTOSAVE.DAT -ErrorAction SilentlyContinue |
             Where-Object { (Get-FileHash $_.FullName -Algorithm SHA1).Hash -eq $h } | Select-Object -First 1
    if (-not $known) {
        $dst = Join-Path $bakRoot (Get-Date -Format 'yyyyMMdd_HHmmss')
        New-Item -ItemType Directory -Force $dst | Out-Null
        Copy-Item (Join-Path $save '*') $dst
        Write-Host "save changed: copied to $dst"
    }
}
$env:PAD_FILE = $pad
foreach ($k in $Env.Keys) { Set-Item -Path "env:$k" -Value $Env[$k] }
Start-Process -FilePath cmd.exe -ArgumentList '/c', (Join-Path $port 'run.bat') -WindowStyle Minimized
# The game has its environment now: remove what -Env set, or the next launch from this same
# PowerShell session inherits it (a chained A/B pair then compares B with B).
foreach ($k in $Env.Keys) { Remove-Item -Path "env:$k" -ErrorAction SilentlyContinue }
Start-Sleep 5

$script:step = 0
# -MenuScale scales every menu wait (1 = old timings, 0.5 = twice as fast); lower until a press is lost.
$script:menuScale = $MenuScale
function Send-Pad([string]$mask, [double]$wait) {
    # The game opens the file every pad poll: retry a write that hits it.
    for ($try = 0; ; $try++) {
        try { Set-Content -Path $pad -Value $mask -NoNewline -ErrorAction Stop; break }
        catch { if ($try -ge 50) { throw }; Start-Sleep -Milliseconds 20 }
    }
    Write-Host "pad $mask"
    Start-Sleep -Milliseconds ([int]($wait * 1000 * $script:menuScale))
    if ($ShotDir) {   # one screenshot after each press: shows what the menus selected
        $script:step++
        & (Join-Path $PSScriptRoot 'screenshot.ps1') -Out (Join-Path $ShotDir ("step{0}.png" -f $script:step))
    }
}

$t0 = Get-Date
while (-not (Test-Path $log) -or -not (Select-String -Path $log -Pattern 'maintitles' -Quiet)) {
    if (-not (Get-Process MotorStormApocalypse -ErrorAction SilentlyContinue)) { throw 'game exited before the title screen' }
    if (((Get-Date) - $t0).TotalSeconds -gt $TitleTimeout) { throw 'title screen not reached' }
    Start-Sleep 2
    # Freeze rule: window title (FPS) unchanged for 10 s = frozen; game left running for inspection.
    $gp = Get-Process MotorStormApocalypse -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
    if ($gp) { $gp.Refresh(); $gt = $gp.MainWindowTitle
        if ($gt -match 'FPS: [1-9]' -and $gt -eq $script:lastTitle) { $script:sameTitle++ } else { $script:sameTitle = 0; $script:lastTitle = $gt }
        if ($script:sameTitle -ge 8) { throw 'FROZEN before the title screen (title unchanged for 16 s); game left running' } }
}
Write-Host ("title screen after {0:N0}s" -f ((Get-Date) - $t0).TotalSeconds)
Start-Sleep -Milliseconds ([int](6000 * $MenuScale))   # maintitles (short clip) -> title screen (was 15 s)
Send-Pad '0x4000 8' 4      # X: title -> main menu
# The main menu takes 5-10 s to appear (white flash first, ~12 draws): a DOWN sent before it is up is
# lost, and the next X then opens "Festival" (prologue) instead of "Pour le fun". Wait for the flash
# (the title screen itself draws > 100), then for the menu.
$m0 = Get-Date; $up = 0; $flash = $false; $d = 0
while ($up -lt 2 -and ((Get-Date) - $m0).TotalSeconds -lt 40) {
    Start-Sleep -Milliseconds 300
    if (-not $flash -and $up -eq 0 -and ((Get-Date) - $m0).TotalSeconds -gt 8 -and $d -gt 100) { break }   # no white flash with an existing save (seen 2026-11-27): menu is up
    $gp = Get-Process MotorStormApocalypse -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
    if ($gp) { $gp.Refresh(); if ($gp.MainWindowTitle -match 'draws: ([0-9]+)') { $d = [int]$Matches[1]; if ($env:MENU_TRACE) { Write-Host ("{0:N1}s d={1}" -f ((Get-Date)-$m0).TotalSeconds, $d) }; if ($d -lt 50) { $flash = $true; $up = 0 } elseif ($flash -and $d -gt 100) { $up++ } } }
}
Write-Host ("main menu up after {0:N0}s" -f ((Get-Date) - $m0).TotalSeconds)
Start-Sleep -Milliseconds ([int](3000 * $MenuScale))
Send-Pad '0x0040 4' 3      # DOWN: "Pour le fun"
Send-Pad '0x4000 8' 5      # X: "Pour le fun" -> Course rapide / Multijoueur / Epreuves speciales
if ($Multiplayer) {
    Send-Pad '0x0040 4' 3  # DOWN: "Multijoueur"
    Send-Pad '0x4000 8' 5  # X: sign-in / terms checks, then the online Wreckreation home (docs/reseau.md)
    return
}
Send-Pad '0x4000 8' 5      # X: "Course rapide" -> setup screen (DEPART selected, circuit "Quai sous pression")
# -Steps 'mask frames wait',...: extra presses on the setup screen before the last X (e.g. change circuit).
# Durations are counts of pad reports, on purpose: the menus auto-repeat a direction every ~5 FRAMES
# held, and they run at 100+ FPS, so a hold in time ('120ms', toolkit patch #29) moves 2-3 entries.
# Masks: CROSS 0x4000, CIRCLE 0x2000, UP 0x0010, DOWN 0x0040, LEFT 0x0080, RIGHT 0x0020, START 0x0008.
foreach ($s in $Steps) { $p = $s -split ' '; Send-Pad ("{0} {1}" -f $p[0], $p[1]) ([double]$p[2]) }
if ($NoStart) { return }
Start-Sleep 2              # let the cursor settle on DEPART (1.5 s was not enough at -MenuScale 0.5)
Send-Pad '0x4000 8' 5      # X: last confirmation, start the race (user-verified 2026-11-20)
Start-Sleep $AfterSeconds
if ($Shot) { & (Join-Path $PSScriptRoot 'screenshot.ps1') -Out $Shot }
