# Blink measure at a race START, the bike leaving with the pack (R2 held from the X that skips the
# presentation), from the guest draws recorded by DRAW_SIG (toolkit patch #47): how often the title
# stops submitting an object for 1-4 frames. No screen grabs (they cost FPS): for pictures of the
# same moment use pack_burst.ps1.
#   scripts\pack_sig.ps1 -Label base [-Track quai|pont] [-Env @{GEO_CACHE='0'}] [-Seconds 25]
# Results: E:\ms_perf\packsig\<label>.bin, <label>.txt (drawsig_blink.py on the race part only),
# <label>.log (run.log). Game stopped at the end.
param(
    [string]$Label = 'base',
    [string]$Track = 'quai',
    [hashtable]$Env = @{},
    [int]$Seconds = 25,          # race seconds recorded after the X
    [string[]]$BlinkArgs = @()   # extra arguments for drawsig_blink.py
)
$ErrorActionPreference = 'Stop'
$port = Join-Path $PSScriptRoot '..\port'
$pad = Join-Path $env:TEMP 'motorstorm_pad.txt'
$dir = 'E:\ms_perf\packsig'
New-Item -ItemType Directory -Force $dir | Out-Null
$bin = Join-Path $dir "$Label.bin"
function Write-Pad([string]$v) {
    for ($try = 0; ; $try++) {
        try { Set-Content -Path $pad -Value $v -NoNewline -ErrorAction Stop; break }
        catch { if ($try -ge 50) { throw }; Start-Sleep -Milliseconds 20 }
    }
}
function Get-Title {
    $p = Get-Process MotorStormApocalypse -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
    if ($p) { $p.Refresh(); return $p.MainWindowTitle }
    return ''
}
$e = @{} + $Env
$e['DRAW_SIG'] = $bin
& (Join-Path $PSScriptRoot 'goto_race.ps1') -Track $Track -Env $e -AfterSeconds 5 | Out-Null
$t0 = Get-Date; $hits = 0
while ($hits -lt 3) {      # race presentation: many draws a few seconds in a row
    if (-not (Get-Process MotorStormApocalypse -ErrorAction SilentlyContinue)) { throw 'game exited during loading' }
    if (((Get-Date) - $t0).TotalSeconds -gt 400) { throw 'race presentation not reached' }
    Start-Sleep 2
    if ((Get-Title) -match 'draws: ([0-9]+)' -and [int]$Matches[1] -gt 500) { $hits++ } else { $hits = 0 }
}
Start-Sleep 3
Write-Pad '0x4000 10'       # X: start
$tick = [Environment]::TickCount64
Start-Sleep 2
Write-Pad '0x0200 3000'     # R2 held
# Freeze rule: the title ends with the frame counter, so an unchanged title = no frame presented.
$last = ''; $same = 0; $fps = @()
for ($s = 2; $s -lt $Seconds; $s++) {
    Start-Sleep 1
    $t = Get-Title
    if ($t -eq $last) { $same++ } else { $same = 0; $last = $t }
    if ($same -ge 10) { throw "FROZEN (title unchanged for 10 s): $t ; game left running" }
    if ($t -match 'FPS: ([0-9.]+)') { $fps += [double]$Matches[1] }
}
Write-Pad ''
Get-Process MotorStormApocalypse -ErrorAction SilentlyContinue | Stop-Process -Confirm:$false
Start-Sleep 3
Copy-Item (Join-Path $port 'run.log') (Join-Path $dir "$Label.log") -Force
$out = python (Join-Path $PSScriptRoot 'drawsig_blink.py') $bin --from-tick ($tick + 1000) @BlinkArgs 2>&1
$out | Set-Content (Join-Path $dir "$Label.txt")
Write-Host ("[pack_sig] {0} ({1}) title FPS median {2}" -f $Label, $Track, (($fps | Sort-Object)[[int]($fps.Count / 2)]))
$out | Select-Object -First 5 | Write-Host
