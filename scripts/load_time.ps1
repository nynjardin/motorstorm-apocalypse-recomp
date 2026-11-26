# Race load time: goto_race.ps1 up to the final X, then the seconds until the race scene draws
# (window title "draws: N" > 1500, same test as race_perf.ps1 uses, 4500 there for the start line).
#   scripts\load_time.ps1 [-Env @{LWCOND_WAKE='0'}] [-Track pont] [-Label x]
# Appends "label seconds" to port\load_time.txt. Nothing else should run meanwhile.
param([hashtable]$Env = @{}, [string]$Track = 'pont', [string]$Label = 'run', [int]$Timeout = 400, [int]$Draws = 1500)
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'goto_race.ps1') -Track $Track -Env $Env -AfterSeconds 0 | Out-Null
$t0 = Get-Date
$sec = -1
while (((Get-Date) - $t0).TotalSeconds -lt $Timeout) {
    $gp = Get-Process MotorStormApocalypse -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
    if (-not $gp) { throw 'game exited during the load' }
    $gp.Refresh()
    if ($gp.MainWindowTitle -match 'draws: ([0-9]+)' -and [int]$Matches[1] -gt $Draws) { $sec = ((Get-Date) - $t0).TotalSeconds; break }
    Start-Sleep -Milliseconds 500
}
$line = "{0} {1:N1}" -f $Label, $sec
Add-Content (Join-Path $PSScriptRoot '..\port\load_time.txt') $line
Write-Host "load_time: $line"
