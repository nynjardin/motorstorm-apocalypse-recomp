# blend_steps.ps1 -Out <dir> [-Res 1920x1080] [-Track pont] [-Wait 14] [-MaxVerts 64] [-Env @{..}]
# Which small blended draw of the scene pass makes a defect (a dark quad on the road...)?
# Runs res_shot.ps1 -Keep (bike left idle on the start line: a still view), reads the manifest of
# the race capture, lists the blended draws of at most -MaxVerts vertices into 0x01010000 (decals,
# glass, tyre ribbons, blob shadows: a handful a frame), then takes one capture per group with the
# frame STOPPED after it (gate file = op number), plus one stopped just before the first.
# Each stopped capture is cap\step_<NN>_op<N>_<fp>; step_00 = before any of them. The defect
# appears in rt_01010000.bmp of the step that draws it. Op numbers move a little from frame to
# frame: steps.txt says, from the stopped frame's OWN manifest, which candidate ops ran.
param(
    [Parameter(Mandatory)][string]$Out,
    [string]$Res = '1920x1080',
    [string]$Track = 'pont',
    [int]$Wait = 14,
    [int]$MaxVerts = 64,
    [hashtable]$Env = @{}
)
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'res_shot.ps1') -Res $Res -Out $Out -Track $Track -Wait $Wait -Keep -Env $Env
$gate = Join-Path $Out 'gate.txt'
$cap = Join-Path $Out 'cap'

function Get-Candidates([string]$manifest) {
    # blended draws of <= MaxVerts vertices into 0x01010000: op, fp, n
    $r = @()
    foreach ($l in [IO.File]::ReadLines($manifest)) {
        if ($l -match '^op(\d+) DRAW +rt=0x01010000 .* fp=0x([0-9A-F]+) vs=-?\d+ n=(\d+) cmask=\w+ blend=1 ') {
            if ([int]$Matches[3] -le $MaxVerts) { $r += [pscustomobject]@{ Op = [int]$Matches[1]; Fp = $Matches[2]; N = [int]$Matches[3] } }
        }
    }
    return $r
}
function Take-Stop([int]$op, [string]$name) {
    $before = @(Get-ChildItem $cap -Directory | ForEach-Object Name)
    Set-Content -Path $gate -Value "$op" -NoNewline
    $new = $null; $t0 = Get-Date
    while (-not $new -and ((Get-Date) - $t0).TotalSeconds -lt 30) {
        Start-Sleep -Milliseconds 700
        $new = Get-ChildItem $cap -Directory | Where-Object { $before -notcontains $_.Name } | Select-Object -First 1
    }
    if (-not $new) { Write-Host "$name : no capture"; return }
    Start-Sleep 6
    Rename-Item $new.FullName $name
    $ran = @(Get-Candidates (Join-Path $cap "$name\manifest.txt") | Where-Object { $_.Op -le $op } | ForEach-Object { "op$($_.Op):$($_.Fp):n$($_.N)" })
    $line = "$name stop=$op ran: $($ran -join ' ')"
    Write-Host $line; Add-Content (Join-Path $Out 'steps.txt') $line
}

$race = Get-ChildItem $cap -Directory -Filter 'frame_*' | Sort-Object Name | Select-Object -Last 1
$cands = @(Get-Candidates (Join-Path $race.FullName 'manifest.txt'))
Set-Content (Join-Path $Out 'steps.txt') "candidates in $($race.Name): $(($cands | ForEach-Object { "op$($_.Op):$($_.Fp):n$($_.N)" }) -join ' ')"
Write-Host (Get-Content (Join-Path $Out 'steps.txt'))
if ($cands.Count) {
    Take-Stop ($cands[0].Op - 1) 'step_00_before'
    $i = 1
    for ($k = 0; $k -lt $cands.Count; $k++) {
        # last op of a run of the same program
        if ($k + 1 -lt $cands.Count -and $cands[$k + 1].Fp -eq $cands[$k].Fp -and $cands[$k + 1].Op -eq $cands[$k].Op + 1) { continue }
        Take-Stop $cands[$k].Op ('step_{0:d2}_op{1}_{2}' -f $i, $cands[$k].Op, $cands[$k].Fp)
        $i++
    }
}
Copy-Item (Join-Path $PSScriptRoot '..\port\run.log') (Join-Path $Out 'run.log') -ErrorAction SilentlyContinue
Get-Process MotorStormApocalypse -ErrorAction SilentlyContinue | Stop-Process -Confirm:$false
Write-Host 'game stopped'
