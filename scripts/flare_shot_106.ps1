# 1.06 build: the bridge race ("Un pont vers nulle part"), the presentation screenshot, then the race PAUSED just after the
# start and put in the game's photo mode (the camera stays put): one picture per call, the same view every time, to compare
# an environment setting (the lens-flare intensity: -Env @{FP_SCALE='20EBC1:0.5'}).
#   scripts\flare_shot_106.ps1 -Out E:\ms_perf\flare\k1.png [-Env @{FP_SCALE='20EBC1:0.5'}] [-Res 1920x1080] [-PauseAfter 5.5]
# Writes <Out> (photo view) and <Out without .png>_pres.png (presentation). The game is stopped at the end.
param(
    [Parameter(Mandatory)][string]$Out,
    [hashtable]$Env = @{},
    [string]$Res = '',
    [double]$PauseAfter = 5.5
)
$ErrorActionPreference = 'Stop'
$port = Join-Path $PSScriptRoot '..\port'
$log = Join-Path $port 'run106.log'
$pad = Join-Path $env:TEMP 'motorstorm_pad.txt'
function Write-Pad([string]$v) {
    for ($t = 0; $t -lt 50; $t++) { try { Set-Content -Path $pad -Value $v -NoNewline -ErrorAction Stop; break } catch { Start-Sleep -Milliseconds 20 } }
}
function Press([string]$mask, [double]$wait) { Write-Pad $mask; Start-Sleep -Milliseconds 400; Write-Pad ''; Start-Sleep -Seconds $wait }
function Get-Title {
    $p = Get-Process MotorStormApocalypse -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
    if ($p) { $p.Refresh(); return $p.MainWindowTitle }
}
New-Item -ItemType Directory -Force (Split-Path $Out) | Out-Null
Get-Process MotorStormApocalypse -ErrorAction SilentlyContinue | Stop-Process -Confirm:$false
Start-Sleep 3
Write-Pad ''
$env:PORT_V106 = '1'; $env:PAD_FILE = $pad; $env:PORT_GAME_LOG = 'LogicFullyActive'
if ($Res) { $env:PORT_RES = $Res }
foreach ($k in $Env.Keys) { Set-Item -Path "env:$k" -Value $Env[$k] }
Start-Process -FilePath cmd.exe -ArgumentList '/c', (Join-Path $port 'run.bat') -WindowStyle Minimized
foreach ($k in $Env.Keys) { Remove-Item -Path "env:$k" -ErrorAction SilentlyContinue }
Remove-Item Env:PORT_V106, Env:PORT_GAME_LOG, Env:PORT_RES -ErrorAction SilentlyContinue
$tl = Get-Date; $nStart = 0
while (((Get-Date) - $tl).TotalSeconds -lt 240) {
    Start-Sleep -Seconds 2
    if ((Test-Path $log) -and (Select-String -Path $log -Pattern 'LogicFullyActive \[AnnouncementDisplayLogic\]' -Quiet -ErrorAction SilentlyContinue)) { break }
    if ($nStart -ge 60) { continue }
    $nStart++
    Write-Pad '0x0008 4'; Start-Sleep -Milliseconds 300; Write-Pad ''
}
Start-Sleep 6
Press '0x4000 8' 8                                   # After Party: X (main menu). A launch that skipped the page: START below is harmless.
$steps = @('0x0040 4 2','0x4000 8 6','0x4000 8 8','0x0040 4 2','0x0040 4 2','0x4000 8 4') + (@('0x0040 4 2') * 13) + @('0x4000 8 4','0x0010 4 2','0x0010 4 3','0x4000 8 1')
foreach ($st in $steps) { $pp = $st -split ' '; Press ($pp[0] + ' ' + $pp[1]) ([double]$pp[2]) }
$t0 = Get-Date; $hits = 0
while ($hits -lt 3) {
    if (-not (Get-Process MotorStormApocalypse -ErrorAction SilentlyContinue)) { throw 'game exited during loading' }
    if (((Get-Date) - $t0).TotalSeconds -gt 400) { throw 'race presentation not reached' }
    Start-Sleep 2
    $t = Get-Title
    if ($t -match 'draws: (\d+)' -and [int]$Matches[1] -gt 500) { $hits++ } else { $hits = 0 }
}
Start-Sleep 4
& (Join-Path $PSScriptRoot 'screenshot.ps1') -Out ($Out -replace '\.png$', '_pres.png') | Select-Object -Last 1
Press '0x4000 10' $PauseAfter                        # X leaves the presentation; countdown ~4 s
Press '0x0008 4' 2                                   # START = pause
Press '0x0040 4' 1; Press '0x0040 4' 1; Press '0x4000 8' 3   # DOWN, DOWN, X = photo mode
& (Join-Path $PSScriptRoot 'screenshot.ps1') -Out $Out | Select-Object -Last 1
Get-Process MotorStormApocalypse -ErrorAction SilentlyContinue | Stop-Process -Confirm:$false
