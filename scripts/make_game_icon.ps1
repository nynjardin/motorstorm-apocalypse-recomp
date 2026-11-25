# make_game_icon.ps1: the game's own icon (PS3_GAME\ICON0.PNG of the player's dump) as the icon of
# MotorStormApocalypse.exe and Launcher.exe. ICON0.PNG is 320x176 with the emblem in the middle
# and transparent sides: the emblem is cropped to a square around its opaque pixels, then drawn
# at 16 to 256 px (32-bit BMP entries, as launcher\make_icon.ps1: every resource compiler takes them).
#   scripts\make_game_icon.ps1 [-GameDir <dump root>]
# Writes (all ignored by Git: a picture of the disc never enters the public repository):
#   port\game_icon.ico, port\app.rc       the game exe's icon (port\CMakeLists.txt takes app.rc
#                                         when it exists: run port\build.bat configure once)
#   launcher\src-tauri\icons\game.ico     the launcher exe's icon (launcher\src-tauri\build.rs takes
#                                         it instead of icons\icon.ico when it exists)
# Without them both exes build as before (the launcher with its own "MS" icon). The launcher's
# window and page show ICON0.PNG read from the game folder at run time, whatever the build.
param(
    [string]$GameDir = 'F:\Jeux\PS3\MotorStorm - Apocalypse (Europe) (En,Fr,De,Es,It,Nl,Pt,Sv,No,Da,Fi,Ko,Pl,Ru) (v02.00)'
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$repo = Split-Path $PSScriptRoot -Parent
$src = Join-Path $GameDir 'PS3_GAME\ICON0.PNG'
if (-not (Test-Path -LiteralPath $src)) { throw "no ICON0.PNG in $GameDir\PS3_GAME" }
$png = [System.Drawing.Bitmap]::FromFile($src)

# The opaque pixels' box (alpha > 8), then the smallest square around its centre that holds it.
$x0 = $png.Width; $y0 = $png.Height; $x1 = -1; $y1 = -1
for ($y = 0; $y -lt $png.Height; $y++) {
    for ($x = 0; $x -lt $png.Width; $x++) {
        if ($png.GetPixel($x, $y).A -gt 8) {
            if ($x -lt $x0) { $x0 = $x }; if ($x -gt $x1) { $x1 = $x }
            if ($y -lt $y0) { $y0 = $y }; if ($y -gt $y1) { $y1 = $y }
        }
    }
}
if ($x1 -lt 0) { throw "ICON0.PNG is fully transparent" }
$side = [math]::Max($x1 - $x0 + 1, $y1 - $y0 + 1)
$cx = ($x0 + $x1 + 1) / 2.0; $cy = ($y0 + $y1 + 1) / 2.0
$crop = New-Object System.Drawing.RectangleF ([float]($cx - $side / 2.0)), ([float]($cy - $side / 2.0)), ([float]$side), ([float]$side)
"ICON0.PNG $($png.Width)x$($png.Height), emblem x $x0-$x1 y $y0-$y1, square of $side px"

$sizes = 16, 24, 32, 48, 64, 128, 256
$images = foreach ($n in $sizes) {
    $bmp = New-Object System.Drawing.Bitmap $n, $n, ([System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.Clear([System.Drawing.Color]::Transparent)
    $g.InterpolationMode = 'HighQualityBicubic'; $g.PixelOffsetMode = 'HighQuality'; $g.CompositingQuality = 'HighQuality'
    $g.DrawImage($png, (New-Object System.Drawing.RectangleF 0, 0, $n, $n), $crop, [System.Drawing.GraphicsUnit]::Pixel)
    $g.Dispose()
    $ms = New-Object System.IO.MemoryStream
    $bw = New-Object System.IO.BinaryWriter $ms
    $bw.Write([int]40); $bw.Write([int]$n); $bw.Write([int](2 * $n)); $bw.Write([int16]1); $bw.Write([int16]32)
    $bw.Write([int]0); $bw.Write([int]0); $bw.Write([int]0); $bw.Write([int]0); $bw.Write([int]0); $bw.Write([int]0)
    for ($y = $n - 1; $y -ge 0; $y--) { for ($x = 0; $x -lt $n; $x++) { $bw.Write([int]$bmp.GetPixel($x, $y).ToArgb()) } }
    $bw.Write((New-Object byte[] ([int]([math]::Ceiling($n / 32) * 4) * $n)))      # AND mask: all 0, alpha rules
    $bw.Flush(); $bmp.Dispose()
    , $ms.ToArray()
}
$png.Dispose()

function Write-Ico([string]$out) {
    $fs = [System.IO.File]::Create($out)
    $w = New-Object System.IO.BinaryWriter $fs
    $w.Write([int16]0); $w.Write([int16]1); $w.Write([int16]$sizes.Count)
    $offset = 6 + 16 * $sizes.Count
    for ($i = 0; $i -lt $sizes.Count; $i++) {
        $n = $sizes[$i]
        $w.Write([byte]($n % 256)); $w.Write([byte]($n % 256)); $w.Write([byte]0); $w.Write([byte]0)
        $w.Write([int16]1); $w.Write([int16]32); $w.Write([int]$images[$i].Length); $w.Write([int]$offset)
        $offset += $images[$i].Length
    }
    foreach ($im in $images) { $w.Write($im) }
    $w.Close()
    "wrote $out ($((Get-Item -LiteralPath $out).Length) bytes)"
}

Write-Ico (Join-Path $repo 'port\game_icon.ico')
Write-Ico (Join-Path $repo 'launcher\src-tauri\icons\game.ico')
# Resource 1: the exe's icon in Explorer, and the one port\main.cpp puts on the game window.
$rc = Join-Path $repo 'port\app.rc'
[System.IO.File]::WriteAllText($rc, "// Written by scripts\make_game_icon.ps1 (not in Git: the icon is the game's own picture).`r`n1 ICON `"game_icon.ico`"`r`n")
"wrote $rc"
