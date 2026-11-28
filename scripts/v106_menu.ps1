# 1.06 build: launch it with a pad file, skip the boot screens with START, and optionally press buttons.
#   scripts\v106_menu.ps1 [-Presses '0x4000 8 5','0x0040 4 3' ...] [-Shot <png>] [-NoLaunch]
# A press = "<mask> <frames> <seconds to wait after>" (masks: X 0x4000, START 0x0008, DOWN 0x0040, UP 0x0010,
# RIGHT 0x0020, LEFT 0x0080, CIRCLE 0x2000, TRIANGLE 0x1000, SQUARE 0x8000), as in goto_race.ps1.
# The launch part now does both presses (title, After Party): -Presses begin on the main menu
# (Festival / Pour le fun / Mon MotorStorm / Options). Race: '0x0040 4 2' (to Pour le fun), '0x4000 8 6', '0x4000 8 8'
# (Course rapide), '0x0040 4 2', '0x0010 4 2', '0x4000 8 150'. Old note:
# 1.06 sequence (user, 27 Nov evening): after "Appuyer sur une touche" the game shows a NEW screen presenting the new map
# (Alcatraz, "Le rock du bagne") and the new modes: it must be validated (X) before the main menu. Whether it comes up
# it shows again on later launches ("After Party": The Rock island, special events; button CONTINUER = X), at a point
# of the sequence that varies: when a run looks stuck, take a screenshot first (2026-11-28: the game sat on it). Without it, "Pour le fun" ... lands on another menu than expected.
# With -NoLaunch the running game is driven (it must have been started with PAD_FILE = %TEMP%\motorstorm_pad.txt).
param([string[]]$Presses = @(), [string]$Shot = '', [switch]$NoLaunch, [int]$TitleTimeout = 240, [switch]$Lan)   # -Lan: through run_lan.bat (multiplayer env)
$ErrorActionPreference = 'Stop'
$port = Join-Path $PSScriptRoot '..\port'
$log = Join-Path $port 'run106.log'
$pad = Join-Path $env:TEMP 'motorstorm_pad.txt'
function Send-Pad([string]$mask) {
    for ($t = 0; $t -lt 50; $t++) { try { Set-Content -Path $pad -Value $mask -NoNewline -ErrorAction Stop; break } catch { Start-Sleep -Milliseconds 100 } }
}
if (-not $NoLaunch) {
    Get-Process MotorStormApocalypse -ErrorAction SilentlyContinue | Stop-Process -Confirm:$false
    Start-Sleep 3
    Send-Pad ''
    $env:PORT_V106 = '1'; $env:PAD_FILE = $pad; $env:PORT_GAME_LOG = '1'   # the game's own log names the screens ("Switching Screen")
    Start-Process -FilePath cmd.exe -ArgumentList '/c', (Join-Path $port $(if ($Lan) { 'run_lan.bat' } else { 'run.bat' })) -WindowStyle Minimized
    $t0 = Get-Date
    # START skips the boot screens and passes "Appuyer sur une touche"; then the After Party page comes up (every launch;
    # the game's log says "LogicFullyActive [AnnouncementDisplayLogic]"); X on it (about 6 s later) gives the main menu.
    # START is pressed ONLY until that line (hard cap 60 presses): it used to be pressed for the whole timeout, and
    # START = pause / resume in a race presentation (user, 2026-11-28).
    $nStart = 0
    while (((Get-Date) - $t0).TotalSeconds -lt $TitleTimeout) {
        Start-Sleep -Seconds 2
        if ((Test-Path $log) -and (Select-String -Path $log -Pattern 'LogicFullyActive \[AnnouncementDisplayLogic\]' -Quiet -ErrorAction SilentlyContinue)) { break }
        if ($nStart -ge 60) { continue }
        $nStart++
        Send-Pad '0x0008 4'; Start-Sleep -Milliseconds 300; Send-Pad ''
    }
    Start-Sleep 6
    Send-Pad '0x4000 8'; Start-Sleep -Milliseconds 400; Send-Pad ''; Start-Sleep 8      # CONTINUER on After Party -> main menu
    Write-Host ("main menu after {0:N0} s" -f ((Get-Date) - $t0).TotalSeconds)
}
foreach ($p in $Presses) {
    $parts = $p -split ' '
    Send-Pad ($parts[0] + ' ' + $parts[1])
    Start-Sleep -Milliseconds 400
    Send-Pad ''
    Start-Sleep -Seconds ([double]$parts[2])
    Write-Host "pad $p"
}
if ($Shot) { & (Join-Path $PSScriptRoot 'screenshot.ps1') -Out $Shot | Select-Object -Last 1 }
