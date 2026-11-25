# make_icon.ps1: draws the launcher's icon (src-tauri\icons\icon.ico), 16 to 256 px, 32-bit BMP entries
# (the oldest ICO form: every resource compiler takes it). Run again to change the drawing.
Add-Type -AssemblyName System.Drawing
$out = Join-Path $PSScriptRoot 'src-tauri\icons\icon.ico'
New-Item -ItemType Directory -Force (Split-Path $out) | Out-Null
$sizes = 16, 24, 32, 48, 64, 128, 256
$images = foreach ($n in $sizes) {
    $bmp = New-Object System.Drawing.Bitmap $n, $n, ([System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = 'AntiAlias'; $g.TextRenderingHint = 'AntiAliasGridFit'
    $g.Clear([System.Drawing.Color]::Transparent)
    $r = [float]($n * 0.2); $d = 2 * $r; $w = $n - 1
    $path = New-Object System.Drawing.Drawing2D.GraphicsPath
    $path.AddArc(0, 0, $d, $d, 180, 90); $path.AddArc($w - $d, 0, $d, $d, 270, 90)
    $path.AddArc($w - $d, $w - $d, $d, $d, 0, 90); $path.AddArc(0, $w - $d, $d, $d, 90, 90); $path.CloseFigure()
    $brush = New-Object System.Drawing.Drawing2D.LinearGradientBrush (New-Object System.Drawing.Point 0, 0), (New-Object System.Drawing.Point $n, $n), ([System.Drawing.Color]::FromArgb(255, 245, 168, 0)), ([System.Drawing.Color]::FromArgb(255, 226, 71, 15))
    $g.FillPath($brush, $path)
    $font = New-Object System.Drawing.Font 'Segoe UI', ([float]($n * 0.36)), ([System.Drawing.FontStyle]::Bold), ([System.Drawing.GraphicsUnit]::Pixel)
    $fmt = New-Object System.Drawing.StringFormat; $fmt.Alignment = 'Center'; $fmt.LineAlignment = 'Center'
    $g.DrawString('MS', $font, (New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(255, 26, 17, 0))), (New-Object System.Drawing.RectangleF 0, 0, $n, $n), $fmt)
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
"wrote $out ($((Get-Item $out).Length) bytes)"
