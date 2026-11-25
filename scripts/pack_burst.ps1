# Window burst at a race START, the bike leaving with the pack (R2 held from the X that skips the
# presentation): the only scripted moment with the other vehicles close on screen. For defects of
# the OTHER vehicles / dynamic props (parts popping or blinking) that the lone scripted bike of
# race_perf.ps1 never shows. True consecutive frames (grab_burst.py, ~9 a second, window in front).
#   scripts\pack_burst.ps1 -Label base [-Track quai] [-Env @{GEO_CACHE='0'}] [-Grabs 150] [-Delay 6]
# Results: E:\ms_perf\packburst_<label>\ (b000.png ..., report.txt, run.log). Game stopped at the end.
param(
    [string]$Label = 'base',
    [string]$Track = 'quai',
    [hashtable]$Env = @{},
    [int]$Grabs = 150,
    [int]$Delay = 6          # seconds between X and the first grab
)
$ErrorActionPreference = 'Stop'
$port = Join-Path $PSScriptRoot '..\port'
$pad = Join-Path $env:TEMP 'motorstorm_pad.txt'
$dir = "E:\ms_perf\packburst_$Label"
New-Item -ItemType Directory -Force $dir | Out-Null
function Write-Pad([string]$v) {
    for ($try = 0; ; $try++) {
        try { Set-Content -Path $pad -Value $v -NoNewline -ErrorAction Stop; break }
        catch { if ($try -ge 50) { throw }; Start-Sleep -Milliseconds 20 }
    }
}
function Get-Draws {
    $p = Get-Process MotorStormApocalypse -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
    if ($p) { $p.Refresh(); if ($p.MainWindowTitle -match 'draws: ([0-9]+)') { return [int]$Matches[1] } }
    return -1
}
& (Join-Path $PSScriptRoot 'goto_race.ps1') -Track $Track -Env $Env -AfterSeconds 5
$t0 = Get-Date; $hits = 0
while ($hits -lt 3) {      # race presentation: many draws a few seconds in a row
    if (-not (Get-Process MotorStormApocalypse -ErrorAction SilentlyContinue)) { throw 'game exited during loading' }
    if (((Get-Date) - $t0).TotalSeconds -gt 400) { throw 'race presentation not reached' }
    Start-Sleep 2
    if ((Get-Draws) -gt 500) { $hits++ } else { $hits = 0 }
}
Start-Sleep 3
Write-Pad '0x4000 10'       # X: start
Start-Sleep 2
Write-Pad '0x0200 3000'     # R2 held
Start-Sleep ([math]::Max(0, $Delay - 2))
python (Join-Path $PSScriptRoot 'grab_burst.py') $dir --n $Grabs 2>&1 | Set-Content (Join-Path $dir 'report.txt')
Write-Pad ''
Get-Process MotorStormApocalypse -ErrorAction SilentlyContinue | Stop-Process -Confirm:$false
Start-Sleep 3
Copy-Item (Join-Path $port 'run.log') (Join-Path $dir 'run.log') -Force
Get-Content (Join-Path $dir 'report.txt') | Select-Object -First 3 | Write-Host
Write-Host "[pack_burst] $dir"
