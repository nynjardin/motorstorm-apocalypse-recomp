# Put the port in the game folder ("portable" layout: port\portable.cpp, docs\lanceur.md):
#   <game>\MotorStormApocalypse.exe, <game>\Lanceur.exe      at the root, beside PS3_GAME
#   <game>\recomp\                                           everything else (see below)
#   scripts\deploy_game.ps1 [-GameDir <root>] [-Exe <game exe>] [-Launcher <Lanceur.exe>] [-NoData]
# The dump itself (PS3_GAME, PS3_DISC.SFB) is never touched and nothing is ever deleted.
#   - our build outputs are replaced by the current ones: the two exes, the three Visual C++ runtime
#     DLLs beside them (msvcp140, vcruntime140, vcruntime140_1), recomp\psarc_patches.bin,
#     recomp\libsre_image.bin, recomp\EBOOT.elf (the decrypted EBOOT of game\BCES00484);
#   - what belongs to the player is copied ONLY WHEN ABSENT, from where port\run.bat keeps it:
#     recomp\save (port\gamedata), recomp\dev_hdd0 and dev_hdd1 (the title's HDD cache, 1.2 GB:
#     without the copy the first boot rebuilds it), recomp\shader_cache, recomp\dev_flash
#     (firmware files of the RPCS3 install). -NoData skips this second group.
# The folder then runs from anywhere (every path is relative to the exe): copy it whole to
# another PC. NOT to be published: the game exe is the game's own code recompiled, EBOOT.elf,
# dev_flash and libsre_image.bin come from the disc and the firmware.
param(
    [string]$GameDir = 'F:\Jeux\PS3\MotorStorm - Apocalypse (Europe) (En,Fr,De,Es,It,Nl,Pt,Sv,No,Da,Fi,Ko,Pl,Ru) (v02.00)',
    [string]$Exe = '',
    [string]$Launcher = 'E:\ms_perf\launcher_target\release\Lanceur.exe',
    [switch]$NoData
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
if (-not $Exe) { $Exe = Join-Path $repo 'port\build\MotorStormApocalypse.exe' }
if (-not (Test-Path -LiteralPath (Join-Path $GameDir 'PS3_GAME\USRDIR\ms3.psarc'))) { throw "not a MotorStorm: Apocalypse folder: $GameDir" }
if (Get-Process MotorStormApocalypse, Lanceur -ErrorAction SilentlyContinue) { throw 'the game or the launcher is running: close them first' }
$data = Join-Path $GameDir 'recomp'
New-Item -ItemType Directory -Force -Path $data | Out-Null

function Put([string]$from, [string]$to) {             # our outputs: replaced
    if (-not (Test-Path -LiteralPath $from)) { Write-Host "  missing, skipped: $from"; return }
    Copy-Item -LiteralPath $from -Destination $to -Force
    Write-Host ("  {0}  ({1:N1} MB)" -f $to.Substring($GameDir.Length + 1), ((Get-Item -LiteralPath $to).Length / 1MB))
}
function Seed([string]$from, [string]$to) {            # the player's: only when absent
    $name = $to.Substring($GameDir.Length + 1)
    if (Test-Path -LiteralPath $to) { Write-Host "  kept as it is: $name"; return }
    if (-not (Test-Path -LiteralPath $from)) { Write-Host "  no source, the game will create it: $name"; return }
    robocopy $from $to /E /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy $from -> $to failed ($LASTEXITCODE)" }
    $m = Get-ChildItem -LiteralPath $to -Recurse -File | Measure-Object Length -Sum
    Write-Host ("  {0}  ({1} files, {2:N0} MB)" -f $name, $m.Count, ($m.Sum / 1MB))
}

Write-Host "game folder: $GameDir"
Put $Exe (Join-Path $GameDir 'MotorStormApocalypse.exe')
Put $Launcher (Join-Path $GameDir 'Lanceur.exe')
# The Visual C++ runtime the game exe imports, beside it: the folder then starts on a PC that has no
# "Visual C++ Redistributable 2015-2022 x64". Taken from System32, the version this PC runs the
# build with: a copy beside the exe wins over the system one, so it must never be OLDER than the
# toolset that built the exe (the Redist folders of Visual Studio here are older than System32).
foreach ($dll in 'msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll') {
    Put (Join-Path $env:SystemRoot "System32\$dll") (Join-Path $GameDir $dll)
}
Put (Join-Path $repo 'game\BCES00484\EBOOT.elf') (Join-Path $data 'EBOOT.elf')
Put (Join-Path $repo 'port\psarc_patches.bin') (Join-Path $data 'psarc_patches.bin')
Put (Join-Path $repo 'work\firmware\libsre\libsre_image.bin') (Join-Path $data 'libsre_image.bin')
if (-not $NoData) {
    Seed (Join-Path $repo 'port\gamedata') (Join-Path $data 'save')
    Seed 'F:\Jeux\PS3\_recomp\BCES00484\dev_hdd0' (Join-Path $data 'dev_hdd0')
    Seed 'F:\Jeux\PS3\_recomp\BCES00484\dev_hdd1' (Join-Path $data 'dev_hdd1')
    Seed 'F:\Jeux\PS3\_recomp\BCES00484\shader_cache' (Join-Path $data 'shader_cache')
    Seed (Join-Path (Split-Path $repo -Parent) 'tools\rpcs3\dev_flash') (Join-Path $data 'dev_flash')
}
$readme = @(
    'MotorStorm: Apocalypse, version PC (recompilation statique)',
    '',
    'Lancer : Lanceur.exe (pseudo, reseau local, reglages), ou MotorStormApocalypse.exe directement.',
    'Les deux doivent rester a la racine du dossier du jeu, a cote de PS3_GAME, avec msvcp140.dll,',
    'vcruntime140.dll et vcruntime140_1.dll (le runtime Visual C++ dont le jeu a besoin).',
    '',
    'Ce dossier recomp contient tout ce que le portage ajoute au jeu ; le disque (PS3_GAME) n''est jamais modifie.',
    '  save\                 la sauvegarde du jeu',
    '  dev_hdd0\, dev_hdd1\   le cache que le jeu construit a son premier lancement (peut etre supprime : il le refait)',
    '  shader_cache\         shaders deja compiles (idem)',
    '  run.log               ce que le jeu a ecrit a son dernier lancement (run.prev.log : celui d''avant)',
    '  lanceur.json, settings.ini   les reglages choisis dans le lanceur',
    '  EBOOT.elf             l''executable du jeu dechiffre (rpcs3.exe --decrypt PS3_GAME\USRDIR\EBOOT.BIN)',
    '  dev_flash\, libsre_image.bin   fichiers du firmware de la PS3',
    '  psarc_patches.bin     menus du jeu modifies a la lecture (parties LAN, resultats)',
    '',
    'Tout est en chemins relatifs : le dossier du jeu peut etre deplace ou copie tel quel sur un autre PC.',
    'A ne pas diffuser : MotorStormApocalypse.exe (le code du jeu recompile), EBOOT.elf, dev_flash, libsre_image.bin.'
)
Set-Content -LiteralPath (Join-Path $data 'LISEZ-MOI.txt') -Value $readme -Encoding ASCII
Write-Host '  recomp\LISEZ-MOI.txt'
Write-Host 'done: start Lanceur.exe in the game folder.'
exit 0      # robocopy leaves 1 ("files copied") in $LASTEXITCODE
