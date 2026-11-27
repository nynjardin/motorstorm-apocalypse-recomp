# slim_copy.ps1 -Out <new folder> [-GameDir <game folder>] [-Video E:\ms_perf\video\conv] [-WhatIf]
# A copy of the game folder for tests on another PC, without the 16 GB of PS3_GAME\USRDIR\ui\video:
# everything else is copied as it is (exes, DLLs, PS3_GAME, recomp\), and the re-encoded movies
# (scripts\video_convert.py, H.264, 2.6 GB for the 56 "_60" movies) go to <Out>\recomp\video, where the
# port looks for them (docs\hle.md "Re-encoded movies"). About 7.5 GB instead of ~21.
# The game folder must hold the CURRENT exe first (scripts\deploy_game.ps1): only an exe of
# 2026-11-27 or later plays recomp\video. Nothing is written or deleted in the source folder; -Out must
# not exist yet. Not copied: ui\video, *.zip at the root (the archive of the dump), recomp\run.log.
# -WhatIf lists the sizes and stops.
param(
    [Parameter(Mandatory = $true)][string]$Out,
    [string]$GameDir = 'F:\Jeux\PS3\MotorStorm - Apocalypse (Europe) (En,Fr,De,Es,It,Nl,Pt,Sv,No,Da,Fi,Ko,Pl,Ru) (v02.00)',
    [string]$Video = 'E:\ms_perf\video\conv',
    [switch]$WhatIf
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath (Join-Path $GameDir 'PS3_GAME\USRDIR\ms3.psarc'))) { throw "not a MotorStorm: Apocalypse folder: $GameDir" }
$movies = @(Get-ChildItem -LiteralPath $Video -Filter '*_60.avi' -File)
if ($movies.Count -lt 56) { throw "$Video holds $($movies.Count) converted movies, 56 expected: run scripts\video_convert.py first" }
if (Test-Path -LiteralPath $Out) { throw "$Out exists already" }
$skipDir = Join-Path $GameDir 'PS3_GAME\USRDIR\ui\video'
$files = Get-ChildItem -LiteralPath $GameDir -Recurse -File -Force | Where-Object {
    -not $_.FullName.StartsWith($skipDir, [StringComparison]::OrdinalIgnoreCase) -and
    -not ($_.DirectoryName -eq $GameDir -and $_.Extension -eq '.zip') -and
    -not $_.FullName.StartsWith((Join-Path $GameDir 'recomp\video'), [StringComparison]::OrdinalIgnoreCase) -and
    $_.Name -ne 'run.log' }
$gb = ($files | Measure-Object Length -Sum).Sum / 1GB
$vgb = ($movies | Measure-Object Length -Sum).Sum / 1GB
Write-Host ("game without ui\video: {0:N2} GB in {1} files; movies: {2:N2} GB; total {3:N2} GB -> {4}" -f $gb, $files.Count, $vgb, ($gb + $vgb), $Out)
$drive = (Split-Path -Qualifier ([IO.Path]::GetFullPath($Out))).TrimEnd(':')
$free = (Get-PSDrive $drive).Free / 1GB
if ($free -lt $gb + $vgb + 1) { throw ("only {0:N1} GB free on {1}:" -f $free, $drive) }
if ($WhatIf) { return }
foreach ($f in $files) {
    $dst = Join-Path $Out $f.FullName.Substring($GameDir.Length).TrimStart('\')
    New-Item -ItemType Directory -Force (Split-Path $dst -Parent) | Out-Null
    Copy-Item -LiteralPath $f.FullName -Destination $dst
}
$vd = Join-Path $Out 'recomp\video'
New-Item -ItemType Directory -Force $vd | Out-Null
foreach ($m in $movies) { Copy-Item -LiteralPath $m.FullName -Destination (Join-Path $vd $m.Name) }
Write-Host "done: $Out"
