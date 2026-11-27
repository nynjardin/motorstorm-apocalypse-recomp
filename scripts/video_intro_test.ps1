# video_intro_test.ps1 [-Env @{..}] [-Timeout 240] [-Out E:\ms_perf\video\intro]
# The whole boot with the REAL movies (PORT_PLAY_VIDEOS=1) and no pad: logo movie, the 98 s intro, title
# screen. Prints the screens the game went through, each movie's access units / end, the audio figures
# during the movies (AUDIO_RATE: silent blocks, holes on the movie's port) and bad lines; watches the
# window title (frame counter unchanged 10 s = frozen: the game is then LEFT RUNNING, freeze rule).
param([hashtable]$Env = @{}, [int]$Timeout = 240, [string]$Out = 'E:\ms_perf\video\intro', [switch]$KeepRunning)
$ErrorActionPreference = 'Stop'
$port = Join-Path $PSScriptRoot '..\port'
$log = Join-Path $port 'run.log'
New-Item -ItemType Directory -Force $Out | Out-Null
Get-Process MotorStormApocalypse -ErrorAction SilentlyContinue | Stop-Process -Confirm:$false
Start-Sleep 3
if (Test-Path $log) { Move-Item $log (Join-Path $port 'run.prev.log') -Force }
$set = @{ PORT_PLAY_VIDEOS = '1'; AUDIO_RATE = '1'; PORT_GAME_LOG = 'Switching Screen' }
foreach ($k in $Env.Keys) { $set[$k] = "$($Env[$k])" }
foreach ($k in $set.Keys) { Set-Item "Env:$k" $set[$k] }
Start-Process -FilePath cmd.exe -ArgumentList '/c', (Join-Path $port 'run.bat') -WindowStyle Minimized
foreach ($k in $set.Keys) { Remove-Item "Env:$k" }
$t0 = Get-Date; $res = 'timeout'; $lastF = ''; $lastChange = Get-Date
while (((Get-Date) - $t0).TotalSeconds -lt $Timeout) {
    Start-Sleep -Milliseconds 1000
    $gp = Get-Process MotorStormApocalypse -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
    if ($gp) {
        $gp.Refresh()
        if ($gp.MainWindowTitle -match '\| f (\d+)') {
            if ($Matches[1] -ne $lastF) { $lastF = $Matches[1]; $lastChange = Get-Date }
            elseif (((Get-Date) - $lastChange).TotalSeconds -ge 10) { $res = 'FROZEN'; break }
        }
    } elseif (((Get-Date) - $t0).TotalSeconds -gt 20) { $res = 'NO PROCESS'; break }
    $txt = Get-Content $log -Raw -ErrorAction SilentlyContinue
    if ($txt -and $txt -match 'Switching Screen "[^"]*" to "TitleScreen"') { $res = 'TITLE'; break }
}
$secs = [int]((Get-Date) - $t0).TotalSeconds
$stamp = Get-Date -Format 'HHmmss'
Copy-Item $log (Join-Path $Out "intro_$stamp.log") -Force
$lines = Get-Content $log
$seq = ($lines | Select-String -Pattern 'Switching Screen "[^"]*" to "([^"]*)"' | ForEach-Object { $_.Matches[0].Groups[1].Value }) -join ' > '
Write-Host ("{0} after {1} s   screens: {2}" -f $res, $secs, $seq)
Write-Host ("video AUs: {0}   audio AUs: {1}   EndSeq (vdec): {2}   SEMA gave up: {3}   idle drains: {4}" -f `
    @($lines | Select-String -SimpleMatch '[cellVdec] DecodeAu').Count, @($lines | Select-String -SimpleMatch '[cellAdec] DecodeAu').Count, `
    @($lines | Select-String -SimpleMatch '[cellVdec] EndSeq').Count, @($lines | Select-String -Pattern '\[SEMA\].*gave up').Count, `
    @($lines | Select-String -SimpleMatch 'idle').Count)
$i = ($lines | Select-String -SimpleMatch '[cellAdec] Open' | Select-Object -First 1).LineNumber
if ($i) { $lines[$i..($lines.Count - 1)] | Select-String -SimpleMatch 'audio-rate' | ForEach-Object { Write-Host ('  ' + $_.Line) } }
$lines | Select-String -Pattern 'BAD READ|HOTREAD|null-read|FATAL|did not decode|dropping|queue full' | Select-Object -First 8 | ForEach-Object { Write-Host ('  ! ' + $_.Line) }
if ($res -ne 'FROZEN' -and -not $KeepRunning) { Get-Process MotorStormApocalypse -ErrorAction SilentlyContinue | Stop-Process -Confirm:$false }
elseif ($res -eq 'FROZEN') { Write-Host 'game left running for inspection' }
