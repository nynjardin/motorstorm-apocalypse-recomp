# vfs_link_copy.ps1 [-Out E:\ms_perf\video\vfs_test] [-Video E:\ms_perf\video\conv] [-Source <game folder>]
# A "copy" of the game made of LINKS, without its ui\video folder (16 GB) and with the re-encoded
# movies as recomp\video: what a slim test copy looks like to the port, built in a second and using no
# disk space. Nothing is written in the source folder. Then:
#   $env:PS3_VFS_ROOT = '<Out>'; port\run.bat        (run.bat keeps a PS3_VFS_ROOT set before the call)
# Directory symbolic links and file symbolic links: needs Windows developer mode or an elevated shell.
param(
    [string]$Out = 'E:\ms_perf\video\vfs_test',
    [string]$Video = 'E:\ms_perf\video\conv',
    [string]$Source = 'F:\Jeux\PS3\MotorStorm - Apocalypse (Europe) (En,Fr,De,Es,It,Nl,Pt,Sv,No,Da,Fi,Ko,Pl,Ru) (v02.00)'
)
$ErrorActionPreference = 'Stop'
function Link-Children([string]$from, [string]$to, [string[]]$skip) {
    New-Item -ItemType Directory -Force $to | Out-Null
    foreach ($c in Get-ChildItem -LiteralPath $from -Force) {
        if ($skip -contains $c.Name) { continue }
        $dst = Join-Path $to $c.Name
        if (Test-Path -LiteralPath $dst) { continue }
        New-Item -ItemType SymbolicLink -Path $dst -Target $c.FullName | Out-Null
    }
}
# real directories along the path to ui\video, links for everything else
Link-Children (Join-Path $Source 'PS3_GAME') (Join-Path $Out 'PS3_GAME') @('USRDIR')
Link-Children (Join-Path $Source 'PS3_GAME\USRDIR') (Join-Path $Out 'PS3_GAME\USRDIR') @('ui')
Link-Children (Join-Path $Source 'PS3_GAME\USRDIR\ui') (Join-Path $Out 'PS3_GAME\USRDIR\ui') @('video')
$sfb = Join-Path $Out 'PS3_DISC.SFB'
if (-not (Test-Path $sfb)) { New-Item -ItemType SymbolicLink -Path $sfb -Target (Join-Path $Source 'PS3_DISC.SFB') | Out-Null }
New-Item -ItemType Directory -Force (Join-Path $Out 'recomp') | Out-Null
$rv = Join-Path $Out 'recomp\video'
if (-not (Test-Path $rv)) { New-Item -ItemType SymbolicLink -Path $rv -Target $Video | Out-Null }
Write-Host "link copy in $Out (no ui\video; recomp\video -> $Video)"
Get-ChildItem -Recurse -Depth 3 $Out | Select-Object -First 30 | ForEach-Object { '  ' + $_.FullName.Substring($Out.Length) + $(if ($_.LinkType) { '  -> link' } else { '' }) }
