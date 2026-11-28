# Launch the port (disc build, or -V106) and drive it to the Festival prologue race (same race on both builds:
# the only scripted comparison between the disc EBOOT and the 1.06 EBOOT). One run at a time, nothing concurrent.
#   scripts\fest_race.ps1 [-V106] [-Env @{...}] [-Shot <png>]
# Sequence: START until the title is up, X (title -> main menu), wait, X (Festival: continue), X (story page),
# then the race loads by itself; then X on the pre-race page when the log says so, R2 held after the countdown.
# The game is left running; the title bar (FPS) is the measure.
param([switch]$V106, [hashtable]$Env = @{}, [string]$Shot = '', [int]$TitleTimeout = 240, [int]$MenuWait = 14, [switch]$Drive, [int]$DriveSamples = 20)
$ErrorActionPreference = 'Stop'
$port = Join-Path $PSScriptRoot '..\port'
$log = Join-Path $port ($(if ($V106) { 'run106.log' } else { 'run.log' }))
$pad = Join-Path $env:TEMP 'motorstorm_pad.txt'
function Send-Pad([string]$mask) {
    for ($t = 0; $t -lt 50; $t++) { try { Set-Content -Path $pad -Value $mask -NoNewline -ErrorAction Stop; break } catch { Start-Sleep -Milliseconds 100 } }
}
function Press([string]$mask, [double]$wait) { Send-Pad $mask; Start-Sleep -Milliseconds 400; Send-Pad ''; Start-Sleep -Milliseconds ([int]($wait * 1000)) }
Get-Process MotorStormApocalypse -ErrorAction SilentlyContinue | Stop-Process -Confirm:$false
Start-Sleep 3
Send-Pad ''
if (Test-Path $log) { Copy-Item $log (Join-Path 'E:\ms_perf' ('fest_prev_' + (Split-Path $log -Leaf))) -Force }
if ($V106) { $env:PORT_V106 = '1' } else { Remove-Item Env:PORT_V106 -ErrorAction SilentlyContinue }
$env:PAD_FILE = $pad; $env:PORT_GAME_LOG = '1'
foreach ($k in $Env.Keys) { Set-Item -Path "env:$k" -Value $Env[$k] }
Start-Process -FilePath cmd.exe -ArgumentList '/c', (Join-Path $port 'run.bat') -WindowStyle Minimized
foreach ($k in $Env.Keys) { Remove-Item -Path "env:$k" -ErrorAction SilentlyContinue }
Remove-Item Env:PORT_V106, Env:PORT_GAME_LOG -ErrorAction SilentlyContinue
$t0 = Get-Date
# Title: the disc build logs 'to "TitleScreen"'; START skips the boot screens on both.
$titlePat = $(if ($V106) { 'LogicFullyActive \[AnnouncementDisplayLogic\]' } else { 'to "TitleScreen"' })
$n = 0
while (((Get-Date) - $t0).TotalSeconds -lt $TitleTimeout) {
    Start-Sleep -Seconds 2
    if ((Test-Path $log) -and (Select-String -Path $log -Pattern $titlePat -Quiet -ErrorAction SilentlyContinue)) { break }
    if ($n -ge 40) { continue }
    $n++; Press '0x0008 4' 0
}
Write-Host ("title after {0:N0} s" -f ((Get-Date) - $t0).TotalSeconds)
if ($V106) { Start-Sleep 6 } else { Start-Sleep 3 }   # 1.06: START already passed the title; the After Party page (X) is up
Press '0x4000 8' 0
Start-Sleep $MenuWait
Write-Host ("main menu after {0:N0} s" -f ((Get-Date) - $t0).TotalSeconds)
Press '0x4000 8' 6     # Festival (cursor starts on it)
Press '0x4000 8' 6     # story page -> race load
Write-Host ("pressed; race loading, t={0:N0} s" -f ((Get-Date) - $t0).TotalSeconds)
if ($Drive) {   # wait for the end of the countdown, hold R2, print the elapsed time of R2 and the FPS every 2 s
    for ($i = 0; $i -lt 240; $i++) { if (Select-String -Path $log -Pattern 'COUNTDOWN : \[0\]' -Quiet -ErrorAction SilentlyContinue) { break }; Start-Sleep 1 }
    Send-Pad '0x0200 3000'
    Write-Host ("R2 held at t={0:N0} s" -f ((Get-Date) - $t0).TotalSeconds)
    $f = @(); for ($i = 0; $i -lt $DriveSamples; $i++) { Start-Sleep 2; $f += ((Get-Process MotorStormApocalypse).MainWindowTitle -replace '.*FPS: ([0-9.]+).*', '$1') }
    Write-Host ("FPS: " + ($f -join ' '))
    $v = $f | ForEach-Object { [double]$_ } | Select-Object -Skip 4
    Write-Host ("mean after 8 s: {0:N1}" -f ($v | Measure-Object -Average).Average)
}
if ($Shot) { Start-Sleep 5; & (Join-Path $PSScriptRoot 'screenshot.ps1') -Out $Shot | Select-Object -Last 1 }
