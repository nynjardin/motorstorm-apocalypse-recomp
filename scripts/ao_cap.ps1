# ao_cap.ps1 -Out <dir> [-Res 1920x1080] [-Track pont] [-Wait 14] [-Env @{..}] [-Stops <fp>,<fp>,...]
# The ambient occlusion chain of the race, stage by stage (toolkit patch #64).
# Runs res_shot.ps1 (-Keep: presentation capture, X, 14 s, race capture, all with the alpha
# planes: RSX_CAP_ALPHA=1), then one more capture per -Stops entry with the frame stopped after
# the LAST op of that fragment program (gate "fp=<hex>"), then stops the game.
# Default stops on the bridge track:
#   0034EE41 = end of the half-size upsample   (rt_03150000_640x540: R = occlusion, A = edges)
#   0034FFC1 = end of the full-size upsample   (rt_01AB0000_a.bmp = occlusion as the scene reads it)
# The quarter-size result (rt_03150000_320x270: G, and _a) survives to the end of any frame.
# Then: scripts\ao_sheet.py <Out> makes one contact sheet of the stages.
param(
    [Parameter(Mandatory)][string]$Out,
    [string]$Res = '1920x1080',
    [string]$Track = 'pont',
    [hashtable]$Env = @{},
    [int]$Wait = 14,          # seconds between the X that starts the race and the race capture (4 = the pack is still close)
    [string[]]$Stops = @('0034EE41', '0034FFC1')
)
$ErrorActionPreference = 'Stop'
$e = @{ RSX_CAP_ALPHA = '1' }
foreach ($k in $Env.Keys) { $e[$k] = $Env[$k] }
& (Join-Path $PSScriptRoot 'res_shot.ps1') -Res $Res -Out $Out -Track $Track -Wait $Wait -Keep -Env $e
$gate = Join-Path $Out 'gate.txt'
$cap = Join-Path $Out 'cap'
foreach ($fp in $Stops) {
    $before = @(Get-ChildItem $cap -Directory -ErrorAction SilentlyContinue | ForEach-Object Name)
    Set-Content -Path $gate -Value "fp=$fp" -NoNewline
    $new = $null; $t0 = Get-Date
    while (-not $new -and ((Get-Date) - $t0).TotalSeconds -lt 30) {
        Start-Sleep -Milliseconds 700
        $new = Get-ChildItem $cap -Directory -ErrorAction SilentlyContinue | Where-Object { $before -notcontains $_.Name } | Select-Object -First 1
    }
    if ($new) { Start-Sleep 6; Rename-Item $new.FullName ("stop_$fp"); Write-Host "stop after fp=$fp -> stop_$fp" }
    else { Write-Host "stop after fp=$fp : no capture" }
}
Copy-Item (Join-Path $PSScriptRoot '..\port\run.log') (Join-Path $Out 'run.log') -ErrorAction SilentlyContinue
Get-Process MotorStormApocalypse -ErrorAction SilentlyContinue | Stop-Process -Confirm:$false
Write-Host 'game stopped'
