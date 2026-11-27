# video_stall_try.ps1 [-Tries 10] [-Env @{VDEC_TRACE='1'}] [-KeepOnStall] [-Timeout 60]
# The first real movie (evologo) stalls on some runs (docs\hle.md "Real movies"). Launches the game with
# PORT_PLAY_VIDEOS=1 up to -Tries times and classifies each run from port\run.log, WITHOUT PORT_GAME_LOG
# (it changes the timing): PASS = "[cellVdec] EndSeq" seen (the first movie ended), STALL = "[SEMA] ...
# gave up" lines before it. With -KeepOnStall the first stalled game is LEFT RUNNING for inspection
# (crash-triage skill) and the script stops. Logs are copied to -Out as try_<n>.log.
param(
    [int]$Tries = 10,
    [hashtable]$Env = @{},
    [switch]$KeepOnStall,
    [int]$Timeout = 60,
    [string]$Out = 'E:\ms_perf\video\stall'
)
$ErrorActionPreference = 'Stop'
$port = Join-Path $PSScriptRoot '..\port'
$log = Join-Path $port 'run.log'
New-Item -ItemType Directory -Force $Out | Out-Null
$pass = 0; $stall = 0; $other = 0
for ($i = 1; $i -le $Tries; $i++) {
    Get-Process MotorStormApocalypse -ErrorAction SilentlyContinue | Stop-Process -Confirm:$false
    Start-Sleep 3
    if (Test-Path $log) { Move-Item $log (Join-Path $port 'run.prev.log') -Force }
    $env:PORT_PLAY_VIDEOS = '1'
    foreach ($k in $Env.Keys) { Set-Item "Env:$k" "$($Env[$k])" }
    Start-Process -FilePath cmd.exe -ArgumentList '/c', (Join-Path $port 'run.bat') -WindowStyle Minimized
    Remove-Item Env:PORT_PLAY_VIDEOS
    foreach ($k in $Env.Keys) { Remove-Item "Env:$k" }
    $t0 = Get-Date; $res = 'timeout'
    while (((Get-Date) - $t0).TotalSeconds -lt $Timeout) {
        Start-Sleep -Milliseconds 500
        if (-not (Test-Path $log)) { continue }
        $txt = Get-Content $log -Raw -ErrorAction SilentlyContinue
        if (-not $txt) { continue }
        if ($txt -match '\[cellVdec\] EndSeq') { $res = 'PASS'; break }
        if (([regex]::Matches($txt, '\[SEMA\][^\n]*gave up')).Count -ge 8) { $res = 'STALL'; break }
    }
    $secs = [int]((Get-Date) - $t0).TotalSeconds
    Copy-Item $log (Join-Path $Out ("try_{0}.log" -f $i)) -Force
    $gp = Get-Process MotorStormApocalypse -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
    $title = if ($gp) { $gp.Refresh(); $gp.MainWindowTitle } else { 'NO PROCESS' }
    Write-Host ("try {0}: {1} after {2} s   {3}" -f $i, $res, $secs, $title)
    switch ($res) { 'PASS' { $pass++ } 'STALL' { $stall++ } default { $other++ } }
    if ($res -ne 'PASS' -and $KeepOnStall) { Write-Host "game left running (pid $($gp.Id))"; break }
}
if (-not ($KeepOnStall -and $res -ne 'PASS')) { Get-Process MotorStormApocalypse -ErrorAction SilentlyContinue | Stop-Process -Confirm:$false }
Write-Host ("PASS {0}  STALL {1}  other {2}" -f $pass, $stall, $other)
