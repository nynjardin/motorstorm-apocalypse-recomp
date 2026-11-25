# Catch the intermittent title/menu freeze (WWS job manager re-reading one job list forever).
# Launches the port again and again up to the main menu with PORT_WATCH (guest threads' state
# every few seconds); a try is a freeze when the window title (FPS | draws) stops changing for
# -StuckSeconds. On a freeze the game is LEFT RUNNING (guest_peek.py can read it) and the log is
# copied to -OutDir. Otherwise the game is stopped and the next try starts.
#   scripts\catch_freeze.ps1 [-Tries 12] [-Env @{SPU_HIST='10'}] [-OutDir E:\ms_perf\freeze]
param(
    [int]$Tries = 12,
    [hashtable]$Env = @{},
    [string]$OutDir = 'E:\ms_perf\freeze',
    [int]$MenuSeconds = 45,
    [int]$StuckSeconds = 10
)
$ErrorActionPreference = 'Stop'
$port = Join-Path $PSScriptRoot '..\port'
$log = Join-Path $port 'run.log'
$pad = Join-Path $env:TEMP 'motorstorm_pad.txt'
New-Item -ItemType Directory -Force $OutDir | Out-Null
function Get-Title {
    $p = Get-Process MotorStormApocalypse -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
    if ($p) { $p.Refresh(); return $p.MainWindowTitle }
    return $null
}
function Write-Pad([string]$v) {
    for ($try = 0; ; $try++) {
        try { Set-Content -Path $pad -Value $v -NoNewline -ErrorAction Stop; break }
        catch { if ($try -ge 50) { throw }; Start-Sleep -Milliseconds 20 }
    }
}
# Title unchanged for $StuckSeconds = frozen (it is rewritten every second with a fresh FPS value;
# two equal readings happen, a dozen in a row do not).
function Test-Stuck([int]$watch, [switch]$Wander) {
    $last = Get-Title; $same = 0
    for ($i = 0; $i -lt $watch; $i++) {
        # -Wander: move in the menu while watching (DOWN / UP alternately every 3 s); tonight's
        # freezes (2026-11-21) all came during menu navigation, not on an idle menu.
        if ($Wander -and $i % 3 -eq 0) { Write-Pad $(if (($i / 3) % 2) { '0x0010 4' } else { '0x0040 4' }) }
        Start-Sleep 1
        $t = Get-Title
        if (-not $t) { return $false }
        if ($t -eq $last) { $same++ } else { $same = 0; $last = $t }
        if ($same -ge $StuckSeconds) { return $true }
    }
    return $false
}
$env:PAD_FILE = $pad
$env:PORT_WATCH = '5'
foreach ($k in $Env.Keys) { Set-Item -Path "env:$k" -Value $Env[$k] }
for ($n = 1; $n -le $Tries; $n++) {
    Get-Process MotorStormApocalypse -ErrorAction SilentlyContinue | Stop-Process -Confirm:$false
    Start-Sleep 4
    Write-Pad ''
    Remove-Item $log -ErrorAction SilentlyContinue
    Start-Process -FilePath cmd.exe -ArgumentList '/c', (Join-Path $port 'run.bat') -WindowStyle Minimized
    $t0 = Get-Date
    while (-not (Test-Path $log) -or -not (Select-String -Path $log -Pattern 'maintitles' -Quiet)) {
        if (((Get-Date) - $t0).TotalSeconds -gt 200) { break }
        Start-Sleep 2
    }
    $frozen = Test-Stuck 22          # title screen appears, city loads behind the logo
    if (-not $frozen) {
        Write-Pad '0x4000 8'         # X: title -> main menu
        $frozen = Test-Stuck $MenuSeconds -Wander
    }
    if ($frozen) {
        Start-Sleep 8                # a few more PORT_WATCH reports of the frozen state
        $dst = Join-Path $OutDir ("freeze_try{0}_{1}.log" -f $n, (Get-Date -Format 'HHmmss'))
        Copy-Item $log $dst
        Write-Host "FROZEN on try $n after $([int]((Get-Date) - $t0).TotalSeconds)s -> $dst (game left running)"
        exit 0
    }
    Write-Host "try ${n}: no freeze"
}
Get-Process MotorStormApocalypse -ErrorAction SilentlyContinue | Stop-Process -Confirm:$false
Write-Host "no freeze in $Tries tries"
exit 1
