# res_shot.ps1 -Res <W>x<H> -Out <dir> [-Track pont] [-Wait 14] [-Keep] [-Env @{..}]
# The bridge race at a given render resolution (PORT_RES, toolkit patch #63), captured as the
# backend sees it: launches through goto_race.ps1, waits for the race presentation ("DEPART"),
# takes one RSX capture there (pres_*), presses X, waits -Wait seconds, takes a second one
# (race_*), converts the backbuffer and the composed frame (rt_01010000) to PNG in -Out, stops
# the game (-Keep leaves it running). -Res 1280x720 = the reference (no scale).
# The captures themselves (every target, manifest, fps.hlsl) stay in <Out>\cap\frame_NN.
# A screenshot of the WINDOW is not used on purpose: PersistentWindows / FancyZones resize it.
param(
    [Parameter(Mandatory)][string]$Res,
    [Parameter(Mandatory)][string]$Out,
    [string]$Track = 'pont',
    [int]$Wait = 14,
    [switch]$Keep,
    [hashtable]$Env = @{}
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
New-Item -ItemType Directory -Force $Out | Out-Null
$gate = Join-Path $Out 'gate.txt'
$cap = Join-Path $Out 'cap'
Remove-Item $gate -ErrorAction SilentlyContinue
$e = @{ PORT_RES = $Res; RSX_CAP_GATE = $gate; RSX_CAP_DIR = $cap }
foreach ($k in $Env.Keys) { $e[$k] = $Env[$k] }

function Get-Title {
    $p = Get-Process MotorStormApocalypse -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
    if (-not $p) { return $null }
    $p.Refresh(); return $p.MainWindowTitle
}
function Wait-Race([int]$timeout) {
    # race scene (more than 2000 draws) at a steady rate; freeze rule: title unchanged 12 s
    $t0 = Get-Date; $last = ''; $same = 0; $ok = 0
    while (((Get-Date) - $t0).TotalSeconds -lt $timeout) {
        $t = Get-Title
        if (-not $t) { throw 'game exited' }
        if ($t -eq $last) { $same++ } else { $same = 0; $last = $t }
        if ($same -ge 4) { throw "FROZEN (title unchanged 12 s): $t; game left running" }
        if ($t -match 'FPS: ([0-9.]+) \| draws: ([0-9]+)' -and [double]$Matches[1] -gt 20 -and [int]$Matches[2] -gt 2000) { $ok++ } else { $ok = 0 }
        if ($ok -ge 4) { return }
        Start-Sleep 3
    }
    throw 'race scene not reached'
}
function Take-Capture([string]$tag) {
    $before = @(Get-ChildItem $cap -Directory -ErrorAction SilentlyContinue | ForEach-Object Name)
    Set-Content -Path $gate -Value '0' -NoNewline
    $new = $null; $t0 = Get-Date
    while (-not $new -and ((Get-Date) - $t0).TotalSeconds -lt 30) {
        Start-Sleep -Milliseconds 700
        $new = Get-ChildItem $cap -Directory -ErrorAction SilentlyContinue | Where-Object { $before -notcontains $_.Name } | Select-Object -First 1
    }
    if (-not $new) { Write-Host "$tag : no capture"; return }
    Start-Sleep 5   # the BMPs are written one by one
    foreach ($n in 'backbuffer', 'rt_01010000') {
        $f = Join-Path $new.FullName "$n.bmp"
        for ($try = 0; $try -lt 10; $try++) {
            try {
                $b = [System.Drawing.Image]::FromFile($f)
                $b.Save((Join-Path $Out "${tag}_$n.png"), [System.Drawing.Imaging.ImageFormat]::Png)
                Write-Host "$tag $n $($b.Width)x$($b.Height) ($($new.Name))"
                $b.Dispose(); break
            } catch { Start-Sleep 1 }
        }
    }
}

& (Join-Path $PSScriptRoot 'goto_race.ps1') -Track $Track -AfterSeconds 5 -Env $e
Wait-Race 300
Write-Host "presentation: $(Get-Title)"
Take-Capture 'pres'
Set-Content -Path (Join-Path $env:TEMP 'motorstorm_pad.txt') -Value '0x4000 10' -NoNewline
Start-Sleep $Wait
Write-Host "race: $(Get-Title)"
Take-Capture 'race'
Copy-Item (Join-Path $PSScriptRoot '..\port\run.log') (Join-Path $Out 'run.log') -ErrorAction SilentlyContinue
if (-not $Keep) { Get-Process MotorStormApocalypse -ErrorAction SilentlyContinue | Stop-Process -Confirm:$false; Write-Host 'game stopped' }
