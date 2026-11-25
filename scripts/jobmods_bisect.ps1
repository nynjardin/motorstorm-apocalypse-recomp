# Which lifted WWS job modules (PORT_JOBMODS, ids 200-238) stop the boot before the title screen?
# For each given range, runs the port with only that range lifted (PORT_JOBMODS_RANGE, plus
# PORT_JOBMODS_EXCLUDE if given) and reports PASS if the title screen is reached in time.
#   scripts\jobmods_bisect.ps1 -Ranges '200-210','211-220' [-Exclude '221,234'] [-Timeout 220]
# Title detection: the port logs the (skipped) "maintitles" video right before the title screen.
param([string[]]$Ranges, [string]$Exclude = '', [int]$Timeout = 220)
$port = Join-Path $PSScriptRoot '..\port'
$log = Join-Path $port 'run.log'
foreach ($r in $Ranges) {
    Get-Process MotorStormApocalypse -ErrorAction SilentlyContinue | Stop-Process -Confirm:$false
    Start-Sleep 3
    Remove-Item $log -ErrorAction SilentlyContinue   # a stale log would match the title at once
    $env:PORT_JOBMODS = '1'; $env:PORT_JOBMODS_RANGE = $r
    if ($Exclude) { $env:PORT_JOBMODS_EXCLUDE = $Exclude } else { Remove-Item env:PORT_JOBMODS_EXCLUDE -ErrorAction SilentlyContinue }
    Start-Process -FilePath cmd.exe -ArgumentList '/c', (Join-Path $port 'run.bat') -WindowStyle Minimized
    Start-Sleep 8
    $t0 = Get-Date; $res = 'FAIL'
    while (((Get-Date) - $t0).TotalSeconds -lt $Timeout) {
        if ((Test-Path $log) -and (Select-String -Path $log -Pattern 'maintitles' -Quiet)) { $res = 'PASS'; break }
        if (-not (Get-Process MotorStormApocalypse -ErrorAction SilentlyContinue)) { $res = 'EXIT'; break }
        Start-Sleep 3
    }
    "{0} range={1} exclude={2} ({3:N0}s)" -f $res, $r, $Exclude, ((Get-Date) - $t0).TotalSeconds
}
Get-Process MotorStormApocalypse -ErrorAction SilentlyContinue | Stop-Process -Confirm:$false
