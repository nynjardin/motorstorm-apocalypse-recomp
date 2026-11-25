# pair_montage.ps1 -Dir <lan_test output> [-Out <png>] [-X 1020 -Y 50 -W 256 -H 90]: one small image with the
# same region (default: the timer at the top right of the race HUD) of every pair of captures made by
# screenshot_pair.ps1 (s<t>_h.png / s<t>_j.png): one row per instant, host on the left, joiner on the right,
# the instant written at the left. To compare the two instances' timers without opening every capture.
param([string]$Dir, [string]$Out = '', [int]$X = 1020, [int]$Y = 50, [int]$W = 256, [int]$H = 90, [string]$Match = '')
Add-Type -AssemblyName System.Drawing
if (-not $Out) { $Out = Join-Path $Dir 'montage.png' }
$hs = @(Get-ChildItem $Dir -Filter 's*_h.png' | Where-Object { -not $Match -or $_.Name -match $Match } | Sort-Object Name)
if (-not $hs) { "no pair in $Dir"; exit 1 }
$bmp = New-Object System.Drawing.Bitmap (60 + 2 * $W), ($H * $hs.Count)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.Clear([System.Drawing.Color]::Black)
$font = New-Object System.Drawing.Font 'Consolas', 11
$row = 0
foreach ($f in $hs) {
    $j = Join-Path $Dir ($f.Name -replace '_h\.png$', '_j.png')
    $src = New-Object System.Drawing.Rectangle $X, $Y, $W, $H
    foreach ($pair in @(@($f.FullName, 60), @($j, (60 + $W)))) {
        if (-not (Test-Path $pair[0])) { continue }
        $im = [System.Drawing.Image]::FromFile($pair[0])
        $g.DrawImage($im, (New-Object System.Drawing.Rectangle $pair[1], ($row * $H), $W, $H), $src, [System.Drawing.GraphicsUnit]::Pixel)
        $im.Dispose()
    }
    $g.DrawString(($f.Name -replace '_h\.png$', ''), $font, [System.Drawing.Brushes]::Yellow, 2, ($row * $H + 4))
    $row++
}
$g.Dispose()
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png); $bmp.Dispose()
"saved $Out ($($hs.Count) rows)"
